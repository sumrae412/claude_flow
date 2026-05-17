# Evaluation Metrics — Ledger + LLM-as-Judge

**Applied in:** [Advisor-Tool A/B Eval Verdict](decisions/2026-04-24-advisor-tool-verdict.md) (worked example using these metrics)

How claude-flow measures latency, cost, and ROI across eval runs, and how we
grade model outputs against ground truth without a human-in-the-loop rubric
inspection step.

## Two pieces

| Piece | File | Purpose |
|-------|------|---------|
| Invocation ledger | `scripts/ledger.py` | One JSONL row per LLM call: tokens, wall time, cost, optional score |
| Pricing table | `scripts/pricing.py` | USD-per-MTok rates; single source of truth |
| LLM-as-judge | `scripts/llm_judge.py` | Opus grades responses against a rubric; logs to the ledger |
| A/B judge runner | `evals/advisor_tool_ab/judge.py` | Applies the judge to `run_ab.py` output |

## Ledger schema

Default location: `memory/episodic/invocations.jsonl`. Append-only, one JSON
object per line. Override via `CLAUDE_FLOW_DIR` env var or the
`ledger_path=` kwarg.

| Field | Type | Notes |
|-------|------|-------|
| `ts` | ISO-8601 UTC string | |
| `session_id` | str or null | Correlation id (eval run, phase id, ...) |
| `caller` | str | Free-form label (`advisor_ab`, `llm_judge`, ...) |
| `model` | str | Must match a key in `pricing.PRICING` to get non-zero cost |
| `arm` | str or null | Eval-arm label (`opus_solo`, ...) |
| `case` | str or null | Eval-case name |
| `input_tokens` / `output_tokens` | int or null | |
| `wall_time_s` | float | Monotonic seconds, 4 decimals |
| `cost_usd` | float | Computed via `pricing.compute_cost` unless caller overrides |
| `success` | bool | `false` for failed/errored calls |
| `error` | str or null | Short description on failure |
| `score` | float or null | Caller-attached quality score for ROI math |
| `extras` | dict | Caller-specific fields (e.g. `invoked_advisor`) |

## Logging a call

```python
from ledger import log_invocation

log_invocation(
    caller="advisor_ab",
    model="claude-opus-4-7",
    wall_time_s=elapsed,
    input_tokens=usage.input_tokens,
    output_tokens=usage.output_tokens,
    session_id="advisor_ab_2026-04-22_run1",
    arm="opus_solo",
    case=case["name"],
    score=rubric_score,
)
```

## Summarizing

```bash
# All rows, grouped by (caller, model, arm).
python scripts/ledger.py summarize

# One eval run.
python scripts/ledger.py summarize --session-id advisor_ab_2026-04-22_run1

# Last 20 rows (debug).
python scripts/ledger.py tail -n 20
```

`summarize` output per group:

- `count`, `successes`, `failures`
- `total_cost_usd`, `mean_cost_usd`
- `total_wall_time_s`, `mean_wall_time_s`
- `total_input_tokens`, `total_output_tokens`
- `mean_score` — if callers attached scores
- `roi_score_per_usd` — mean score ÷ mean cost, the arm-comparison number

## LLM-as-judge

The old rubric scorer was substring-match (see `run_ab.py::score_rubric`) —
fast, cheap, but coarse. It also leaned on humans to read `response_text`
when a row failed unexpectedly, to tell noise from real misses. The judge
pipeline replaces that human loop with a structured Opus call.

### How it scores

1. For each row, `judge_response()` builds a prompt containing the rubric
   criteria, the case context/question, and the response under review.
2. Opus (`claude-opus-4-7` by default) returns a JSON object:
   ```json
   {
     "per_criterion": [
       {"criterion": "...", "passed": true, "rationale": "..."},
       ...
     ]
   }
   ```
3. The score is `sum(passed) / len(rubric)`.
4. Every call logs to the ledger as `caller="llm_judge"`.

### Running it on A/B results

```bash
# Live run — requires ANTHROPIC_API_KEY.
python evals/advisor_tool_ab/run_ab.py \
    --cases-dir evals/advisor_tool_ab/cases \
    --out evals/advisor_tool_ab/results_live.json \
    --session-id advisor_ab_2026-04-22_run1

# Judge pass — reads results_live.json, writes results_judged.json.
python evals/advisor_tool_ab/judge.py \
    --results evals/advisor_tool_ab/results_live.json \
    --cases-dir evals/advisor_tool_ab/cases \
    --out evals/advisor_tool_ab/results_judged.json \
    --session-id advisor_ab_2026-04-22_run1
```

`results_judged.json` extends `results.json` with:

- `per_case[*].judge` — per-row `{score, per_criterion, judge_model, cost_usd, wall_time_s}`
- `per_case[*].judge_agrees_with_substring` — bool within a 0.01 tolerance
- `judge_aggregate` — per-arm mean judge score + judge cost
- `judge_disagreements` — rows where |substring − judge| ≥ 0.25; the ones
  that would have needed human inspection under the old flow

### Why both scorers for now

We keep the substring scorer alongside the judge for at least one full run
so we can measure agreement and catch judge regressions. When
`judge_disagreements` is small and explainable, the substring rubric can
retire.

## Before a live run — verify

- [ ] `scripts/pricing.py` — every model you'll call has a current row. All
  shipped rates are marked `TODO: verify`; refresh them against the
  provider's pricing page.
- [ ] `ANTHROPIC_API_KEY` exported.
- [ ] `pip install anthropic` (`run_ab.py` and `llm_judge.py` both import
  lazily).
- [ ] Choose a `--session-id` that identifies the run — the ledger groups on
  it and ROI reporting depends on it.
