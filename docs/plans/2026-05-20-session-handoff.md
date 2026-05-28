# 2026-05-20 — NVIDIA LLM Router Planning Session — Handoff

## Goal (next session)

Implement **Task 3** of [courierflow/docs/plans/2026-05-20-nvidia-llm-router.md](../../../../courierflow/docs/plans/2026-05-20-nvidia-llm-router.md) — the `NvidiaProvider` implementation under `app/services/ai/providers/nvidia.py`. First task that actually instantiates an SDK client and touches a real network surface. Pattern is fixed by Tasks 1+2; this is execution, not design.

## Current state (what shipped, what didn't)

**Shipped:**
- `claude_flow` #61 — CLAUDE.md NVIDIA gotcha refresh + plan docs + this handoff doc (merged 2026-05-21)
- `courierflow` #707 — 11-task NVIDIA LLM router plan doc (merged 2026-05-21)
- `claude-skills` #104 — session-learnings from the planning session (merged 2026-05-21, 5 conflicts resolved at merge time)
- `courierflow` #709 — **Task 1**: NVIDIA + router settings fields in `app/config.py` + 5 unit tests (merged 2026-05-22 as `939f45c1`)
- `courierflow` #710 — **Task 2**: `LLMProvider` Protocol + `LLMResponse` dataclass + `LLMProviderError` + 5 unit tests (merged 2026-05-22 as `333ec278`)

**In-flight: none.**

**Untouched but planned:**
- Tasks 3–11 of the courierflow plan. Tasks 3–5 (the three provider implementations) are parallelizable — they all depend on Task 2 and on nothing else. Task 6 (Alembic migration for `llm_shadow_audit`) is also independent and can run alongside.

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

**Files to create:**
- `app/services/ai/providers/__init__.py` (empty)
- `app/services/ai/providers/nvidia.py` — `NvidiaProvider` class implementing the `LLMProvider` protocol
- `tests/unit/ai/providers/__init__.py` (empty)
- `tests/unit/ai/providers/test_nvidia.py` — failing test first (TDD), then implement

**Operation:** Follow Task 3 Step 1–3 of [the plan](../../../../courierflow/docs/plans/2026-05-20-nvidia-llm-router.md) verbatim. The plan has the full code for both the test and the implementation.

Key design choices already fixed by the plan — do not relitigate:
- Uses the `openai` SDK pointed at `settings.nvidia_base_url` (NVIDIA's edge speaks OpenAI's chat-completions API)
- Wraps SDK exceptions as `LLMProviderError(provider="nvidia", retryable=True)`
- Maps `choice.message.tool_calls` into the unified `LLMResponse.tool_calls` shape (list of `{id, name, arguments}`)
- `model` is held on the instance, not passed per-call

**Acceptance:** `pytest tests/unit/ai/providers/test_nvidia.py -v` passes (3 tests minimum: parse OpenAI response, wrap provider error, pass through tool_calls).

**Important — verify the live NVIDIA model ID before relying on it.** Task 1 committed `nvidia_model="moonshotai/kimi-k2.6"` un-reverified because there was no `.env` in courierflow. Task 3 is the first task that hits the live endpoint. Run the model-list curl from Pre-flight below; if `moonshotai/kimi-k2.6` is gone, update `nvidia_model` default in `app/config.py` and the plan doc as part of this PR.

## Architectural invariants to preserve

- **Promotion gate is gold-set accuracy, NOT Claude-NVIDIA agreement.** See plan Task 11. The 2026-05-20 A/B (above) proves agreement-rate is misleading.
- **Services depend on the `LLMProvider` protocol, never on SDKs directly.** Plan Task 2 establishes this. Direct `AsyncAnthropic(...)` / `AsyncOpenAI(...)` instantiation in services is the anti-pattern we're migrating away from.
- **Shadow mode never blocks the request path.** Plan Task 7 audit logger must `try/except: log.warning` all exceptions. Fire-and-forget.
- **Plan-only model IDs drift ~4 weeks.** See [claude_flow/CLAUDE.md](../../CLAUDE.md) NVIDIA gotcha section. Always `curl https://integrate.api.nvidia.com/v1/models` before relying on any model ID.
- **Skills canonical location:** `/Users/summerrae/claude_code/claude-skills/` — never write skills to `claude_flow/skills/`. See MEMORY `feedback_skills_canonical_location.md`.

## Template / reference PRs

- **courierflow #710** (Task 2) — the protocol this task implements. `app/services/ai/llm_provider.py` defines the exact shape `NvidiaProvider` must conform to. Mock with the same pattern in the test.
- **courierflow #709** (Task 1) — pattern for ship cadence on this plan: one PR per task, TDD test file alongside, standalone-test verification in PR body when local `pytest` can't run, `ruff format --check` clean before push.
- `claude_flow/agent-sdk/pr-reviewer/src/model-client.ts` — TypeScript reference for the NVIDIA call pattern. Architecture transfers to Python; the message-mapping + tool_calls extraction is essentially the same.

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
pytest tests/unit/ai/providers/test_nvidia.py -v   # Task 3 acceptance
pytest tests/unit/ai/ -v                            # all router unit tests
ruff format --check app/services/ai/providers/ tests/unit/ai/providers/
```

**Known local-env gap (carried from Tasks 1–2):** Courierflow's local `.venv` is missing prod deps (`procrastinate`, `sqlmodel` — installed mid-Task-1, but the venv is generally stale relative to `pyproject.toml`/`uv.lock`). `pytest` won't load `tests/conftest.py` locally. Verification pattern that worked for #709 and #710: run each test function standalone via `importlib` against the imported module; document the standalone proof in the PR body and let CI run the real gate. CI uses `pip install -r requirements.txt` and has been green on both Task 1 and Task 2.

No project-specific `quick_ci.sh` exists in courierflow — Copilot Critical Eval Gate on the PR + CI `pytest` are the gates.

## Ship instructions

Use `/ship`, not `/claude-flow`. This is pattern-execution of an approved plan, not new design work. One PR per logical task (or merge 2-3 small adjacent tasks into one PR — Tasks 1+2 could ship together since they're both pure scaffolding with no dependencies on each other).

Update the courierflow plan doc's task headers with `[x]` as tasks merge so future readers know the cursor position.

## Mode directive

Auto mode. Surface premise contradictions only.

---

## Execution log

- 2026-05-20 — Plans authored and gotcha-refreshed in claude_flow + courierflow. A/B run validated cost-saving premise (NVIDIA $0 + 24% faster on PR #60) but revealed calibration gap that drove Task 11 redesign. Ship'd both PRs.

- 2026-05-21 — Merged the three open PRs from the planning session: claude_flow #61, courierflow #707, claude-skills #104. #104 needed conflict resolution at merge time: 1 hand-merged content conflict in `claude-flow/SKILL.md` (kept both: new table row from the branch + new `## Notes` section from main); 3 add/add conflicts on SKILL.md files where the branch's stale 2026-05-20 drafts were superseded by canonical versions on main — resolved with `git checkout --theirs`. Verified no branch-unique content was lost (files were `additions:N, deletions:0` on the branch).

- 2026-05-22 — Shipped Tasks 1 and 2: courierflow #709 (settings) and #710 (LLMProvider protocol). Both verified via standalone-import test execution since local `.venv` lacks prod deps; both CI checks green. Five tests each. Task 2 added three tests beyond the plan's minimum to cover real failure modes (mutable-default isolation, safe-default constructor, `retryable=False` preservation). Scaffolding phase complete — next session opens with Task 3 (NVIDIA provider) as the first network-touching implementation.
