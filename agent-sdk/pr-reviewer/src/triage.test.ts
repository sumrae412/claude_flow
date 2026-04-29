// Run with: npm test  (or node --test dist/*.test.js after build)
// Uses node:test (built-in, Node 22+). No jest, no vitest — keeps the
// dev-dep surface small.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseFindings, deduplicateFindings, triageFindings } from './triage.js';
import { selectReviewers } from './reviewers.js';
import type { Finding } from './triage.js';

const f = (over: Partial<Finding>): Finding => ({
  severity: 'MEDIUM',
  file: 'a.ts',
  line: 10,
  description: 'placeholder',
  reviewer: 'test',
  ...over,
});

// ─── parseFindings ────────────────────────────────────────────────────────────

test('parseFindings: extracts standard [SEVERITY] file:line — description', () => {
  const out = parseFindings('code', '[HIGH] src/app.ts:42 — Null deref on user');
  assert.equal(out.length, 1);
  assert.equal(out[0].severity, 'HIGH');
  assert.equal(out[0].file, 'src/app.ts');
  assert.equal(out[0].line, 42);
  assert.equal(out[0].description, 'Null deref on user');
  assert.equal(out[0].reviewer, 'code');
});

test('parseFindings: accepts hyphen and en-dash separators', () => {
  const out = parseFindings('code', [
    '[LOW] x.ts:1 - hyphen',
    '[LOW] x.ts:2 – en dash',
    '[LOW] x.ts:3 — em dash',
  ].join('\n'));
  assert.equal(out.length, 3);
});

test('parseFindings: accepts null/N/A line values', () => {
  const out = parseFindings('code', '[MEDIUM] README.md:N/A — missing heading');
  assert.equal(out.length, 1);
  assert.equal(out[0].line, null);
});

test('parseFindings: skips lines that do not match pattern', () => {
  const out = parseFindings('code', [
    'Some preamble',
    '[HIGH] real.ts:5 — real finding',
    'more prose',
    '## header',
  ].join('\n'));
  assert.equal(out.length, 1);
});

test('parseFindings: rejects unknown severity tokens', () => {
  const out = parseFindings('code', '[CATASTROPHIC] x.ts:1 — nope');
  assert.equal(out.length, 0);
});

// ─── deduplicateFindings ─────────────────────────────────────────────────────

test('dedup: identical findings collapse, mergedFrom lists both reviewers', () => {
  const out = deduplicateFindings([
    f({ reviewer: 'code', description: 'Null deref on user object when undefined' }),
    f({ reviewer: 'security', description: 'Null deref on user object when undefined' }),
  ]);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0].mergedFrom?.sort(), ['code', 'security']);
});

test('dedup: keeps higher severity when merging', () => {
  const out = deduplicateFindings([
    f({ severity: 'LOW', description: 'workflow trigger was removed breaking auto updates' }),
    f({ severity: 'CRITICAL', description: 'workflow trigger removed breaks automatic updates' }),
  ]);
  assert.equal(out.length, 1);
  assert.equal(out[0].severity, 'CRITICAL');
});

test('dedup: different files stay separate even with identical descriptions', () => {
  const out = deduplicateFindings([
    f({ file: 'a.ts', description: 'missing null check on input' }),
    f({ file: 'b.ts', description: 'missing null check on input' }),
  ]);
  assert.equal(out.length, 2);
});

test('dedup: line proximity within ±3 merges; beyond stays separate', () => {
  const close = deduplicateFindings([
    f({ line: 10, description: 'missing null check on input argument value' }),
    f({ line: 12, description: 'missing null check on input argument value' }),
  ]);
  assert.equal(close.length, 1);

  const far = deduplicateFindings([
    f({ line: 10, description: 'missing null check on input argument value' }),
    f({ line: 50, description: 'missing null check on input argument value' }),
  ]);
  assert.equal(far.length, 2);
});

test('dedup: paraphrases of the same issue collapse via Dice', () => {
  const out = deduplicateFindings([
    f({
      description:
        'Once workflow uses only workflow_dispatch the Update Documentation name is misleading users might assume automatic runs',
    }),
    f({
      description:
        'The workflow trigger was changed from automatic push events to manual-only dispatch this reduces automation',
    }),
  ]);
  assert.equal(out.length, 1, 'Real paraphrase pair should merge');
});

test('dedup: genuinely different issues on same line stay separate', () => {
  const out = deduplicateFindings([
    f({
      description:
        'workflow trigger changed to workflow_dispatch without input schema head_commit will be undefined at runtime',
    }),
    f({
      description:
        'workflow now has no automatic triggers creating risk that documentation updates will not happen automatically',
    }),
  ]);
  assert.equal(out.length, 2, 'Runtime-failure and doc-drift are distinct concerns');
});

test('dedup: stemmer catches automatic/automation/automatically', () => {
  const out = deduplicateFindings([
    f({ description: 'The workflow removes automatic triggers breaking continuous delivery' }),
    f({ description: 'The workflow removes automation triggers breaking continuous deliveries' }),
  ]);
  assert.equal(out.length, 1);
});

test('dedup: threshold override via DEDUP_SIMILARITY_THRESHOLD', () => {
  // Paraphrase pair that scores ~0.3 Dice at default threshold 0.25 (merges).
  // Raising threshold to 0.5 should push them apart without requiring entirely
  // disjoint descriptions.
  const pair: Parameters<typeof deduplicateFindings>[0] = [
    f({
      description:
        'Once workflow uses only workflow_dispatch the Update Documentation name is misleading users might assume automatic runs',
    }),
    f({
      description:
        'The workflow trigger was changed from automatic push events to manual-only dispatch this reduces automation',
    }),
  ];
  // Baseline: merges at default threshold.
  assert.equal(deduplicateFindings(pair).length, 1);

  const before = process.env.DEDUP_SIMILARITY_THRESHOLD;
  process.env.DEDUP_SIMILARITY_THRESHOLD = '0.5';
  try {
    assert.equal(
      deduplicateFindings(pair).length,
      2,
      'Paraphrase pair should stay separate at 0.5 threshold',
    );
  } finally {
    if (before === undefined) delete process.env.DEDUP_SIMILARITY_THRESHOLD;
    else process.env.DEDUP_SIMILARITY_THRESHOLD = before;
  }
});

test('dedup: first-time finding gets mergedFrom = [reviewer]', () => {
  const out = deduplicateFindings([
    f({ reviewer: 'code', description: 'single lonely finding with no duplicates anywhere' }),
  ]);
  assert.equal(out.length, 1);
  assert.deepEqual(out[0].mergedFrom, ['code']);
});

// ─── triageFindings ───────────────────────────────────────────────────────────

test('triage: groups findings by severity', () => {
  const out = triageFindings([
    f({ severity: 'CRITICAL' }),
    f({ severity: 'HIGH' }),
    f({ severity: 'HIGH' }),
    f({ severity: 'LOW' }),
    f({ severity: 'NITPICK' }),
  ]);
  assert.equal(out.critical.length, 1);
  assert.equal(out.high.length, 2);
  assert.equal(out.medium.length, 0);
  assert.equal(out.low.length, 1);
  assert.equal(out.nitpick.length, 1);
});

test('reviewer prompts: guard against gold-like style bias', () => {
  const reviewers = selectReviewers('+++ b/src/app.ts\n+const value = 1;\n');
  for (const reviewer of reviewers) {
    const system = reviewer.system.toLowerCase();
    assert.match(system, /correctness/);
    assert.match(system, /gold/);
    assert.match(system, /style\/minimality/);
  }
});
