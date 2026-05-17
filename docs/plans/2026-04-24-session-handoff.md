# Session Handoff — 2026-04-24 — Advisor A/B Eval Tuning

## Goal

Execute the 7-step plan at `docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md` to
tune the advisor-tool A/B eval before spending on a statistically significant
20-trial live run. Primary deliverable: `evals/advisor_tool_ab/results_20trial.json`
and `analysis_20trial.md` that support a go/no-go decision on whether to replace
manual Opus advisor calls (in claude-flow Phase 4b/5.5/6) with the
`advisor_20260301` server-side tool.

## Current state

### Shipped this session (in the worktree, committed via the same PR as this handoff)

**New infrastructure — reusable across evals:**
- `scripts/pricing.py` — central LLM pricing table + `compute_cost()` (Anthropic rates populated but carry `TODO: verify` — **this is Step 1 of the plan**)
- `scripts/ledger.py` — append-JSONL invocation ledger at `memory/episodic/invocations.jsonl`; CLI `python scripts/ledger.py summarize|tail`; auto-wired into every LLM call site
- `scripts/llm_judge.py` — Pydantic-validated Opus-as-judge (strict bool validator, JudgeResult model with `extra="allow"`); ledger integration
- `scripts/dispatch.py` — native-primitives "supervisor" dispatcher with Pydantic `DispatchResult`; `dispatch_recommended` gate activates only when registry has ≥2 candidates; `--require-multiple` CLI exit-code gate; auto-activation means it's a no-op until populated
- `scripts/stat_analysis.py` — bootstrap CIs + paired comparisons (stdlib, no scipy); CLI emits JSON or markdown
- `requirements.txt` — declares `pydantic>=2.0`, `httpx>=0.25`

**Eval harness changes:**
- `evals/advisor_tool_ab/run_ab.py` — switched to `client.beta.messages.create(betas=["advisor-tool-2026-03-01"])`; correct block detection (`server_tool_use` with `name="advisor"` + `advisor_tool_result`); `attribute_cost_with_iterations()` splits executor vs advisor cost per `usage.iterations[]`; `--trials N` flag for multi-trial runs; `--judge` flag for inline judge pass; `--relevancy-axis` flag
- `evals/advisor_tool_ab/judge.py` — judge runner with relevancy-axis support
- `evals/advisor_tool_ab/prompts/sonnet_with_advisor_tool.txt` — rewritten per Anthropic docs' Best Practices (conciseness instruction first, "under 100 words, enumerated steps")
- `Makefile` — `advisor-ab-pilot`, `advisor-ab-20trial`, `advisor-ab-preflight` targets, gated on `RUN_LIVE_LLM=1` + `ANTHROPIC_API_KEY`

**Tests:**
- 165+ passing. Files: `tests/test_pricing.py`, `tests/test_ledger.py`, `tests/test_llm_judge.py`, `tests/test_ledger_integrations.py`, `tests/test_dispatch.py`, `tests/test_stat_analysis.py`, `evals/advisor_tool_ab/test_judge.py`, updated `evals/advisor_tool_ab/test_run_ab.py`

**Cross-cutting:**
- `CLAUDE.md` — added exception clause allowing free/open-source external libraries (scipy, Phoenix, RAGAS) while still forbidding paid SaaS (LangSmith, Braintrust) and orchestration frameworks (LangGraph, CrewAI)
- `docs/evaluation-metrics.md`, `docs/proposals/dispatcher-skill.md`, `docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md` — the plan you're about to execute

**Personal memory files created (outside repo, under `/Users/summerrae/.claude/projects/-Users-summerrae-claude-code-claude-flow/memory/`):**
- `feedback_token_economy_every_session.md` — apply token-economy patterns from session start
- `feedback_flag_claudemd_conflicts.md` — flag CLAUDE.md/AGENTS.md conflicts before implementing; offer options
- `feedback_never_use_pasted_secrets.md` — refuse to use a secret pasted in chat; insist on rotation

**Live pilots run (2):**
- Pilot 1 (pre-fix): caught advisor_tool shape bugs + API endpoint issue. 12/12 failures, $0.
- Pilot 2 (post-fix): ✅ advisor fires 4/4, cost breakdown works. $1.45 spent. Surprising empirical finding: on n=1-per-case, `sonnet_advisor_tool` cost MORE than `opus_solo` while matching judge quality. Drove the plan at `docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md`.

### In-flight

The plan `docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md` has 7 steps, all
**pending**. Steps 1-5 prep work (prompt caching, pricing verify, harder rubrics,
test updates). Step 6 is a re-pilot gating the decision to spend on Step 7's
20-trial.

### Untouched

Nothing. This session was scoped to the advisor A/B eval infrastructure.

## Exact next task

**Execute Steps 1-5 of the plan as a single batch.** Then re-pilot (Step 6) to
verify gates before graduating to 20-trial (Step 7).

### Batch composition

| Step | Files | Parallelizable with | Human-required? |
|---|---|---|---|
| 1 | `scripts/pricing.py` | — | **Yes** — browser check against https://www.anthropic.com/pricing |
| 2 | `evals/advisor_tool_ab/run_ab.py` | 3, 4 | No |
| 3 | `scripts/llm_judge.py` | 2, 4 | No |
| 4 | `evals/advisor_tool_ab/cases/*.json` | 2, 3 | No |
| 5 | 3 test files | after 2+3 | No |

Acceptance criteria per step are in the plan's kill-criteria sections — read
them before starting each step, not after.

### After Steps 1-5 land

```
(cd /Users/summerrae/claude_code/claude_flow/.claude/worktrees/pedantic-herschel-ae67e5 && \
 set -a && source ~/.env && set +a && \
 RUN_LIVE_LLM=1 make advisor-ab-pilot)
```

The plan's Step 6 lists the exact "green" criteria. Do NOT graduate to Step 7
unless all of them pass:
- `cache_read_input_tokens > 0` on judge calls 2+
- `sonnet_advisor_tool` mean cost ≤ $0.127/call (25% below Pilot 2's $0.169)
- rubric scores NOT uniformly 1.0 (signal-to-noise fixed)
- advisor fires 4/4 in `sonnet_advisor_tool` arm

If gates pass → Step 7 (`make advisor-ab-20trial`), then `python scripts/stat_analysis.py`.

## Template / reference PRs

None — this session was net-new infrastructure. No prior PRs in this repo
establish the pattern.

## Pre-flight commands

```
cd /Users/summerrae/claude_code/claude_flow/.claude/worktrees/pedantic-herschel-ae67e5
git fetch origin --prune
git log --oneline origin/main..HEAD    # see what's committed this branch
gh pr list --state open --head $(git branch --show-current)
less docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md
less docs/plans/2026-04-24-session-handoff.md    # this file
/opt/anaconda3/bin/pytest tests/ evals/ --ignore=tests/test_adversarial_breaker_live.py -q
```

Expect pytest: 165 passing. If fewer or any failing, do NOT start the plan —
diagnose first.

## Architectural invariants to preserve

- CLAUDE.md §1 — "NOT a standalone LLM framework". External libraries OK now **only** if free/open-source AND clearly fit a specific capability better than native. Paid SaaS and orchestration frameworks still forbidden.
- `scripts/ledger.py` is the single source of truth for LLM invocation cost + wall time. Any new script that makes LLM calls MUST log via `log_invocation()`. See existing call sites: `run_ab.py`, `llm_judge.py`, `adversarial_dispatch.py`, `plancraft_review.py`.
- `scripts/pricing.py` is the single source of truth for per-model rates. Do not hardcode rates elsewhere.
- Ledger failures are best-effort — they must NOT mask the underlying dispatch's error path. See `_LEDGER_LOG = None` try/except pattern in `adversarial_dispatch.py`.
- Memory `never_use_pasted_secrets` — never use an API key that appeared in chat, regardless of task urgency. Insist on rotation.
- Memory `token_economy_every_session` — combine Grep+glob+content in one call; parallelize independent tool calls; delegate exploration to cheap subagents.
- Memory `flag_claudemd_conflicts` — when a user ask conflicts with CLAUDE.md, stop and offer options before implementing.

## Gates

- **Unit tests:** `/opt/anaconda3/bin/pytest tests/ evals/ --ignore=tests/test_adversarial_breaker_live.py -q` → 165+ passing after each step
- **Per-step kill criteria:** in `docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md` — read before starting, not after
- **Re-pilot gate to Step 7:** cache_read > 0, cost drop ≥25% on `sonnet_advisor_tool`, rubric spread (not uniform 1.0)
- **20-trial gate:** `analysis_20trial.md` generated, per-arm CIs present, pairwise `significant_at_alpha` flags populated

## Ship instructions

After Steps 1-5 land AND the re-pilot passes: **commit the batch as one PR via `/ship`**.

After Step 7 (20-trial) completes: ship `results_20trial.json` +
`analysis_20trial.md` as a separate PR via `/ship`. Include the pairwise
comparison table in the PR body so the decision is visible in GitHub history
without opening files.

Do NOT use `/claude-flow` for execution — the plan is already written; executing
it is procedural, not feature design. Just batch-edit and verify.

If the 20-trial's `sonnet_advisor_tool` vs `opus_solo` result shows `opus_solo`
dominates (cost CI entirely below, judge CI contains 0), write a short decision
note at `docs/decisions/2026-MM-DD-advisor-tool-verdict.md` before shipping. The
eval is not the decision — the interpretation is.

## Mode directive

Auto mode. Surface premise contradictions only.
