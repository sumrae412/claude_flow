# Advisor A/B Eval — Token Efficiency + Accuracy Tuning

**Date:** 2026-04-24
**Status:** Draft plan, pending user approval
**Path:** claude-flow LITE/PLAN (no schema, no new endpoints, ~5 files modified)
**Est. total cost to execute:** ~$2 in re-pilots + $12-25 in 20-trial
**Supersedes:** Pilot 2 findings surfaced 3 fixable issues before 20-trial

---

## Context

After Pilot 2 validated the advisor-tool-2026-03-01 pipeline end-to-end (advisor fires
4/4, costs attributed correctly, judge pipeline green), the empirical result was that
`sonnet_advisor_tool` cost MORE per call than `opus_solo` while matching judge quality.
Three root causes were identified:

1. **Advisor verbosity** — outputs 94-2660 tokens per call, 3-4× the Anthropic docs'
   typical range (400-700). A single conciseness line per docs' Best Practices
   section is claimed to cut advisor output 35-45% — partially fixed in the prompt
   but untested.
2. **No prompt caching** — 240 executor calls and 240 judge calls all send near-
   identical system prompts + context. 20-30% of executor cost and 30-40% of judge
   cost is recoverable via `cache_control` breakpoints.
3. **Unverified pricing** — every rate in `scripts/pricing.py` carries `TODO: verify`.
   The 20-trial's ROI pairwise comparisons are only as accurate as those numbers.

Plus a secondary concern for decision quality: **ceiling effects** in the rubrics
(all arms score ≥0.95), leaving no statistical headroom for the 20-trial to
differentiate arms.

## Requirements

1. Reduce executor input-token cost on the 20-trial by ≥20% via prompt caching.
2. Reduce judge input-token cost on the 20-trial by ≥30% via prompt caching.
3. Eliminate `TODO: verify` markers on Anthropic rates in `scripts/pricing.py`.
4. Create rubric headroom: at least one arm should be able to score <0.6 on at least
   one case, so the 20-trial can produce statistically significant arm differences.
5. Preserve the existing pipeline (dry-run tests, judge, ledger, run_ab CLI flags, stat_analysis).
6. All 165 existing tests must still pass.

Acceptance criteria for graduating to 20-trial:
- Re-pilot shows `cache_read_input_tokens > 0` on the 2nd+ (case, arm) call
- Re-pilot `sonnet_advisor_tool` mean cost drops by ≥25% vs Pilot 2's $0.169/call
- Dry-run of the hardened rubrics shows `rubric_score` spread across arms (not
  uniformly 1.0)
- `make advisor-ab-pilot` exits 0, all 12 rows `success: true`, advisor fires 4/4

## Plan

### Step 1 — Verify Anthropic pricing rates

| field | value |
|---|---|
| id | 1 |
| files | `scripts/pricing.py` |
| type | `shared_prerequisite` |
| depends_on | — |
| status | pending |

Open https://www.anthropic.com/pricing in a browser. For each of
`claude-opus-4-7`, `claude-sonnet-4-6`, `claude-haiku-4-5-20251001`, confirm the
input and output rates match the `PRICING` table. Update any that differ. Remove
the `TODO: verify` comments on Anthropic rows only (leave OpenAI/DeepSeek marked
since we don't need them for this eval, but they're still unverified).

**Test requirement:** After update, run `/opt/anaconda3/bin/pytest
tests/test_pricing.py -q` — should stay green. If rates changed, commit with
`fix(pricing): update Anthropic rates against 2026-04-24 console snapshot`.

**Kill criterion:** If Anthropic rates have moved by >30% from the current
snapshot, stop and reassess the eval budget — the cost estimates in this plan may
be materially off.

---

### Step 2 — Add prompt caching to executor arms

| field | value |
|---|---|
| id | 2 |
| files | `evals/advisor_tool_ab/run_ab.py` |
| type | `value_unit` |
| depends_on | `{step: 1, type: knowledge}` — need accurate pricing to verify cost delta post-cache |
| status | pending |

Currently [run_ab.py:169-176](../../evals/advisor_tool_ab/run_ab.py) sends the
prompt as a single content block:
```python
"messages": [{"role": "user", "content": prompt}]
```

Restructure to use a system message + user content blocks with a `cache_control`
breakpoint after the case context (before the question). Anthropic's docs: a
cache breakpoint 5 minutes before the next identical prefix triggers a cache hit
at ~10% of the input rate.

```python
# Pseudocode — the system + instructions + case context are the cacheable prefix.
create_kwargs["system"] = [
    {"type": "text", "text": prompt_system_part,
     "cache_control": {"type": "ephemeral"}}
]
create_kwargs["messages"] = [{"role": "user", "content": [
    {"type": "text", "text": f"CONTEXT:\n{case['context']}\n\n"
                              f"QUESTION:\n{case['question']}"},
]}]
```

This requires splitting `sonnet_solo.txt` and `sonnet_with_advisor_tool.txt` into
a system preamble (cacheable) + a context/question suffix (per-call). Minimal
approach: keep `.txt` files as-is, split at the `CONTEXT:` marker in code.

**Test requirement:**
- Update `tests/test_ledger_integrations.py` mock to include
  `cache_read_input_tokens` and `cache_creation_input_tokens` fields in fake
  Anthropic responses.
- Add a live-path assertion in an integration test verifying `cache_read_input_tokens >
  0` on a 2nd identical call (new test in `evals/advisor_tool_ab/test_run_ab.py`).
  Can mock the Anthropic client.
- `pytest tests/ evals/ -q` stays green.

**Kill criterion:** If the `cache_control` shape is rejected by the API (400),
fall back to no caching and accept 25-35% higher 20-trial cost — do not block
the overall plan.

---

### Step 3 — Add prompt caching to the judge

| field | value |
|---|---|
| id | 3 |
| files | `scripts/llm_judge.py` |
| type | `value_unit` |
| depends_on | `{step: 1, type: knowledge}` |
| status | pending |

Same pattern as Step 2, applied to `judge_response()`. Currently
[llm_judge.py:227-232](../../scripts/llm_judge.py) sends:
```python
client.messages.create(
    system=JUDGE_SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_prompt}],
)
```

The `JUDGE_SYSTEM_PROMPT` is fixed across all 240 judge calls — perfect cache
candidate. The `user_prompt` (`_build_user_prompt`) also contains rubric
criteria + context + question which repeat across trials of the same case; only
the `response_text` differs. Two cache breakpoints:

1. After `JUDGE_SYSTEM_PROMPT` — always the same, caches across all calls
2. After `CONTEXT: … QUESTION: …` in user content — caches across all trials of
   one case (read by 19 of 20 trials)

**Test requirement:**
- Update `tests/test_llm_judge.py::_fake_anthropic_response` to include cache
  fields.
- Assert that the second call within a simulated "same case, different trial"
  scenario triggers `cache_read_input_tokens > 0`.
- All 9 existing judge tests still pass.

**Kill criterion:** Same as Step 2.

---

### Step 4 — Harden rubrics for signal-to-noise

| field | value |
|---|---|
| id | 4 |
| files | `evals/advisor_tool_ab/cases/*.json` (4 files) |
| type | `value_unit` |
| depends_on | — (independent of caching work) |
| status | pending |

For each case, add 2 discriminator criteria that push the rubric from "any
reasonable answer passes" to "only substantive architectural analysis passes":

- `names a quantitative threshold` — keyword lists require numeric or
  comparative language (e.g. for phase4: `"keywords": ["ms", "latency",
  "throughput", "QPS", "worker", "fan-out"]`)
- `acknowledges a counter-argument` — keywords capture qualifier language
  (`however`, `but`, `trade-off`, `downside`, `risk`, `unless`)

Keep the existing 4 simpler criteria; add the 2 new ones bringing each case to 6
criteria. This raises the ceiling — a perfect-looking but shallow answer that
would score 1.0 today should now score 4/6 ≈ 0.67.

**Test requirement:**
- Re-run dry-run: `python evals/advisor_tool_ab/run_ab.py --cases-dir
  evals/advisor_tool_ab/cases --out /tmp/r.json --dry-run` must succeed.
- Manual: pick one of Pilot 2's actual `response_text` values (stored in
  `results_pilot.json`) and re-score against the new rubric. It should land in
  [0.5, 0.85] range, not the 0.95+ we saw. If it still scores ≥0.95, the rubric
  isn't strict enough; iterate.

**Kill criterion:** If re-scoring Pilot 2 responses against the new rubric drops
every arm below 0.3, the rubric is too hard — re-tune before graduating. This is
the only step where "too hard" is a real risk.

---

### Step 5 — Update integration tests for cache fields

| field | value |
|---|---|
| id | 5 |
| files | `tests/test_ledger_integrations.py`, `tests/test_llm_judge.py`, `evals/advisor_tool_ab/test_run_ab.py` |
| type | `shared_prerequisite` |
| depends_on | `{step: 2, type: build}`, `{step: 3, type: build}` |
| status | pending |

Mocks currently return a bare `usage` mock with only `input_tokens` and
`output_tokens`. With caching, Anthropic responses also include:
- `cache_read_input_tokens: int`
- `cache_creation_input_tokens: int`

Extend `_fake_anthropic_response` helpers in all three test files to accept these
as kwargs, defaulting to 0. Add a dedicated test per Step 2 and Step 3 that
asserts the cache fields are preserved in ledger rows (via `extras`).

**Test requirement:** `pytest tests/ evals/
--ignore=tests/test_adversarial_breaker_live.py -q` shows 165+N passing, 0
failing.

**Kill criterion:** None — this step is tight, mechanical.

---

### Step 6 — Re-pilot with all changes (gate to 20-trial)

| field | value |
|---|---|
| id | 6 |
| files | `evals/advisor_tool_ab/results_pilot.json` (regenerated) |
| type | `shared_prerequisite` |
| depends_on | `{step: 1, type: knowledge}`, `{step: 2, type: build}`, `{step: 3, type: build}`, `{step: 4, type: build}`, `{step: 5, type: build}` |
| status | pending |

Run `RUN_LIVE_LLM=1 make advisor-ab-pilot`. Cost ~$1-1.50 (expected to land
lower than Pilot 2's $1.45 because of caching on judge — but cache needs a warm
call to kick in, so first call pays full rate).

**Test requirement — gate to graduating:**
- All 12 rows `success: true`, advisor fires 4/4 on `sonnet_advisor_tool`
- Ledger rows for 2nd+ judge call show `cache_read_input_tokens > 0`
- `sonnet_advisor_tool` mean cost ≤ $0.127/call (25% below Pilot 2's $0.169)
- Rubric scores are NOT uniformly 1.0 across all 12 rows (signal-to-noise fixed)
- `make` exits 0

**Kill criterion:** If cache_read is 0 everywhere, either Step 2 or Step 3
implementation is wrong — do not graduate; diagnose first. If rubric scores are
still uniformly 1.0, the hardened rubrics weren't hard enough — revisit Step 4
before spending 20-trial money.

---

### Step 7 — Graduate to 20-trial + statistical analysis

| field | value |
|---|---|
| id | 7 |
| files | `evals/advisor_tool_ab/results_20trial.json`, `evals/advisor_tool_ab/analysis_20trial.md` |
| type | `value_unit` |
| depends_on | `{step: 6, type: data}` |
| status | pending |

Gated behind Step 6 passing. The Makefile target `advisor-ab-20trial` already
enforces `results_pilot.json` exists as a prerequisite. Run:

```
RUN_LIVE_LLM=1 make advisor-ab-20trial
```

This fires 240 A/B calls + 240 judge calls + generates `analysis_20trial.md`
via `stat_analysis.py`.

Expected cost with all improvements: **$12-25** (down from $20-40 estimate).
- Cache on executor saves ~25% of input tokens
- Cache on judge saves ~35% of input tokens
- Tightened advisor prompt saves ~40% of advisor output tokens

**Test requirement:**
- `analysis_20trial.md` contains per-arm means with 95% CIs on rubric_score,
  judge_score, cost_usd, latency_s
- Pairwise comparisons with `significant_at_alpha` flags
- If `sonnet_advisor_tool` vs `opus_solo` pairwise cost diff CI excludes 0 AND
  judge diff CI contains 0, the decision is clear: pick whichever is cheaper.

**Kill criterion:** If the 20-trial surfaces new bugs (ratelimits, schema drift),
rollback = stop spending and diagnose. Don't keep re-running on hope.

---

## Execution order and parallelism

Phase 5 dispatch strategy per claude-flow conventions:

**Sequential (data deps):**
1. Step 1 (pricing verify) — blocks cost math correctness downstream
2. Steps 2, 3, 4 can run in **parallel** (no deps on each other)
3. Step 5 (test updates) — after 2, 3 land
4. Step 6 (re-pilot) — after 1-5 all green
5. Step 7 (20-trial) — after 6 gates pass

**Parallel fan-out opportunity:** Steps 2, 3, 4 touch independent files.
Appropriate for 3 parallel subagent dispatches OR one operator batching all
three in a single editing turn.

## Rollback strategy

Each step is a single commit. If Step 6 re-pilot fails cleanly, the last green
state is the previous commit. `git reset --hard HEAD~1` per step is safe. All
changes are in the worktree; no upstream pushes until 20-trial passes.

## Out of scope (explicitly deferred)

- OpenAI / DeepSeek pricing verification (not used in this eval)
- Retry logic for transient Anthropic errors (fix if 20-trial actually hits one)
- Temperature tuning (variance-averaged across 20 trials)
- Judge calibration against human-labeled ground truth (proper eval
  infrastructure, overkill here)
- Advisor-tool conversation-level caching (`caching` field on tool def) — docs
  say breakeven at ≥3 advisor calls per request; our structure is 1 call per
  request, so no benefit
- Scheduling the 20-trial as a recurring cron (Option 3 from earlier — needs one
  successful manual run first anyway)
