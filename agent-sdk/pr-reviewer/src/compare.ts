// A/B comparison harness. Runs the same PR through two providers (typically
// Anthropic vs. NVIDIA ensemble), then uses the existing Dice-similarity dedup
// as the overlap oracle: if a finding from side A would merge with a finding
// from side B under deduplicateFindings, they're considered the same issue.
//
// Usage:
//   node dist/compare.js <PR_NUMBER> [--anthropic] [--nvidia]
//
// Env vars pass through to each provider's ModelClient (ANTHROPIC_*, NVIDIA_*,
// NVIDIA_MODEL_POOL, etc.). If neither flag is given, both are run.

import { execFileSync } from 'child_process';
import { getModelClient } from './model-client.js';
import { runReview } from './review.js';
import { deduplicateFindings } from './triage.js';
import type { Finding } from './triage.js';

interface SideResult {
  label: string;
  modelId: string;
  findings: Finding[];       // raw, pre-dedup
  deduped: Finding[];        // after within-side dedup
  elapsedMs: number;
  ok: boolean;
  error?: string;
}

function parseArgs(): { prNumber: number; runAnthropic: boolean; runNvidia: boolean } {
  const args = process.argv.slice(2);
  let prNumber: number | null = null;
  let runAnthropic = false;
  let runNvidia = false;

  for (const arg of args) {
    if (arg === '--anthropic') runAnthropic = true;
    else if (arg === '--nvidia') runNvidia = true;
    else if (/^\d+$/.test(arg)) prNumber = parseInt(arg, 10);
  }

  if (prNumber === null) {
    console.error(
      'Usage: node dist/compare.js <PR_NUMBER> [--anthropic] [--nvidia]\n' +
      '  (if no flag given, runs both)',
    );
    process.exit(1);
  }

  if (!runAnthropic && !runNvidia) {
    runAnthropic = true;
    runNvidia = true;
  }

  return { prNumber, runAnthropic, runNvidia };
}

async function runSide(label: string, providerName: string, diff: string): Promise<SideResult> {
  const start = Date.now();
  try {
    const client = getModelClient(providerName);
    const { findings } = await runReview(diff, client, { logPrefix: `[${label}]` });
    const deduped = deduplicateFindings(findings);
    return {
      label,
      modelId: client.modelId,
      findings,
      deduped,
      elapsedMs: Date.now() - start,
      ok: true,
    };
  } catch (err) {
    return {
      label,
      modelId: 'n/a',
      findings: [],
      deduped: [],
      elapsedMs: Date.now() - start,
      ok: false,
      error: err instanceof Error ? err.message : String(err),
    };
  }
}

// Tag each finding with its side-of-origin, then run them all through dedup.
// The dedup collapses cross-side matches into a single entry. By inspecting
// the `reviewer` field of each surviving finding we can tell whether it came
// solely from side A, solely from side B, or was collapsed (shared).
function analyzeOverlap(a: Finding[], b: Finding[], labelA: string, labelB: string): {
  shared: number;
  uniqueA: number;
  uniqueB: number;
} {
  // Re-tag so we can trace provenance through dedup.
  const tagged: Finding[] = [
    ...a.map((f) => ({ ...f, reviewer: `__${labelA}__${f.reviewer}` })),
    ...b.map((f) => ({ ...f, reviewer: `__${labelB}__${f.reviewer}` })),
  ];
  const merged = deduplicateFindings(tagged);

  // For each surviving finding, check whether its original side had a sibling
  // that got absorbed into it. We do this by running the overlap check again:
  // a survivor from side A is "shared" if there exists a side-B finding that
  // would dedupe with it.
  let shared = 0;
  let uniqueA = 0;
  let uniqueB = 0;

  for (const survivor of merged) {
    const fromA = survivor.reviewer.startsWith(`__${labelA}__`);
    // The dedup already collapsed cross-side pairs into one survivor. Ask
    // whether the *other* side had a finding that would have merged with
    // this one — if yes, this survivor represents a pair (shared). Each
    // merged pair yields exactly one survivor, so counting shared once per
    // such survivor is correct regardless of which side won the severity tie.
    const otherSide = fromA ? b : a;
    const hadDupeOnOtherSide = otherSide.some((candidate) =>
      deduplicateFindings([
        { ...survivor, reviewer: 'survivor' },
        { ...candidate, reviewer: 'other' },
      ]).length === 1,
    );
    if (hadDupeOnOtherSide) {
      shared++;
    } else if (fromA) {
      uniqueA++;
    } else {
      uniqueB++;
    }
  }

  return { shared, uniqueA, uniqueB };
}

function severityBreakdown(findings: Finding[]): string {
  const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, NITPICK: 0 };
  for (const f of findings) counts[f.severity]++;
  return `C:${counts.CRITICAL} H:${counts.HIGH} M:${counts.MEDIUM} L:${counts.LOW} N:${counts.NITPICK}`;
}

async function main(): Promise<void> {
  const { prNumber, runAnthropic, runNvidia } = parseArgs();

  // execFileSync is the safer variant — the shell-injection concern flagged
  // on execSync doesn't apply here, but compare.ts is a new file and we may
  // as well model good hygiene.
  const diff = execFileSync('gh', ['pr', 'diff', String(prNumber)], {
    encoding: 'utf8',
  });
  console.log(`PR #${prNumber}: ${diff.split('\n').length} lines\n`);

  // Run both sides sequentially (not parallel) so their console output
  // interleaves cleanly via the logPrefix rather than racing.
  const results: SideResult[] = [];
  if (runAnthropic) {
    console.log('─── Anthropic ───');
    results.push(await runSide('anthropic', 'anthropic', diff));
    console.log();
  }
  if (runNvidia) {
    console.log('─── NVIDIA ───');
    results.push(await runSide('nvidia', 'nvidia', diff));
    console.log();
  }

  console.log('─── Summary ───');
  for (const r of results) {
    const status = r.ok ? `${r.deduped.length} findings (${severityBreakdown(r.deduped)})` : `FAILED: ${r.error}`;
    console.log(`  ${r.label.padEnd(10)} ${(r.elapsedMs / 1000).toFixed(1).padStart(5)}s  ${status}  [${r.modelId}]`);
  }

  if (results.length === 2 && results[0].ok && results[1].ok) {
    const [A, B] = results;
    const overlap = analyzeOverlap(A.deduped, B.deduped, A.label, B.label);
    const total = overlap.shared + overlap.uniqueA + overlap.uniqueB;
    const agreement = total > 0 ? ((overlap.shared / total) * 100).toFixed(0) : '0';
    console.log();
    console.log('─── Overlap (Dice ≥ 0.25, same file, line ±3) ───');
    console.log(`  Shared:          ${overlap.shared}`);
    console.log(`  ${A.label} only:    ${overlap.uniqueA}`);
    console.log(`  ${B.label} only:       ${overlap.uniqueB}`);
    console.log(`  Agreement rate:  ${agreement}% (${overlap.shared}/${total})`);
  }
}

main().catch((err) => {
  console.error('Unhandled error:', err);
  process.exit(1);
});
