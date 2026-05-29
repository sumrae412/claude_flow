// Throwaway A/B harness for the revalidation FP-cut claim (handoff Task 1).
// NOT shipped — exists only to produce the numbers behind the decision record.
//
// Design: run the review pass ONCE, then the post-dedup list is the "off" arm
// and revalidateFindings(deduped) is the "on" arm. Running review once isolates
// the revalidate effect from LLM run-to-run variance (the whole point — an A/B
// that re-runs review would confound the filter with sampling noise).
//
// Emits: every dropped finding with its verdict reasoning (so a human can judge
// whether the drop was a genuine FP), plus call-count and input-token cost of
// the revalidation pass.
//
// Usage: node dist/compare-revalidate.js <PR_NUMBER> [<PR_NUMBER> ...]

import { execFileSync } from 'child_process';
import { getModelClient } from './model-client.js';
import type { ModelClient, ReviewResponse, SystemPrompts } from './model-client.js';
import { runReview } from './review.js';
import { deduplicateFindings } from './triage.js';
import { revalidateFindings } from './revalidate.js';
import type { Finding } from './triage.js';

// Wraps a ModelClient to count calls + sum input tokens, so we can attribute
// cost to the review pass vs. the revalidation pass separately.
class CountingClient implements ModelClient {
  readonly providerName: string;
  readonly modelId: string;
  preferSoftPrompts = false;
  calls = 0;
  inputTokens = 0;
  cacheReadTokens = 0;
  cacheCreateTokens = 0;

  constructor(private inner: ModelClient) {
    this.providerName = inner.providerName;
    this.modelId = inner.modelId;
  }

  async createReview(systems: SystemPrompts, user: string): Promise<ReviewResponse> {
    this.calls++;
    const r = await this.inner.createReview(systems, user);
    this.inputTokens += r.usage?.input_tokens ?? 0;
    this.cacheReadTokens += r.usage?.cache_read_input_tokens ?? 0;
    this.cacheCreateTokens += r.usage?.cache_creation_input_tokens ?? 0;
    return r;
  }

  snapshot() {
    return {
      calls: this.calls,
      inputTokens: this.inputTokens,
      cacheReadTokens: this.cacheReadTokens,
      cacheCreateTokens: this.cacheCreateTokens,
    };
  }

  reset() {
    this.calls = 0;
    this.inputTokens = 0;
    this.cacheReadTokens = 0;
    this.cacheCreateTokens = 0;
  }
}

function fmtFinding(f: Finding): string {
  return `[${f.severity}] ${f.file}:${f.line ?? '?'} — ${f.description}`;
}

async function runPR(prNumber: number): Promise<void> {
  const diff = execFileSync('gh', ['pr', 'diff', String(prNumber)], { encoding: 'utf8' });
  const diffLines = diff.split('\n').length;
  console.log(`\n${'═'.repeat(72)}`);
  console.log(`PR #${prNumber} — ${diffLines} diff lines`);
  console.log('═'.repeat(72));

  const client = new CountingClient(getModelClient());

  // ── Review pass (shared by both arms) ──
  const { findings, reviewerCount } = await runReview(diff, client, { logPrefix: `[#${prNumber}]` });
  const deduped = deduplicateFindings(findings);
  const reviewCost = client.snapshot();

  console.log(`\nReview: ${reviewerCount} reviewer(s), ${findings.length} raw → ${deduped.length} after dedup`);
  console.log(`Review cost: ${reviewCost.calls} calls, ${reviewCost.inputTokens} input tok` +
    `, ${reviewCost.cacheReadTokens} cache-read, ${reviewCost.cacheCreateTokens} cache-create`);

  console.log('\n── OFF arm (deduped, what ships without revalidate) ──');
  for (const f of deduped) console.log(`  ${fmtFinding(f)}`);
  if (deduped.length === 0) console.log('  (no findings)');

  if (deduped.length === 0) {
    console.log('\nNo findings to revalidate — revalidate is a no-op on this PR.');
    return;
  }

  // ── Revalidation pass (the "on" arm transform) ──
  client.reset();
  const { kept, dropped, errors, unverified } = await revalidateFindings(deduped, diff, client);
  const revalCost = client.snapshot();

  console.log('\n── ON arm (revalidate applied) ──');
  console.log(`Kept ${kept.length}, dropped ${dropped.length} FP, ${errors} errored, ${unverified.length} unverified(budget)`);
  console.log(`Revalidate cost: ${revalCost.calls} calls, ${revalCost.inputTokens} input tok` +
    `, ${revalCost.cacheReadTokens} cache-read, ${revalCost.cacheCreateTokens} cache-create`);

  const inputMultiplier = reviewCost.inputTokens > 0
    ? (revalCost.inputTokens / reviewCost.inputTokens).toFixed(2)
    : 'n/a';
  console.log(`Cost ratio (revalidate input tok / review input tok): ${inputMultiplier}×`);

  console.log('\n── DROPPED findings (claimed false positives — judge these) ──');
  if (dropped.length === 0) console.log('  (none dropped)');
  for (const f of dropped as (Finding & { verdictReasoning?: string })[]) {
    console.log(`  ${fmtFinding(f)}`);
    console.log(`     ↳ FP reasoning: ${f.verdictReasoning ?? '(none)'}`);
  }

  console.log('\n── SUMMARY ──');
  console.log(`  OFF: ${deduped.length} findings | ON: ${kept.length} findings | dropped: ${dropped.length}` +
    ` (${deduped.length > 0 ? ((dropped.length / deduped.length) * 100).toFixed(0) : 0}% of post-dedup)` +
    ` | extra cost: ${revalCost.calls} calls / ${revalCost.inputTokens} input tok / ${inputMultiplier}× review input`);
}

async function main(): Promise<void> {
  const prNumbers = process.argv.slice(2).filter((a) => /^\d+$/.test(a)).map((a) => parseInt(a, 10));
  if (prNumbers.length === 0) {
    console.error('Usage: node dist/compare-revalidate.js <PR_NUMBER> [<PR_NUMBER> ...]');
    process.exit(1);
  }
  for (const pr of prNumbers) {
    await runPR(pr);
  }
}

main().catch((err) => {
  console.error('Unhandled error:', err);
  process.exit(1);
});
