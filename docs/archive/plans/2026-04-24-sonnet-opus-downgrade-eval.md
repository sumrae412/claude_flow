# Sonnet-vs-Opus Downgrade Eval — Phases 4b / 5.5

**Date:** 2026-04-24
**Status:** Draft plan, auto-executing
**Path:** claude-flow LITE (no schema, ~3 files modified, reuses advisor-tool harness)
**Est. total cost:** ~$5-6
**Precedes:** a decision doc at `docs/decisions/2026-04-DD-sonnet-vs-opus-phase-downgrade.md`

---

## Context

PR #50's decision doc ruled out the `advisor_20260301` server-side tool for claude-flow phases 4b / 5.5 / 6. Alongside that result, `sonnet_solo` (judge=0.93) trailed `opus_solo` (judge=1.00) by 0.07 at 2.5× lower cost. n=1 per case; not decision-grade.

Current Opus pricing is $5/$25 per MTok (66% drop from March). Per-call cost delta between arms: Opus $0.060 vs Sonnet $0.038 = **$0.022/call**. A claude-flow session hits 2-3 escalation calls = $0.04-0.07 saved per session. Real question: **does Sonnet miss critical reasoning steps often enough to cost more than $0.02 in downstream rework?**

Phase 6 excluded — asymmetric cost of a missed critical security finding swamps savings. Only 4b and 5.5 in scope.

## Requirements

1. Resolve the Sonnet-vs-Opus judge-score gap with decision-grade confidence at n=15 trials per (case, arm).
2. Calibrate against Opus-as-judge bias: run every response through both Opus and Sonnet judges; surface any ranking divergence in the decision doc.
3. Cases must have real reasoning headroom — drop ceiling-saturated `phase2_gap_identification`, add one adversarial-depth case where first-order reasoning gives the wrong answer.
4. Total spend ≤$8 across pilot + 15-trial + dual judge.
5. Existing 167 tests must still pass.

Acceptance criteria for recommending Sonnet downgrade per phase:
- Sonnet case-level judge mean ≥ 0.95 (either judge)
- No case's Sonnet 95% CI lower bound below 0.85
- Dual-judge agreement: same arm winner (or tie) under both judges
- No Sonnet response missing a criterion that every Opus response covers (critical-miss check)

## Plan

### Step 1 — Add adversarial case + harness flags

| field | value |
|---|---|
| id | 1 |
| files | `evals/advisor_tool_ab/cases/phase3_constraint_interaction_trap.json`, `evals/advisor_tool_ab/run_ab.py`, `evals/advisor_tool_ab/judge.py` |
| type | `value_unit` |
| depends_on | — |
| status | pending |

- New case `phase3_constraint_interaction_trap.json`: HIPAA-compliant DB backup strategy with 5 constraints + 3 options, where the "obvious" Option B (continuous WAL to warm replica) has a subtle logical-corruption blind spot. Tests reasoning depth Opus is theorized to beat Sonnet on.
- `run_ab.py`: add `--arms` flag (comma-separated filter against `ARMS`).
- `judge.py`: add `--judge-model` flag; thread through `judge_results()` → `judge_response(judge_model=...)`.

**Test requirement:** `pytest tests/ evals/ --ignore=tests/test_adversarial_breaker_live.py -q` stays green. Dry-run regenerates with `--arms sonnet_solo,opus_solo` producing 2-arm output.

**Kill criterion:** if the adversarial case can't be designed to discriminate (both models score ≥0.95 on the pilot), revisit case design before 15-trial.

### Step 2 — Pilot (3 cases × 2 arms × 1 trial × 2 judges)

| field | value |
|---|---|
| id | 2 |
| files | `evals/advisor_tool_ab/results_sonnet_opus_pilot.json` |
| type | `value_unit` |
| depends_on | Step 1 |

Cases: `phase3_constraint_interaction_trap`, `phase4_architecture_tradeoff`, `phase5_mid_impl_architectural_concern`.

Commands:
```
RUN_LIVE_LLM=1 python evals/advisor_tool_ab/run_ab.py \
  --arms sonnet_solo,opus_solo --trials 1 \
  --cases-dir <scoped_cases_dir> \
  --out evals/advisor_tool_ab/results_sonnet_opus_pilot.json \
  --session-id sonnet_opus_pilot_$(date +%Y%m%d_%H%M%S)

python evals/advisor_tool_ab/judge.py \
  --results evals/advisor_tool_ab/results_sonnet_opus_pilot.json \
  --cases-dir <scoped_cases_dir> \
  --out evals/advisor_tool_ab/results_sonnet_opus_pilot_judge_opus.json \
  --judge-model claude-opus-4-7

python evals/advisor_tool_ab/judge.py \
  --results evals/advisor_tool_ab/results_sonnet_opus_pilot.json \
  --cases-dir <scoped_cases_dir> \
  --out evals/advisor_tool_ab/results_sonnet_opus_pilot_judge_sonnet.json \
  --judge-model claude-sonnet-4-6
```

Expected cost: ~$0.50.

**Kill criterion:** all three cases score 1.0 across both arms under both judges → rubrics/cases lack discrimination, do not graduate to 15-trial. Adversarial case fails to differentiate → revisit Step 1 design.

### Step 3 — 15-trial full run

| field | value |
|---|---|
| id | 3 |
| files | `evals/advisor_tool_ab/results_sonnet_opus_20260424.json` + dual-judge outputs |
| type | `value_unit` |
| depends_on | Step 2 pass |

Same commands with `--trials 15`. Expected cost: ~$5.

3 cases × 2 arms × 15 trials = 90 executor calls. 90 × 2 judges = 180 judge calls.

Per-call cost estimate (post-caching-revert, all rates verified 2026-04-24):
- sonnet_solo exec: 45 × $0.015 ≈ $0.68
- opus_solo exec: 45 × $0.037 ≈ $1.67
- Opus judge: 90 × $0.023 ≈ $2.07
- Sonnet judge: 90 × $0.010 ≈ $0.90
- **Total ≈ $5.30**

### Step 4 — Stat analysis + decision doc

| field | value |
|---|---|
| id | 4 |
| files | `docs/decisions/2026-04-DD-sonnet-vs-opus-phase-downgrade.md` |
| depends_on | Step 3 |

Run `stat_analysis.py` on both judge outputs. Surface:
- Per-arm case-level means with 95% CIs (bootstrap)
- Paired comparisons with `significant_at_alpha`
- Dual-judge agreement table (does ranking flip between Opus-judge and Sonnet-judge?)
- Critical-miss check: any criterion that 100% of Opus responses hit but <80% of Sonnet responses hit

Decision doc phrasing per phase (case maps to phase):
- phase3 ↔ plan-level escalation? (not a current phase — treat as stress test)
- phase4 ↔ Phase 4b (architecture stress test)
- phase5 ↔ Phase 5.5 (mid-impl escalation)

For each, state: recommend Sonnet / keep Opus / inconclusive. Explicitly factor in judge bias and the $0.022/call savings at 2-3 calls per session.

## Rollback

Each step is a single commit (or two for Step 1: case + flags). Steps 2-3 produce JSON artifacts only. Force-delete branch if we abandon — no migration debt.

## Out of scope

- Phase 6 downgrade — explicitly deferred per earlier decision; asymmetric miss cost.
- Sonnet 4.6 vs Sonnet 4.5 — only latest in play.
- Haiku-as-judge — cost too low to matter for the bias question at this N.
- Extrapolating to phases outside 4b / 5.5 — those weren't pilot-tested and cases weren't built for them.
