# 2026-05-20 — NVIDIA LLM Router Planning Session — Handoff

## Goal (next session)

Implement Task 1 of [courierflow/docs/plans/2026-05-20-nvidia-llm-router.md](../../../../courierflow/docs/plans/2026-05-20-nvidia-llm-router.md) — declare the new NVIDIA + LLM-router settings fields in `app/config.py` and ship the first commit of the multi-PR migration.

## Current state (what shipped this session, what didn't)

**Shipped (this session, see PR list below):**
- `claude_flow` PR: CLAUDE.md NVIDIA gotcha refresh + new plan doc for `llm_judge.py` NVIDIA provider option + this handoff doc.
- `courierflow` PR: new plan doc `docs/plans/2026-05-20-nvidia-llm-router.md` — 11-task central LLM router with NVIDIA-first + Claude fallback + shadow-mode A/B audit. Plan-only, no code.

**In-flight: none.** Both PRs ship or merged before this handoff lands.

**Untouched but planned:**
- Implementation of either plan. The courierflow plan is the bigger lever (production token spend); the claude_flow `llm_judge.py` plan is a 2-task warmup.

## Empirical evidence collected this session

A/B test on `claude_flow` PR #60 (203-line diff, bash + docs):

| | Anthropic (Sonnet) | NVIDIA (kimi-k2.6) |
|---|---|---|
| Wall time | 38.9s | 31.4s |
| Findings | 49 (13 CRITICAL) | 23 (4 CRITICAL) |
| Cost | ~$0.10 est | $0 |

**Key finding driving plan design:** Anthropic and NVIDIA *fundamentally calibrate differently*. Anthropic's security reviewer over-flags command-injection on bash scripts that take no untrusted input. NVIDIA undershoots. This invalidated the original Task 11 gate ("≥90% Claude-NVIDIA agreement"); replaced with a hand-labeled gold-set methodology. **Do not regress this decision** — agreement-rate gating is a trap.

Logs at `/tmp/anthropic-run.log` and `/tmp/nvidia-run.log` (local-only, ephemeral).

## Exact next task

**File:** `/Users/summerrae/claude_code/courierflow/app/config.py`

**Operation:** Add the fields specified in Task 1 of the plan inside `class Settings(BaseSettings):`. Verbatim from plan:

```python
# NVIDIA / OpenAI-compatible provider
nvidia_api_key: Optional[str] = None
nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
nvidia_model: str = "moonshotai/kimi-k2.6"  # verified 2026-05-20; re-verify before changing
nvidia_timeout_s: float = 240.0  # below NVIDIA's 5-min edge

# LLM router behavior
llm_primary_provider: str = "anthropic"  # "nvidia" | "anthropic" | "openai"
llm_shadow_mode: bool = False  # when True, also call shadow provider and log
llm_shadow_provider: str = "nvidia"
```

Then write `tests/unit/test_llm_router_settings.py` per Task 1 Step 2 and commit.

**Acceptance:** `pytest tests/unit/test_llm_router_settings.py -v` passes; `pytest` overall still green.

## Architectural invariants to preserve

- **Promotion gate is gold-set accuracy, NOT Claude-NVIDIA agreement.** See plan Task 11. The 2026-05-20 A/B (above) proves agreement-rate is misleading.
- **Services depend on the `LLMProvider` protocol, never on SDKs directly.** Plan Task 2 establishes this. Direct `AsyncAnthropic(...)` / `AsyncOpenAI(...)` instantiation in services is the anti-pattern we're migrating away from.
- **Shadow mode never blocks the request path.** Plan Task 7 audit logger must `try/except: log.warning` all exceptions. Fire-and-forget.
- **Plan-only model IDs drift ~4 weeks.** See [claude_flow/CLAUDE.md](../../CLAUDE.md) NVIDIA gotcha section. Always `curl https://integrate.api.nvidia.com/v1/models` before relying on any model ID.
- **Skills canonical location:** `/Users/summerrae/claude_code/claude-skills/` — never write skills to `claude_flow/skills/`. See MEMORY `feedback_skills_canonical_location.md`.

## Template / reference PRs

- `claude_flow` `agent-sdk/pr-reviewer/src/model-client.ts` — TypeScript reference for the NVIDIA-first router pattern. Architecture transfers to Python; code does not.
- This session's `claude_flow` PR (NVIDIA gotcha refresh) — pattern for date-stamped gotcha updates.

## Pre-flight commands (run before touching code)

```bash
cd /Users/summerrae/claude_code/courierflow
git fetch origin --prune
git status
gh pr list --state open
# Verify NVIDIA model list — drift gotcha
set -a; source .env; set +a
curl -sS https://integrate.api.nvidia.com/v1/models \
  -H "Authorization: Bearer $NVIDIA_API_KEY" \
  | python3 -c "import sys,json; print('\n'.join(sorted(m['id'] for m in json.load(sys.stdin)['data'] if 'kimi' in m['id'])))"
# If moonshotai/kimi-k2.6 is gone, update nvidia_model default + flag in PR description.
```

Also read these before starting:
- `courierflow/docs/plans/2026-05-20-nvidia-llm-router.md` (the plan)
- `claude_flow/CLAUDE.md` "Known Gotchas" + "Pipeline Discipline Rules" sections
- This file

## Gates

```bash
cd /Users/summerrae/claude_code/courierflow
pytest tests/unit/test_llm_router_settings.py -v   # Task 1 acceptance
pytest                                              # nothing regresses
ruff format --check app/config.py tests/unit/test_llm_router_settings.py
```

No project-specific `quick_ci.sh` exists in courierflow as of this session — `pytest` alone is the gate.

## Ship instructions

Use `/ship`, not `/claude-flow`. This is pattern-execution of an approved plan, not new design work. One PR per logical task (or merge 2-3 small adjacent tasks into one PR — Tasks 1+2 could ship together since they're both pure scaffolding with no dependencies on each other).

Update the courierflow plan doc's task headers with `[x]` as tasks merge so future readers know the cursor position.

## Mode directive

Auto mode. Surface premise contradictions only.

---

## Execution log

- 2026-05-20 — Plans authored and gotcha-refreshed in claude_flow + courierflow. A/B run validated cost-saving premise (NVIDIA $0 + 24% faster on PR #60) but revealed calibration gap that drove Task 11 redesign. Ship'd both PRs.
