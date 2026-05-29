// Optional second-pass false-positive filter. Inspired by deepsec's
// `revalidate` stage (vercel-labs/deepsec), which empirically cuts FP rate
// ~50% on whole-repo scans. Smaller upside expected here since dedup +
// severity overshoot already filter aggressively, but worth surfacing as an
// opt-in knob (PR_REVIEWER_REVALIDATE=1) — doubles cost on the findings list.
//
// For each finding, ask the model to re-read the diff and emit a verdict:
//   true-positive | false-positive | uncertain
// Drops `false-positive`; keeps the rest (uncertain stays so we don't throw
// away signal on ambiguous cases). Failures during revalidation pass through
// the original finding — we never silently drop on transport errors.

import type { Finding } from './triage.js';
import type { ModelClient } from './model-client.js';

export type Verdict = 'true-positive' | 'false-positive' | 'uncertain';

export interface RevalidatedFinding extends Finding {
  verdict?: Verdict;
  verdictReasoning?: string;
}

const REVALIDATE_SYSTEM = `You are reviewing a single finding from an earlier code review pass to check if it is a real issue or a false positive.

You will be given the original PR diff and one finding. Re-read the diff carefully and decide whether the finding is correct.

Respond on a single line in exactly this format:
[VERDICT] reasoning

Where VERDICT is one of: TRUE_POSITIVE, FALSE_POSITIVE, UNCERTAIN.

Guidelines:
- TRUE_POSITIVE: the finding accurately describes a real issue in the diff.
- FALSE_POSITIVE: the finding misreads the code, references nonexistent code, contradicts what the diff actually does, or describes an issue that the diff itself already mitigates.
- UNCERTAIN: not enough context in the diff to confirm or refute. Prefer this over guessing.

Do not output anything else. One line, starting with the bracketed verdict.`;

const VERDICT_PATTERN = /^\[(TRUE_POSITIVE|FALSE_POSITIVE|UNCERTAIN)\]\s*(.*)$/;

function userMessage(finding: Finding, diff: string): string {
  return `Original PR diff:

\`\`\`diff
${diff}
\`\`\`

Finding to revalidate:
[${finding.severity}] ${finding.file}:${finding.line ?? '?'} — ${finding.description}
(reported by: ${finding.reviewer})`;
}

function parseVerdict(text: string): { verdict: Verdict; reasoning: string } | null {
  for (const rawLine of text.split('\n')) {
    const line = rawLine.trim();
    if (!line) continue;
    const m = VERDICT_PATTERN.exec(line);
    if (!m) continue;
    const tag = m[1];
    const reasoning = (m[2] ?? '').trim();
    if (tag === 'TRUE_POSITIVE') return { verdict: 'true-positive', reasoning };
    if (tag === 'FALSE_POSITIVE') return { verdict: 'false-positive', reasoning };
    return { verdict: 'uncertain', reasoning };
  }
  return null;
}

export interface RevalidateResult {
  kept: RevalidatedFinding[];
  dropped: RevalidatedFinding[];
  errors: number;
  // Findings NOT revalidated because the call budget was exhausted (Rule 6).
  // They are kept in the final output (never dropped), but surfaced separately
  // so the PR comment can flag that they went unverified (Rule 12).
  unverified: RevalidatedFinding[];
}

// Severity order so the budget spends on the highest-stakes findings first;
// the cheap-to-lose tail (LOW/NITPICK) is what goes unverified under a cap.
const SEVERITY_ORDER: Record<string, number> = {
  CRITICAL: 5, HIGH: 4, MEDIUM: 3, LOW: 2, NITPICK: 1,
};

// Default cap on revalidation model calls. Revalidation doubles cost across
// the findings list, so without a ceiling a noisy high-recall ensemble can
// blow the budget. Override with PR_REVIEWER_MAX_REVALIDATE; 0 disables the
// cap (revalidate everything).
const DEFAULT_MAX_REVALIDATE = 30;

export async function revalidateFindings(
  findings: Finding[],
  diff: string,
  client: ModelClient,
): Promise<RevalidateResult> {
  if (findings.length === 0) {
    return { kept: [], dropped: [], errors: 0, unverified: [] };
  }

  const cap = parseInt(
    process.env.PR_REVIEWER_MAX_REVALIDATE ?? String(DEFAULT_MAX_REVALIDATE),
    10,
  );
  // Spend the budget on the highest-severity findings first.
  const ordered = [...findings].sort(
    (a, b) => (SEVERITY_ORDER[b.severity] ?? 0) - (SEVERITY_ORDER[a.severity] ?? 0),
  );
  const toRevalidate = cap > 0 ? ordered.slice(0, cap) : ordered;
  const unverified: RevalidatedFinding[] = (cap > 0 ? ordered.slice(cap) : []).map(
    (f) => ({ ...f, verdict: 'uncertain', verdictReasoning: 'revalidation budget exhausted' }),
  );

  const results = await Promise.all(
    toRevalidate.map(async (f): Promise<RevalidatedFinding> => {
      try {
        const response = await client.createReview(
          { aggressive: REVALIDATE_SYSTEM, soft: REVALIDATE_SYSTEM },
          userMessage(f, diff),
        );
        const parsed = parseVerdict(response.text);
        if (!parsed) {
          return { ...f, verdict: 'uncertain', verdictReasoning: 'unparseable verdict' };
        }
        return { ...f, verdict: parsed.verdict, verdictReasoning: parsed.reasoning };
      } catch (err) {
        // Transport/model error — keep the finding rather than silently drop it.
        return {
          ...f,
          verdict: 'uncertain',
          verdictReasoning: `revalidation error: ${err instanceof Error ? err.message : String(err)}`,
        };
      }
    }),
  );

  const kept: RevalidatedFinding[] = [];
  const dropped: RevalidatedFinding[] = [];
  let errors = 0;
  for (const r of results) {
    if (r.verdictReasoning?.startsWith('revalidation error:')) errors++;
    if (r.verdict === 'false-positive') dropped.push(r);
    else kept.push(r);
  }
  // Budget-skipped findings are kept in the output but tracked as unverified.
  kept.push(...unverified);
  return { kept, dropped, errors, unverified };
}
