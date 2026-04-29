# Advisor-Tool A/B Eval

**Status:** DRY-RUN SCAFFOLDING ONLY — live eval deferred.

## Purpose

Decide whether Anthropic's server-side `advisor_20260301` tool should replace
*any* of claude-flow's current manual advisor calls (Phase 4b stress tests,
Phase 5.5 escalation, Phase 6 iter-2 retries, Phase 2 gap identification).

The eval compares three arms across four representative cases:

| Arm                   | Model  | Extra tools            | Role in eval                                    |
|-----------------------|--------|------------------------|-------------------------------------------------|
| `sonnet_solo`         | Sonnet | none                   | Baseline. "Do we need anything more than this?" |
| `sonnet_advisor_tool` | Sonnet | `advisor_20260301`     | Treatment. "Does the tool close the gap?"       |
| `opus_solo`           | Opus   | none                   | Ceiling. "What's the best we could do?"         |

If `sonnet_advisor_tool` rubric-matches `opus_solo` at materially lower cost,
the tool replaces manual Opus advisor calls in the relevant phases.

## Cases

Four cases under `cases/`, each drawn from a claude-flow phase that currently
invokes an Opus advisor or might benefit from one:

| Case file                                      | Phase analog                              |
|------------------------------------------------|-------------------------------------------|
| `phase2_gap_identification.json`               | Phase 2 research gap identification *     |
| `phase4_architecture_tradeoff.json`            | Phase 4b architecture stress test         |
| `phase5_mid_impl_architectural_concern.json`   | Phase 5.5 mid-implementation escalation   |
| `phase6_critical_finding_fix.json`             | Phase 6 iter-2 retry on critical finding  |

\* Included as a *should-not-benefit* anchor — guards against Opus-bias in the
final recommendation.

Each case has a `rubric` of ~4 criteria scored by substring match (see
`score_rubric` in `run_ab.py`). Rubrics are intentionally simple so the
eval is cheap to re-run when prompts change.

## Rubric schema

Each rubric item is a dict:

```json
{"criterion": "short human-readable label", "keywords": ["kw1", "kw2", "..."]}
```

The score for a case is the fraction of rubric items where **any** keyword
appears as a case-insensitive substring in the model's response. `score_rubric`
**raises `ValueError`** on malformed items (e.g. bare strings) so regressions
don't silently produce zeros.

Note: this diverges from the plan's (Step 4) simpler list-of-strings schema;
the dict shape is the shipped contract.

## Running the dry run

The dry-run path produces a structurally-valid results JSON with zeroed
metrics and `dry_run: true` on every row. It makes no network calls and does
not require the `anthropic` SDK.

```bash
cd /Users/summerrae/claude_code/claude_flow
pytest evals/advisor_tool_ab/test_run_ab.py -v
```

Or invoke the runner directly:

```bash
python evals/advisor_tool_ab/run_ab.py \
  --cases-dir evals/advisor_tool_ab/cases \
  --out /tmp/results.json \
  --dry-run
```

## Running the live eval (deferred — future work)

When ready to run the real eval:

1. `pip install anthropic` (the runner lazily imports it inside the live path).
2. Export `ANTHROPIC_API_KEY`.
3. Drop the `--dry-run` flag:
   ```bash
   python evals/advisor_tool_ab/run_ab.py \
     --cases-dir evals/advisor_tool_ab/cases \
     --out evals/advisor_tool_ab/results_live.json
   ```

### Expected cost

Rough estimate: ~$1–2 for one full pass (4 cases × 3 arms × ~2K output
tokens, with Opus dominating the bill). Re-runs for prompt iteration are
cheap enough that this can be budgeted as routine.

### Expected outputs

`results_live.json` has the same schema as the dry-run output, plus:

* `rubric_score` — non-zero, in `[0.0, 1.0]`, from substring-match scoring.
* `cost_usd` — computed inline by `attribute_cost()` from the `usage` field
  (token counts) and the module-level `PRICING` table. The table ships with
  zeroed rates and must be populated with current Anthropic pricing before
  the first live run; until then `cost_usd` stays 0.0 to avoid misleading
  totals. See the TODOs section.
* `latency_s` — measured wall-clock per-call.
* `usage` — `{"input_tokens": int | None, "output_tokens": int | None}`; `null`
  on dry-run rows.
* `response_text` — full model response (kept for manual inspection of why
  a case passed or failed its rubric). Empty string on dry-run rows.
* `invoked_advisor` — bool; whether the advisor tool actually fired during the
  call. Always `False` for non-advisor arms and for dry-run rows.

### Known TODOs for the live path

The live path is **scaffolding, not production**. Before running for real,
confirm — in roughly this order, these are the first things a future session
should populate:

* **Populate `PRICING` in `run_ab.py`** with current USD-per-million-token
  rates for `MODEL_SONNET` and `MODEL_OPUS` from the Anthropic pricing page.
  Until this is populated, `cost_usd` stays 0.0 on every row and the
  cost-attribution analysis is a no-op.
* **Verify the advisor-tool shape.** Current best-effort placeholder is
  `{"type": "advisor_20260301", "name": "advisor", "model": MODEL_OPUS, "max_uses": 2}`
  with an `anthropic-beta: advisor-tool-2026-03-01` header. The live path
  prints a one-time `WARN` on stderr when the advisor arm is first dispatched;
  cross-check against current Anthropic docs before interpreting results.
* **Model IDs** (`MODEL_SONNET`, `MODEL_OPUS`) are current. Source of truth:
  https://docs.anthropic.com/en/docs/about-claude/models.
* **Max-tokens budget per call** (currently 2048) is sufficient for the rubric
  criteria that depend on the model elaborating on trade-offs.
* **No retry/backoff** — if rate-limited, re-run from scratch. Adding
  exponential backoff is an explicit out-of-scope follow-up.

## Judge Bias Guardrails

The LLM judge prompt explicitly prioritizes substantive correctness and
completeness over gold-like surface traits. This is intentional: clean,
minimal, familiar-looking answers can outscore longer answers when the judge is
under-specified, even when the longer answer is the one that actually satisfies
the benchmark criterion.

When adding or editing eval cases:

* Write rubric criteria around observable task success, risk coverage, and
  required reasoning, not answer style.
* Treat concision, polish, minimality, and formatting as tiebreakers only.
* Include at least one case where a plausible but incomplete "clean" answer
  should lose to a more complete answer, so judge drift is visible.
* Prefer dual-judge or human spot checks when a result is used to change model
  routing or phase ownership.

## Decision criteria

The live eval is run once prompts and rubrics are stable. The decision doc
(written after the live run) answers:

* Which phases (if any) should switch to the advisor tool?
* Which should stay on manual Opus calls?
* Which should downshift to Sonnet solo (because the gap turned out to be
  smaller than assumed)?

## Related

* Plan: `docs/plans/2026-04-17-blog-insights-integration.md` (Task 1).
* Memory: `Pattern: Cross-Model Retry Diagnosis` — Phase 5 iter-3 cross-model
  retry, which this eval may inform.
