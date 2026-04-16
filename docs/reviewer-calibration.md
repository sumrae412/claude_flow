# Reviewer Calibration (LLM-as-Judge Validation)

## Why

LLM reviewers in Phase 6 are judges. A judge with high false-positive rate wastes your time ("signal-to-noise" already in prompt-optimization); a judge with high false-negative rate is worse — you ship bugs while the dashboard shows green. Aggregate scores alone can't distinguish these.

Calibration measures **judge agreement**: does the reviewer's pass/fail verdict match a human's on the same finding? Reviewers below threshold are flagged for demotion or prompt revision.

Source: Hamel Husain's error-analysis workflow — *"You must hand-label some data and compare the LLM judge's scores to the human labels."*

## When to run

- After a reviewer is added (initial calibration).
- Every 30 days (see `judge_calibration.refresh_interval_days` in `reviewer-registry.json`).
- After any prompt change to the reviewer's underlying agent.
- Ad-hoc when you suspect drift (too many dismissed findings, too many escaped bugs).

## Binary verdicts only

Reviewers must emit pass/fail per finding, not a score. A "helpfulness: 4.2 vs 4.7" score is not measurable against human ground truth. Per-finding binary verdicts are.

If a reviewer currently emits a score, wrap it at the threshold you'd actually act on (e.g. `score < 3 → fail`) and calibrate the wrapped binary.

## Protocol

1. **Sample.** From the last N sessions' reviewer findings for the target reviewer, sample `sample_size` findings (default 20).
2. **Label.** Present each finding to a human (usually the user). Human marks `pass` (real issue) or `fail` (false positive / noise).
3. **Compare.** `agreement = count(judge_verdict == human_verdict) / sample_size`.
4. **Decide.**
   - `agreement >= min_agreement` → reviewer is calibrated. Record `last_agreement` and `last_calibrated` in the registry.
   - `agreement < min_agreement` → flag for prompt revision OR demote one cascade_tier. Don't silently continue.

## Registry fields

```json
"calibration": {
  "verdict_type": "binary",
  "min_agreement": 0.75,
  "sample_size": 20,
  "last_calibrated": "2026-04-15",
  "last_agreement": 0.82,
  "note": "optional — override reasons"
}
```

Reviewers without a `calibration` block fall back to `judge_calibration.fallback_min_agreement` (set at the registry top level).

## Script (to implement)

`scripts/calibrate_reviewers.py <reviewer_id>` — samples, prompts user for labels, computes agreement, writes back to the registry. Out of scope for this doc; design in this file, implementation gated behind first actual use.

## Failure mode this prevents

The dashboard-vs-reality gap: automated eval scores look healthy while users hit bugs the judge consistently mislabels as "no issue". Calibration is the only way to know your judge is measuring the right thing.

## Related

- [prompt-optimization SKILL](../skills/prompt-optimization/SKILL.md) — scoring formulas (true_positive_rate, signal_to_noise) that feed into the calibration sample
- [reviewer_registry memory](../../../.claude/projects/-Users-summerrae-claude-flow/memory/reviewer_registry.md) — registry-as-source-of-truth pattern
