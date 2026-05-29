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
  // Reviewers that actually produced output (errored reviewers excluded).
  reviewerCount: number;
  // Reviewers selected before any failure or maxAgents truncation. When this
  // exceeds reviewerCount, coverage was partial — see degraded/skipped.
  plannedReviewerCount: number;
  diffLines: number;
  // Reviewer (or reviewer@model) labels that threw / timed out. Rule 12: a
  // degraded reviewer is reported, never silently dropped to an empty list.
  degraded: string[];
  // Reviewers dropped because the selection exceeded maxAgents.
  skipped: string[];
}

export async function runReview(
  diff: string,
  client: ModelClient,
  opts: RunReviewOptions = {},
): Promise<RunReviewResult> {
  const { maxAgents = 6, logPrefix = '' } = opts;
  const prefix = logPrefix ? `${logPrefix} ` : '';
  const diffLines = diff.split('\n').length;
  const findings: Finding[] = [];
  const degraded: string[] = [];
  const skipped: string[] = [];

  // Parse a response into findings, splitting ensemble segments so each
  // model's findings carry a `reviewer@model` label. That label flows into
  // deduplicateFindings' mergedFrom, so cross-model consensus survives the
  // join (Rule 7) instead of every finding reading as the same reviewer.
  // Also rolls any per-source failures into `degraded` (Rule 12).
  const parseResponse = (reviewerName: string, response: { text: string; segments?: { source: string; text: string }[]; failures?: { source: string; error: string }[] }): Finding[] => {
    for (const f of response.failures ?? []) {
      degraded.push(`${reviewerName}@${f.source}`);
    }
    if (response.segments && response.segments.length > 0) {
      return response.segments.flatMap((seg) =>
        parseFindings(`${reviewerName}@${seg.source}`, seg.text),
      );
    }
    return parseFindings(reviewerName, response.text);
  };

  if (diffLines < 50) {
    console.log(`${prefix}Small PR detected — using single combined reviewer`);
    try {
      const response = await client.createReview(
        // Combined small-PR prompt is already neutral; no soft variant needed.
        { aggressive: COMBINED_SMALL_PR_SYSTEM },
        combinedSmallPRUserMessage(diff),
      );
      const parsed = parseResponse('combined', response);
      findings.push(...parsed);
      console.log(`${prefix}  combined: ${parsed.length} findings`);
      logCacheUsage(`${prefix}combined`, response.usage);
      return { findings, reviewerCount: 1, plannedReviewerCount: 1, diffLines, degraded, skipped };
    } catch (err) {
      console.error(`${prefix}${client.providerName} API error (combined reviewer):`, err);
      degraded.push('combined');
      return { findings, reviewerCount: 0, plannedReviewerCount: 1, diffLines, degraded, skipped };
    }
  }

  let reviewers = selectReviewers(diff);
  const plannedReviewerCount = reviewers.length;
  console.log(`${prefix}Selected reviewers: ${reviewers.map((r) => r.name).join(', ')}`);

  if (reviewers.length > maxAgents) {
    console.warn(
      `${prefix}Reviewer count (${reviewers.length}) exceeds maxAgents (${maxAgents}), truncating to core 3`,
    );
    skipped.push(...reviewers.slice(3).map((r) => r.name));
    reviewers = reviewers.slice(0, 3);
  }

  const results = await Promise.all(
    reviewers.map(async (reviewer): Promise<{ findings: Finding[]; ran: boolean }> => {
      try {
        console.log(`${prefix}  Running reviewer: ${reviewer.name}`);
        // Pass both variants; each client picks its own at call time.
        // Crucial for FallbackModelClient — lets Anthropic-as-fallback use
        // aggressive even when primary was NVIDIA (soft).
        const response = await client.createReview(
          { aggressive: reviewer.system, soft: reviewer.systemSoft },
          reviewer.userMessage(diff),
        );
        const parsed = parseResponse(reviewer.name, response);
        console.log(`${prefix}  ${reviewer.name}: ${parsed.length} findings`);
        logCacheUsage(`${prefix}${reviewer.name}`, response.usage);
        return { findings: parsed, ran: true };
      } catch (err) {
        // Rule 12 — record the degraded reviewer rather than silently
        // returning [] and letting reviewerCount over-claim coverage.
        console.error(`${prefix}${client.providerName} API error (${reviewer.name}):`, err);
        degraded.push(reviewer.name);
        return { findings: [], ran: false };
      }
    }),
  );

  let reviewerCount = 0;
  for (const r of results) {
    findings.push(...r.findings);
    if (r.ran) reviewerCount++;
  }

  return { findings, reviewerCount, plannedReviewerCount, diffLines, degraded, skipped };
}
