import { test } from 'node:test';
import assert from 'node:assert/strict';

import { runReview } from './review.js';
import { revalidateFindings } from './revalidate.js';
import { formatPRComment } from './github.js';
import { triageFindings } from './triage.js';
import type { Finding } from './triage.js';
import type { ModelClient, ReviewResponse, SystemPrompts } from './model-client.js';

// Minimal fake client. Each test supplies the createReview behaviour it needs;
// the goal is to drive review.ts / revalidate.ts down their partial-failure
// and budget branches deterministically (no network, no model variance).
function fakeClient(
  createReview: (systems: SystemPrompts, user: string) => Promise<ReviewResponse>,
): ModelClient {
  return {
    providerName: 'fake',
    modelId: 'fake-model',
    preferSoftPrompts: false,
    createReview,
  };
}

// 60 plain lines → multi-reviewer path (≥50), no special-file reviewers.
const PLAIN_DIFF = Array.from({ length: 60 }, (_, i) => `+ line ${i}`).join('\n');

test('review: a reviewer that throws is recorded in degraded, not swallowed (Rule 12)', async () => {
  const client = fakeClient(async () => {
    throw new Error('502 gateway');
  });
  const r = await runReview(PLAIN_DIFF, client);
  // Invariant: a failed reviewer must NOT inflate the reported coverage.
  assert.equal(r.reviewerCount, 0);
  assert.equal(r.plannedReviewerCount, 3);
  assert.deepEqual([...r.degraded].sort(), ['code', 'security', 'silentFailure']);
  assert.equal(r.findings.length, 0);
});

test('review: ensemble segments preserve per-model provenance (Rule 7)', async () => {
  // Small-PR path exercises parseResponse with segments from two models.
  const client = fakeClient(async (): Promise<ReviewResponse> => ({
    text: 'ignored when segments present',
    segments: [
      { source: 'kimi', text: '[HIGH] a.ts:1 — null deref in handler' },
      { source: 'deepseek', text: '[HIGH] a.ts:1 — null deref in handler' },
    ],
  }));
  const r = await runReview('+ one line', client); // <50 → combined reviewer
  // Two raw findings, each tagged with the model that produced it.
  const reviewers = r.findings.map((f) => f.reviewer).sort();
  assert.deepEqual(reviewers, ['combined@deepseek', 'combined@kimi']);
});

test('review: ensemble per-model failures roll into degraded (Rule 12)', async () => {
  const client = fakeClient(async (): Promise<ReviewResponse> => ({
    text: '[LOW] a.ts:2 — minor',
    segments: [{ source: 'kimi', text: '[LOW] a.ts:2 — minor' }],
    failures: [{ source: 'minimax', error: '504 timeout' }],
  }));
  const r = await runReview('+ one line', client);
  assert.deepEqual(r.degraded, ['combined@minimax']);
});

test('review: reviewers beyond the agent cap land in skipped (Rule 12)', async () => {
  // python + alembic + async + route → 6 reviewers selected.
  const richDiff =
    '+++ b/app/routes/api.py\n' +
    '+import alembic  # migration\n' +
    '+async def view():\n' +
    '+    await thing()\n' +
    Array.from({ length: 50 }, (_, i) => `+ pad ${i}`).join('\n');
  const client = fakeClient(async () => ({ text: '' }));
  const r = await runReview(richDiff, client, { maxAgents: 4 });
  // The 3 deterministic-scope reviewers past the core 3 are skipped.
  assert.deepEqual([...r.skipped].sort(), ['apiDoc', 'async', 'migration']);
});

test('revalidate: budget cap leaves low-severity findings unverified but kept (Rule 6)', async () => {
  const findings: Finding[] = [
    { severity: 'CRITICAL', file: 'a.ts', line: 1, description: 'crit', reviewer: 'code' },
    { severity: 'HIGH', file: 'b.ts', line: 2, description: 'high', reviewer: 'code' },
    { severity: 'MEDIUM', file: 'c.ts', line: 3, description: 'med', reviewer: 'code' },
    { severity: 'LOW', file: 'd.ts', line: 4, description: 'low', reviewer: 'code' },
    { severity: 'NITPICK', file: 'e.ts', line: 5, description: 'nit', reviewer: 'code' },
  ];
  process.env.PR_REVIEWER_MAX_REVALIDATE = '2';
  const client = fakeClient(async () => ({ text: '[TRUE_POSITIVE] looks real' }));
  try {
    const res = await revalidateFindings(findings, 'diff', client);
    // Budget = 2 → the 3 lowest-severity findings go unverified...
    assert.equal(res.unverified.length, 3);
    assert.deepEqual(
      res.unverified.map((f) => f.severity).sort(),
      ['LOW', 'MEDIUM', 'NITPICK'],
    );
    // ...but nothing is dropped, and all 5 survive into kept.
    assert.equal(res.dropped.length, 0);
    assert.equal(res.kept.length, 5);
  } finally {
    delete process.env.PR_REVIEWER_MAX_REVALIDATE;
  }
});

test('formatPRComment: partial coverage surfaces a banner and honest reviewer count', () => {
  const triaged = triageFindings([
    { severity: 'HIGH', file: 'a.ts', line: 1, description: 'x', reviewer: 'code' },
  ]);
  const comment = formatPRComment(triaged, 2, {
    plannedReviewerCount: 3,
    degraded: ['security'],
    skipped: [],
    unverifiedCount: 4,
    droppedCount: 1,
  });
  assert.match(comment, /2 of 3 reviewers/);
  assert.match(comment, /Partial coverage/);
  assert.match(comment, /security/);
  assert.match(comment, /4 finding\(s\) kept but unverified/);
  assert.match(comment, /1 finding\(s\) dropped as false positives/);
});

test('formatPRComment: full coverage shows no partial-coverage banner', () => {
  const triaged = triageFindings([
    { severity: 'LOW', file: 'a.ts', line: 1, description: 'x', reviewer: 'code' },
  ]);
  const comment = formatPRComment(triaged, 3, { plannedReviewerCount: 3 });
  assert.doesNotMatch(comment, /Partial coverage/);
  assert.match(comment, /across 3 reviewers/);
});
