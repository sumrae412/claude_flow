// Core review pipeline, factored out of index.ts so the A/B comparison harness
// in compare.ts can run the same pipeline with different ModelClients without
// going through CLI subprocesses. Returns raw (pre-dedup) findings so callers
// can decide whether to dedupe per-side or across-sides for overlap analysis.

import {
  selectReviewers,
  COMBINED_SMALL_PR_SYSTEM,
  combinedSmallPRUserMessage,
} from './reviewers.js';
import { parseFindings } from './triage.js';
import type { Finding } from './triage.js';
import type { ModelClient } from './model-client.js';

// Mirrors the Anthropic cache_control usage shape so the existing log helper
// works for Anthropic and no-ops for others.
interface CacheUsage {
  cache_creation_input_tokens?: number | null;
  cache_read_input_tokens?: number | null;
  input_tokens?: number | null;
}

function logCacheUsage(reviewer: string, usage: CacheUsage | undefined): void {
  if (!usage) return;
  const created = usage.cache_creation_input_tokens ?? 0;
  const read = usage.cache_read_input_tokens ?? 0;
  const input = usage.input_tokens ?? 0;
  if (created === 0 && read === 0) return;
  console.log(`  ${reviewer} cache: read=${read} created=${created} fresh_input=${input}`);
}

export interface RunReviewOptions {
  maxAgents?: number;
  // Prefix prepended to console.log lines so compare.ts can distinguish
  // concurrent runs' output (e.g., "[anthropic] combined: 5 findings").
  logPrefix?: string;
}

export interface RunReviewResult {
  findings: Finding[];
  reviewerCount: number;
  diffLines: number;
}

// Dynamic dispatch by diff size: small PRs get a single combined reviewer,
// larger PRs fan out to N reviewers chosen by `selectReviewers`. The pattern
// rhymes with poteto/noodle's adversarial-review (1 reviewer <50 LOC, 2 reviewers
// 50–200, 3 reviewers 200+/5+ files); ours uses finer-grained selection rather
// than fixed buckets. The multi-model fan-out (NVIDIA_MODEL_POOL) is validated
// by Nolan Lawson's observation that multiple models for one PR review
// "significantly reduces hallucinations and false positives" — see
// https://nolanlawson.com/2026/05/25/using-ai-to-write-better-code-more-slowly/
export async function runReview(
  diff: string,
  client: ModelClient,
  opts: RunReviewOptions = {},
): Promise<RunReviewResult> {
  const { maxAgents = 6, logPrefix = '' } = opts;
  const prefix = logPrefix ? `${logPrefix} ` : '';
  const diffLines = diff.split('\n').length;
  const findings: Finding[] = [];
  let reviewerCount = 0;

  if (diffLines < 50) {
    reviewerCount = 1;
    console.log(`${prefix}Small PR detected — using single combined reviewer`);
    try {
      const response = await client.createReview(
        // Combined small-PR prompt is already neutral; no soft variant needed.
        { aggressive: COMBINED_SMALL_PR_SYSTEM },
        combinedSmallPRUserMessage(diff),
      );
      const parsed = parseFindings('combined', response.text);
      findings.push(...parsed);
      console.log(`${prefix}  combined: ${parsed.length} findings`);
      logCacheUsage(`${prefix}combined`, response.usage);
    } catch (err) {
      console.error(`${prefix}${client.providerName} API error (combined reviewer):`, err);
    }
    return { findings, reviewerCount, diffLines };
  }

  let reviewers = selectReviewers(diff);
  console.log(`${prefix}Selected reviewers: ${reviewers.map((r) => r.name).join(', ')}`);

  if (reviewers.length > maxAgents) {
    console.warn(
      `${prefix}Reviewer count (${reviewers.length}) exceeds maxAgents (${maxAgents}), truncating to core 3`,
    );
    reviewers = reviewers.slice(0, 3);
  }
  reviewerCount = reviewers.length;

  const results = await Promise.all(
    reviewers.map(async (reviewer) => {
      try {
        console.log(`${prefix}  Running reviewer: ${reviewer.name}`);
        // Pass both variants; each client picks its own at call time.
        // Crucial for FallbackModelClient — lets Anthropic-as-fallback use
        // aggressive even when primary was NVIDIA (soft).
        const response = await client.createReview(
          { aggressive: reviewer.system, soft: reviewer.systemSoft },
          reviewer.userMessage(diff),
        );
        const parsed = parseFindings(reviewer.name, response.text);
        console.log(`${prefix}  ${reviewer.name}: ${parsed.length} findings`);
        logCacheUsage(`${prefix}${reviewer.name}`, response.usage);
        return parsed;
      } catch (err) {
        console.error(`${prefix}${client.providerName} API error (${reviewer.name}):`, err);
        return [] as Finding[];
      }
    }),
  );
  for (const batch of results) findings.push(...batch);

  return { findings, reviewerCount, diffLines };
}
