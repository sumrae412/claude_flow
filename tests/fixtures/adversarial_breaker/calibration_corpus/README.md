# Adversarial-breaker calibration corpus

20 labeled diffs used by `scripts/calibrate_adversarial_breaker.py` to compute reviewer-vs-human agreement.

## Layout

Each case is a directory:

- `diff.patch` — the planted-bug input fed to the live reviewer
- `expected.json` — per-criterion human-labeled scores (1-10) plus rationale

## Coverage

- 3 cases per scored criterion (18 total)
- 2 clean cases (well-implemented code; reviewer should score 7-9 across the board, NOT all 10s)

All 20 cases diff production code, not test files. Cases targeting `test_coverage_gaps` (16-18) plant production-code changes with missing/mis-shaped test coverage — they are not "tests of tests". The persona scores test-file diffs differently from production-code diffs; keeping the corpus production-only avoids conflating those two calibration signals.

## Scoring discipline

Human scores were assigned BEFORE running the live LLM, scoring each case honestly per my judgment of bug severity. Targeted criterion: 1-4. Adjacent issues: 4-6. Truly orthogonal: 7-9. Clean cases: 7-9.

## Agreement formula

Per-case agreement = (count of criteria where |judge - human| <= 2) / 6.
Overall agreement = mean of per-case agreements.

Pass threshold (from `reviewer-registry.json`): >= 0.7.
