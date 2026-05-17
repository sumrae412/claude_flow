# Decision — Sonnet-vs-Opus Downgrade for Phases 4b / 5.5

**Date:** 2026-04-24
**Status:** Decided
**Eval plan:** `docs/archive/plans/2026-04-24-sonnet-opus-downgrade-eval.md`
**Phase 6 scope:** explicitly deferred in [PR #50's decision doc](2026-04-24-advisor-tool-verdict.md); asymmetric miss cost on critical security findings makes the savings not worth it.

## Decision

| Phase | Recommendation | Why |
|---|---|---|
| **Phase 4b (architecture stress test)** | **Keep Opus** | Sonnet misses a reasoning step in the adversarial case 10/15 of the time; both judges show a significant quality gap. |
| **Phase 5.5 (mid-implementation escalation)** | **Switch to Sonnet** | Dead tie on quality across both judges; saves $0.026/call. |

Rough per-session savings at 1-2 mid-impl escalations: $0.03-$0.05. Small, but compounds, and the quality data is as flat as evals get at n=15.

## Evidence

15 trials × 3 cases × 2 arms = 90 executor calls, each graded by both Opus-as-judge and Sonnet-as-judge (calibration pass). Raw run: [`evals/advisor_tool_ab/results_sonnet_opus_15trial.json`](../../evals/advisor_tool_ab/results_sonnet_opus_15trial.json). Judge outputs: `results_sonnet_opus_15trial_judge_opus.json`, `results_sonnet_opus_15trial_judge_sonnet.json`.

### Per-case judge scores (mean, n=15)

| Case | Judge | Sonnet | Opus | Gap | Verdict |
|---|---|---|---|---|---|
| phase3 — adversarial constraint trap | Opus | 0.811 | 0.978 | +0.17 Opus | Opus wins |
| phase3 — adversarial constraint trap | Sonnet | 0.889 | 0.989 | +0.10 Opus | Opus wins |
| phase4 — architecture trade-off | Opus | 0.844 | 0.933 | +0.09 Opus | Opus wins |
| phase4 — architecture trade-off | Sonnet | 0.844 | 0.922 | +0.08 Opus | Opus wins |
| phase5 — mid-impl escalation | Opus | **0.989** | **0.989** | 0.00 | **Tie** |
| phase5 — mid-impl escalation | Sonnet | 0.967 | 0.922 | -0.04 Sonnet | Tie (Opus outlier dragged mean — one row scored 0.00) |

### Aggregate + significance (paired bootstrap, 95% CI)

| Judge | Δ judge (Sonnet − Opus) | 95% CI | Significant |
|---|---|---|---|
| Opus-as-judge | −0.085 | [−0.130, −0.041] | **Yes** |
| Sonnet-as-judge | −0.044 | [−0.096, +0.019] | No (CI crosses 0) |

The Opus-judge vs Sonnet-judge disagreement at aggregate is real — Sonnet-as-judge is consistently ~0.05-0.08 kinder to Sonnet-as-executor. We expected this ("judge picks its own style"). The **per-case** picture is robust to it though: both judges rank the arms the same way in every case.

### Critical-miss check (Sonnet missed in ≥50% of trials)

| Case | Criterion | Sonnet miss | Opus miss |
|---|---|---|---|
| phase3 | names logical-corruption / operator-error risk of live replica | **10/15** | 1/15 |
| phase4 | names a quantitative threshold or metric | 10/15 | 3-4/15 |

The phase3 miss is the load-bearing evidence. The adversarial case was explicitly designed to probe second-order reasoning — Option B (continuous WAL to warm replica) satisfies every first-order constraint but has a subtle failure mode (replica inherits logical corruption). **Sonnet misses this in 67% of trials; Opus catches it in 93%.** Both judges agree. This is not a judge-bias artifact.

The phase4 "quantitative threshold" miss is less load-bearing — it's the broken keyword rubric from PR #50 (matches on "ms", "throughput", "QPS" etc., which naturally appear in some responses and not others regardless of reasoning depth). Both arms are dinged on it intermittently.

## Confidence

**High, per case.** n=15 with CI bootstrap on both judges and dual-judge critical-miss convergence. Per-case ranking is consistent under both judges for all three cases. The cases were chosen to represent the phases in question:
- **phase3 adversarial** — stresses the exact reasoning depth Phase 4b needs.
- **phase4 architecture** — direct proxy for Phase 4b stress test (case is literally named that).
- **phase5 mid-impl** — direct proxy for Phase 5.5 escalation.

**Moderate on generalization.** Each case is a single scenario; a different phase-4b problem could shake out differently. But we have three independent signals pointing the same way on phase 4b: aggregate score gap, adversarial reasoning gap, critical-miss rate on the planted trap.

## What we spent

| Item | Spend |
|---|---|
| Pilot (3 cases × 2 arms × 1 trial × 2 judges) | $0.37 |
| 15-trial executor | $1.23 |
| Opus judge on 15-trial | $2.14 |
| Sonnet judge on 15-trial | $0.90 |
| **Total** | **~$4.64** |

Under the $5-10 budget from the plan. The dual-judge calibration added ~$0.90 — cheap and load-bearing; without it we couldn't have ruled out judge bias as the whole signal.

## Surprises

- **Sonnet-judge is kinder to Sonnet-executor on aggregate** (expected), but **not on per-case ranking** (somewhat surprising — we expected the self-favoring bias to flip at least one case). This strengthens the per-case decisions.
- **Phase5 Opus had a zero-score outlier under Sonnet judge** (one of 15 trials graded 0/6). Real bug or parsing glitch, can't tell without re-running. Small enough not to move the per-case verdict but should be noted if phase 5.5 downgrade is revisited.
- **Opus-solo cost ended lower than expected** — $0.041/call vs the $0.060 estimate in the plan. Judge is the dominant cost per call (~$0.021), and Opus judge was cheaper than modeled. Revised savings for phase 5.5 downgrade: $0.026/call not $0.022.

## Implementation

For phase 5.5 (mid-implementation escalation) in claude-flow:
- Find all call sites currently using `claude-opus-4-7` for Phase 5.5.
- Switch default to `claude-sonnet-4-6`.
- No prompt changes needed — Sonnet got tied-quality output with the same prompts.
- Watch the ledger for any uptick in retry rate or rework over the next ~20 Phase 5.5 fires. If retries go up >20%, revert — the per-session savings were $0.03, not $3.

For phase 4b: no change. Keep Opus.

## Out of scope

- **Phase 6 downgrade** — deferred (asymmetric miss cost on critical security findings).
- **Other phases (1-4a, 5)** — not pilot-tested; no cases built for them. Running a separate eval would cost another ~$5 per phase probed.
- **Retry-as-escalation:** if you want hybrid behavior ("try Sonnet, retry with Opus if Sonnet flags uncertainty"), that's a separate design, not a downgrade.
- **Haiku-as-executor for phase 5.5:** the data on phase5 shows Sonnet at 0.99 judge score; Haiku would probably underperform. Not run because the cost delta doesn't justify the eval spend.

## Rollback

If phase 5.5 retry rate goes up or reviewers start flagging Sonnet responses as worse, revert by flipping the model constant back to `claude-opus-4-7`. No schema debt, no cleanup needed.
