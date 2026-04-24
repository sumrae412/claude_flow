# Decision — Advisor-Tool A/B Eval Verdict

**Date:** 2026-04-24
**Status:** Decided
**Supersedes:** `docs/plans/2026-04-24-advisor-ab-eval-tuning.md` Step 7 (20-trial run)

## Decision

**Do not wire the `advisor_20260301` server-side tool into claude-flow Phases 4b / 5.5 / 6.**

Use `opus_solo` (Opus with no extra tools) for escalated architecture / review / mid-implementation calls. `opus_solo` beats `sonnet_advisor_tool` on both cost and quality at current pricing.

## Evidence

Single-trial pilot (n=1 per case × 3 arms × 4 cases = 12 rows), run 2026-04-24 with pricing verified against `claude.com/pricing` (see [`scripts/pricing.py`](../../scripts/pricing.py)).

| Arm                   | Mean exec cost | Mean judge cost | Mean rubric | **Mean judge score** | Mean latency |
|-----------------------|---------------:|----------------:|------------:|---------------------:|-------------:|
| `opus_solo`           |     **$0.0366** |         $0.0235 |        1.00 |             **1.00** |       26.3 s |
| `sonnet_advisor_tool` |         $0.0854 |         $0.0213 |        0.96 |                 0.89 |       46.2 s |
| `sonnet_solo`         |         $0.0149 |         $0.0228 |        1.00 |                 0.93 |       22.1 s |

Pilot artifacts: [`evals/advisor_tool_ab/results_pilot.json`](../../evals/advisor_tool_ab/results_pilot.json), ledger rows under `session_id=advisor_ab_pilot_20260424_134335`.

### Why `opus_solo` wins

- **Cost:** $0.037/call vs $0.085/call — **2.3× cheaper** than `sonnet_advisor_tool`.
- **Quality:** perfect judge score (1.00) vs 0.89 for `sonnet_advisor_tool`.
- **Latency:** 26 s vs 46 s — about half.

The advisor tool's original premise was "Sonnet-speed with Opus-quality escalation on demand." At 2026-03 pricing (Opus $15/$75), that trade-off was plausible. At 2026-04 pricing (Opus $5/$25, a 66% drop — see below), there is no cost win left: running Opus directly end-to-end is cheaper AND higher quality than Sonnet calling Opus-as-advisor.

### Why `sonnet_advisor_tool` is expensive

Each `sonnet_advisor_tool` call fires the advisor once, so the request pays Sonnet's executor tokens **plus** Opus's advisor tokens plus the overhead of the tool-use loop. The advisor output averages ~2,000 tokens per call (see Pilot 2 notes in the plan doc) — roughly 3-4× the executor's output, billed at Opus rates.

### Why `sonnet_solo` isn't the answer either

`sonnet_solo` is cheapest ($0.015/call) but its judge score (0.93) trails `opus_solo`'s 1.00. For the workloads this eval targets (architecture trade-offs, mid-implementation escalation, security-finding retries), the 0.07 quality gap matters. `sonnet_solo` remains the right choice for phases where Sonnet was already adequate (general execution) — this decision doesn't change that.

## Confidence

**Directional confidence: high.** Statistical confidence: low (n=1 per case).

The cost gap between `opus_solo` and `sonnet_advisor_tool` is ~2.3×, and the judge-quality gap is 1.00 vs 0.89. These are large effects relative to plausible trial-to-trial variance. A 20-trial run (~$12-25) would tighten CIs but is extremely unlikely to flip the ordering.

Skipping the 20-trial spend because:
1. The originally-planned 20-trial was sized for a **close** call (Pilot 2 showed `sonnet_advisor_tool` comparable to `opus_solo` at 2026-03 prices). The call is no longer close.
2. The keyword-substring rubric was structurally broken — it scored 11/12 responses at 1.00 because the discriminator keywords ("however", "but", "trade-off") appear in virtually every answer. The 20-trial would have inherited that noise. Trusting the LLM-as-judge score instead gives us the cleaner signal above.
3. Prompt caching would not have moved the numbers — Anthropic's 1024-token minimum for `cache_control` means the current prompts are below the threshold. Cache writes silently no-op'd in the pilot. The caching code was reverted; pricing and cache-field plumbing were kept as future-ready infra.

## Surprises

- **Opus 4.7 dropped 66% in price since the plan was written** (`$15/$75 → $5/$25` per MTok). Every cost estimate in the plan was stale. Verified against both `claude.com/pricing` and `platform.claude.com/docs/en/about-claude/pricing`. Committed in [`scripts/pricing.py`](../../scripts/pricing.py) with the `TODO: verify` markers removed.
- `sonnet_advisor_tool` underperformed `opus_solo` on judge quality (0.89 vs 1.00), not just on cost. The forwarding of full conversation history to the advisor doesn't compensate for Sonnet's weaker draft — the executor still writes the final answer.
- Prompt caching's 1024-token minimum is undocumented in the surface-level caching guide but load-bearing for small-prompt evals. Captured as a gotcha in the session notes.

## Out of scope

- Phases where the advisor tool might still earn its keep: long conversations where the advisor context accumulates, or workloads where the advisor gets called ≥3× per request (breakeven shifts with advisor-side conversation caching per Anthropic's tool-caching docs). This eval was single-call per request.
- Revisiting when Anthropic reduces the cache minimum, or when Sonnet+advisor overhead drops.
- Whether `sonnet_solo` should replace `opus_solo` for some of these phases. The 0.07 judge gap is suggestive but worth a separate eval sized for that specific question.

## Rollback

If a future Anthropic pricing shift, advisor-tool overhead reduction, or cache-minimum change reopens the question: reuse this eval harness (`evals/advisor_tool_ab/`), re-run `make advisor-ab-pilot` against current pricing, and revisit.
