# Plan: Soften the adversarial-breaker persona scoring band

**Status:** Drafted 2026-04-16. Pending execution after PR #39 + corpus-rewrite PR merge.
**Estimated effort:** 4-6 hours including iteration.
**Estimated LLM spend:** ~$0.50-1.00 (2-4 calibration cycles at ~$0.20 each).
**Blast radius:** Production. Every Phase 6 review goes through the modified persona.

## Why

The first dry calibration run (PR #39) produced a 49.17% mean agreement — far below the 70% threshold. The headline pattern across 20 cases:

- Clean cases (19, 20): **8% mean agreement**. Sonnet rates textbook-clean code at 2-4 across all criteria.
- Bug cases (01-15): **60% mean agreement**. The planted criterion almost always agrees; adjacent criteria score systematically lower than my human labels.
- Test-file cases (16-18): **22% mean agreement** — addressed by the corpus-rewrite plan.

The planted-criterion agreement (case-01 TOCTOU at concurrency_safety = 1, case-04 SQL injection at input_validation = 1, etc.) shows the persona's *capability* is fine. But the score band is too aggressive: with `score_threshold: 7`, **even clean code gets blocking findings on every criterion**, which is noise, not signal.

Root cause is in the persona file itself:

> 10 = unbreakable, 7 = good enough to ship, 4 = likely breaks under load, 1 = breaks trivially

Sonnet hears "10 = unbreakable" and gives almost nothing 8+ because all production code can theoretically break. Result: scores cluster in 1-4, threshold at 7 means everything blocks.

## What to change

### Persona file — `claude-skills/claude-flow/scripts/adversarial_breaker_persona.txt`

Old block:

```
score (integer 1-10): 10 = unbreakable, 7 = good enough to ship, 4 = likely breaks under load, 1 = breaks trivially
```

Proposed new block:

```
score (integer 1-10), where the gradation is calibrated to ship-readiness, not perfection:
  10 = invariants enforced and tested; provably correct under all stated inputs
  9  = production-grade; would survive load + adverse inputs without intervention
  8  = ship as-is; minor adjacent concerns acceptable for a first pass
  7  = ship-ready but worth noting in PR review (minor noise)
  6  = ship after addressing the break_case (small follow-up)
  5  = the break_case is realistic; fix before merge
  4  = the break_case will fire in production within weeks
  3  = the break_case will fire under normal load; block ship
  2  = catastrophic in production; would page someone
  1  = breaks trivially (test it locally and watch it fail)

Adversarial intent applies to the BREAK_CASE, not the SCORE. Find the worst plausible scenario; then rate based on how realistic that scenario is in production. Code that survives normal production traffic should score 7-9 even if you can construct a contrived failure mode at score 1.

For test-file diffs (paths matching `tests/`, `test_*.py`), input_validation, concurrency_safety, and failure_modes apply only insofar as the test ITSELF is fragile (flaky, races, fixture leaks). Score test files on test_coverage_gaps primarily; mark other criteria as 7+ unless the test infrastructure has its own bugs.
```

The key shift: **adversarial = find the bug, not invent a low score**. The 1-10 scale gets used end-to-end. Threshold 7 starts to mean "ship-ready" instead of "perfect."

### Recorded fixture — `claude_flow/tests/fixtures/adversarial_breaker/recorded_response.json`

The existing recording assumes the old persona. After persona edit:

1. Delete or back up `recorded_response.json` (back up so we can compare the score deltas).
2. Run `make record-adversarial-fixture` (~$0.01) — refreshes the recording against the new persona.
3. **Manually verify** the new recording still has `concurrency_safety <= 2` for case-01 (`expected_scores.json` enforces this in the live test). If it doesn't, the persona softened too much — re-tighten.

### Calibration

After the persona + recording are updated:

1. `make calibrate-adversarial-dry` (~$0.20). Expect mean agreement to land 65-80%. Per-case agreement on clean cases (19, 20) should jump from 8% to 60-100%.
2. If under 70%: iterate on the persona (which criterion is still mismatched?). Probably 1-2 iterations.
3. Once dry-run passes: `make calibrate-adversarial` (~$0.20) to record `last_calibrated` and `last_agreement` in the registry.

### Registry update

Once a real calibration passes, the script auto-writes:

```json
"calibration": {
  ...
  "last_calibrated": "2026-04-XX",
  "last_agreement": 0.7XXX
}
```

That registry change is its own diff; commit alongside the persona + recording changes.

## Cross-repo coordination

Three artifacts in two repos:

| Repo | File | Change |
|---|---|---|
| claude-skills | `claude-flow/scripts/adversarial_breaker_persona.txt` | Persona softening |
| claude_flow | `tests/fixtures/adversarial_breaker/recorded_response.json` | Refreshed recording |
| claude_flow | `reviewer-registry.json` | `last_calibrated` + `last_agreement` populated |

Two PRs — the persona PR (claude-skills) and the recording+calibration PR (claude_flow) must land together. Recording is a recording of the new persona, so claude-skills PR must merge first OR ship as a single coordinated cross-repo merge. The post-`aed5f39` cross-repo persona resolution means tests in claude_flow load the persona via `~/.claude/skills` symlink, so out-of-order merges create temporary calibration drift on main (the recording would target a persona that hasn't shipped yet).

Recommended order:
1. claude-skills persona PR → review → merge.
2. Pull updated persona locally. Run `make record-adversarial-fixture` + `make calibrate-adversarial`.
3. claude_flow PR with the refreshed recording + registry update.

## Steps

1. **Backup current state**: `cp claude-skills/claude-flow/scripts/adversarial_breaker_persona.txt /tmp/persona_pre_softening.txt`. Keep for diff.
2. Edit persona per above.
3. Refresh recording: `make record-adversarial-fixture`. Verify case-01 still scores TOCTOU ≤ 2.
4. Dry calibrate: `make calibrate-adversarial-dry`. Inspect per-case deltas.
5. Iterate persona if needed. Re-record + re-dry-calibrate each iteration.
6. Once dry-run passes (>=70%): `make calibrate-adversarial` to write registry.
7. Open PR pair (claude-skills first, then claude_flow with recording + registry update).

## Verification

- `make record-adversarial-fixture` succeeds and case-01 expected_scores bounds still pass.
- `make calibrate-adversarial-dry` overall agreement >= 0.7.
- Phase 6 dispatch on a known-clean PR (e.g. a typo fix) produces no sub-threshold findings.
- Phase 6 dispatch on the case-01 TOCTOU diff still produces a `concurrency_safety` blocking finding.

## Decision points

**Should we also lower `score_threshold` from 7 to 5 instead of softening the persona?**

No. The threshold should mean "ship-ready", not be calibrated to whatever the model happens to score. Lowering it would:
- Make more code blocking (more noise) at low end.
- Effectively let the model define what "ship-ready" means by its scoring habit.
- Mask the real issue (band miscalibration) instead of fixing it.

**Should we widen the agreement tolerance from ±2 to ±3?**

No. ±2 is generous already (a 4-vs-7 still agrees on ±3 boundary). Widening would hide signal that the persona band is still off after softening.

**Should we accept the current persona and just record `last_agreement: 0.49`?**

Tempting because it's free. But that records a known-broken value as "the calibrated state of the reviewer," which is misleading telemetry. `last_agreement: null` ("never calibrated") is more honest than `last_agreement: 0.49` ("calibrated and broken").

## Risk assessment

| Risk | Mitigation |
|---|---|
| Persona softens too much, misses TOCTOU case-01 | Live test still asserts `must_score_below_threshold: ["concurrency_safety"]`. Test fails before ship. |
| Iteration cost exceeds $1 | Set a budget cap. If 4 iterations don't pass, escalate the persona design as a separate problem. |
| Production reviewer becomes too lenient on real bugs | Drift detection workflow (PR #39's other half) catches if case-01 stops being caught. Weekly cadence. |
| Recording / persona / registry land out of order | Sequence per "Cross-repo coordination" section. Document in PR bodies. |

## Out of scope

- Adding new criteria. The 6 criteria are stable; this plan tunes the score scale, not the dimensions.
- Switching reviewer to a different model. `sonnet` alias is fine; the persona is what's miscalibrated.
- Bulk updating other reviewers' personas. Each scored reviewer needs its own calibration and its own band tuning.
