# llm_judge.py NVIDIA Provider Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an opt-in NVIDIA provider to `scripts/llm_judge.py` so eval-pilot judging can run on free models when Anthropic pricing shifts or eval scale is large.

**Architecture:** Add a `--provider {anthropic,nvidia}` CLI flag (default `anthropic`, preserving current behavior). When `nvidia` is selected, route the judge call through an OpenAI-compatible client pointed at NVIDIA's endpoint. Reuse the same JSON-output contract — judges return per-criterion pass/fail + rationale regardless of provider.

**Tech Stack:** Python 3.11, `openai` SDK (already a dep via courierflow-style reuse), existing `anthropic` SDK, existing ledger logging.

**Ruled Out:**
- Provider switch via env var only — explicit `--provider` is more debuggable during eval pilots.
- Generalizing into `agent-sdk/pr-reviewer/`'s `ModelClient` TS module — Python<>TS bridge isn't worth one script's worth of reuse.
- NVIDIA as default — Anthropic-graded Opus is the current calibration baseline; flipping defaults invalidates prior eval results.

## References

- `scripts/llm_judge.py` — the file being modified
- `agent-sdk/pr-reviewer/src/model-client.ts` — TypeScript reference for NVIDIA provider pattern (architecture transfers, not the code)
- `CLAUDE.md` "PR reviewer is provider-pluggable" + "NVIDIA gotchas" sections — model ID versioning, soft prompt requirement, 5-min edge timeout
- MEMORY `feedback_pricing_freshness_pre_flight.md` — verify NVIDIA model list before relying on a specific ID

---

## Pre-flight (manual, before Task 1)

1. Verify NVIDIA model list: `curl -sS https://integrate.api.nvidia.com/v1/models -H "Authorization: Bearer $NVIDIA_API_KEY" | jq '.data[].id' | sort | head -30`
2. Pick the judge model — recommend a reasoning-capable model (judges benefit from reasoning). `moonshotai/kimi-k2-instruct-0905` is confirmed working. **Caveat from CLAUDE.md:** NVIDIA reasoning models that put output in a `reasoning` field are not currently parsed — skip those unless wiring that up.
3. Set `NVIDIA_API_KEY`, `NVIDIA_JUDGE_MODEL` in the eval session's env.

## Success Criteria

- `python scripts/llm_judge.py --help` shows `--provider {anthropic,nvidia}`
- Existing usage (no `--provider`) produces byte-identical behavior to pre-change
- New NVIDIA path returns the same JSON shape (`score`, `per_criterion`, `judge_model`, `cost_usd`, `wall_time_s`)
- Dry-run path still works for both providers
- Cost-USD field is populated for NVIDIA (0.0 — free tier — but logged for audit)
- Ledger logs `provider=nvidia` alongside model ID for filter-ability in cost reports

---

### Task 1: Add `--provider` flag + provider dispatch
**Type:** value_unit
**Depends on:** none

**Files:**
- Modify: `scripts/llm_judge.py`
- Test: `tests/test_llm_judge.py` (add cases)

**Step 1: Failing test**

```python
# tests/test_llm_judge.py — add to existing file

def test_judge_response_accepts_provider_kwarg(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("NVIDIA_API_KEY", "")
    # dry-run path — no network
    from scripts.llm_judge import judge_response
    r = judge_response(
        response_text="x",
        rubric=[{"criterion": "is x", "weight": 1.0}],
        context=None,
        question=None,
        session_id="t",
        case_name="t",
        arm="t",
        provider="nvidia",  # NEW
    )
    assert r["judge_model"].startswith(("moonshot", "meta", "nvidia")) or r.get("dry_run")
```

Run: `pytest tests/test_llm_judge.py::test_judge_response_accepts_provider_kwarg -v` → FAIL (TypeError, unexpected kwarg)

**Step 2: Implement**

In `scripts/llm_judge.py`, locate the `judge_response()` function and:

1. Add `provider: str = "anthropic"` param
2. Branch on provider:
   - `"anthropic"`: existing code path, unchanged
   - `"nvidia"`: call `_judge_via_nvidia(...)` (new helper)
3. Add `_judge_via_nvidia()` that:
   - Reads `NVIDIA_API_KEY`, `NVIDIA_JUDGE_MODEL` (default `moonshotai/kimi-k2-instruct-0905`), `NVIDIA_BASE_URL` (default `https://integrate.api.nvidia.com/v1`)
   - Uses `openai.OpenAI(api_key=..., base_url=...)` (sync — judge calls are sync today)
   - Sends the same judge prompt as the Anthropic path, parses the same JSON-coded response
   - Returns the same dict shape; `cost_usd=0.0` (free tier), `judge_model` = the NVIDIA model ID
   - Logs to the existing ledger with `provider="nvidia"`

4. CLI: if `__main__` block parses args, add `argparse` flag `--provider`, pass to `judge_response`.

**Step 3: Test, commit**

```bash
git add scripts/llm_judge.py tests/test_llm_judge.py
git commit -m "feat(llm_judge): add NVIDIA provider option"
```

---

### Task 2: Document in CLAUDE.md "Known Gotchas"
**Type:** value_unit
**Depends on:** T1

**Files:**
- Modify: `CLAUDE.md` (Known Gotchas section)

Add a single bullet documenting that `llm_judge.py` supports `--provider nvidia`, and reminding readers to check the model ID against `/v1/models` before pilots.

Keep it brief — one line, format-matching the existing gotchas.

Commit.

---

## Rollback

`--provider` is opt-in. Reverting requires no rollback — existing callers that omit `--provider` are byte-identical to pre-change behavior.

If the NVIDIA path produces bad judgements during a pilot, drop `--provider nvidia` and re-run.

## Gate Validation

- [ ] `pytest tests/test_llm_judge.py` is the test command (verified — file exists)
- [ ] No new external scripts referenced
