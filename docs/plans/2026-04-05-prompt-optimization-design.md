# Prompt Optimization Engine — Design

**Date:** 2026-04-05
**Target:** Phase 2 explorer prompts (extensible to all subagents later)
**Goal:** Explorer prompts measurably improve over time via A/B testing with F1-scored outcomes

---

## Problem

Phase 2 dispatches explorer subagents with static prompts from `smart-exploration/prompt-library.md`. There's no feedback loop:

- No data on whether explored files were actually useful in implementation
- No detection of **missed files** — critical files the explorer didn't find that the implementer needed
- No way to compare prompt variants and converge on better wording
- Exploration quality directly determines architecture and implementation quality

## Solution

A closed-loop prompt optimization system:

1. **Track** which files each explorer finds (Phase 2 output)
2. **Track** which files are actually used in implementation (Phase 5 reads)
3. **Compute** precision (found & used / found) and recall (found & used / total needed)
4. **Score** each prompt variant with F1(precision, recall) * (1 - retry_rate)
5. **Rotate** variants via A/B selection per session
6. **Promote** the winner after sufficient data (10+ sessions)
7. **Generate** challenger variants by LLM-rewriting the loser

---

## Data Model

### `memory/prompt-variants.json`

```json
{
  "schema_version": 1,
  "explorer": {
    "feature": {
      "variants": [
        {
          "id": "feature-A-v1",
          "role": "route-service-model-chain",
          "prompt": "think harder about... Trace the route -> service...",
          "created": "2026-04-05T00:00:00Z",
          "metrics": {
            "sessions": 0,
            "total_files_found": 0,
            "total_files_used": 0,
            "total_files_needed": 0,
            "total_retries": 0,
            "precision_sum": 0.0,
            "recall_sum": 0.0,
            "f1_sum": 0.0
          },
          "active": true
        }
      ],
      "min_sessions": 10,
      "current_best": null
    }
  }
}
```

Each task category (endpoint, ui, data, etc.) has its own variant pool. Each explorer role (A and B) within a category has independent variants.

### `memory/exploration-events.jsonl`

One line per Phase 2 session. Appended by the tracking script.

```json
{
  "ts": "2026-04-05T12:00:00Z",
  "session_id": "abc123",
  "task_category": "endpoint",
  "variant_id": "endpoint-A-v2",
  "explorer_role": "A",
  "files_found": ["routes/payments.py", "services/payment_service.py", ...],
  "files_used_in_impl": ["routes/payments.py", "models/invoice.py", ...],
  "files_needed_not_found": ["utils/currency.py", "config/stripe.py"],
  "precision": 0.6,
  "recall": 0.75,
  "f1": 0.67,
  "phase5_retries": 2,
  "score": 0.44
}
```

---

## Score Calculation

```
precision = |files_found ∩ files_used| / |files_found|
recall    = |files_found ∩ files_used| / |files_used|
f1        = 2 * precision * recall / (precision + recall)
score     = f1 * (1 - min(retry_rate, 1.0))
```

Where:
- `files_found` = files listed in explorer output (Phase 2)
- `files_used` = files read/edited during Phase 5 implementation
- `retry_rate` = phase5_retries / plan_steps (normalized)

**Score range:** 0.0 (useless) to 1.0 (perfect). Higher is better.

**Why F1:** Precision alone rewards finding fewer files. Recall alone rewards finding everything. F1 balances both — the explorer should find the files that matter and not flood with noise.

**Why retry penalty:** High retry rates in Phase 5 often trace back to poor exploration — the implementer didn't have context it needed, leading to wrong assumptions.

---

## Variant Selection (A/B)

**Per session, per explorer role:**

1. If a category has only 1 active variant per role → use it (no A/B)
2. If 2+ active variants → select via epsilon-greedy:
   - 80% of the time: pick the variant with highest avg score
   - 20% of the time: pick a random non-best variant (exploration)
3. Record which variant was selected in the exploration event

**Minimum sessions before comparison:** 10 per variant. Until both variants have 10+ sessions, rotate evenly (round-robin).

---

## Promotion & Challenger Generation

Triggered by `prompt-optimization` skill during session-learnings:

### Promotion (auto)

When both variants in a category have 10+ sessions:
- If variant A's avg F1 > variant B's avg F1 by 0.05+: A wins
- Update `current_best` in prompt-variants.json
- Update the corresponding prompt in `prompt-library.md`

### Challenger Generation (semi-auto)

When a variant loses:
1. Ask an LLM: "This explorer prompt scored F1={loser_f1}. The winning prompt scored F1={winner_f1}. The loser missed these files in recent sessions: {missed_files_summary}. Rewrite the losing prompt to better find these file types while keeping the same exploration scope."
2. The rewritten prompt becomes a new variant (active=true)
3. The old loser is deactivated (active=false, preserved for history)

**Challenger generation requires user approval** — proposed via session-learnings output, not auto-applied.

---

## Integration Points

### 1. Phase 2 (smart-exploration)

**Modified behavior:** Before dispatching explorers, the orchestrator:
1. Classifies task category (existing behavior)
2. Calls `select_variant(category, role)` to pick which prompt to use
3. Records the variant_id for tracking
4. Dispatches the selected prompt

### 2. Post-Phase-2 (new hook or inline)

After explorers return, record `files_found` per explorer. This is the set of files listed in each explorer's output.

### 3. Post-Phase-5 (new hook or inline)

After implementation completes, compute:
- `files_used_in_impl` = all files read/edited during Phase 5
- `files_needed_not_found` = files_used_in_impl - files_found (across all explorers)
- `phase5_retries` = count of retry loop iterations

Write the exploration event to `memory/exploration-events.jsonl`.

### 4. Session Learnings (extended)

After session-learnings runs its existing analysis, also:
1. Read exploration-events.jsonl for this session
2. Update prompt-variants.json with new metrics
3. Check if any variant pair is ready for promotion
4. If promotion triggered, propose the change
5. If challenger generation needed, draft it for user approval

### 5. MCP Server (new tool)

`get_prompt_performance` tool returns:
- Per-category, per-role variant comparison table
- Current best variant per role
- Recent miss patterns (most commonly missed file types)
- Recommendation: "ready to promote" / "needs more data" / "no significant difference"

---

## File Changes

| File | Action | Est. Lines | Description |
|------|--------|-----------|-------------|
| `memory/prompt-variants.json` | **Create** | ~120 | Seed with current prompts as v1 variants |
| `memory/exploration-events.jsonl` | **Create** | 0 | Empty, populated at runtime |
| `scripts/prompt-tracker.py` | **Create** | ~180 | Record exploration events, compute scores |
| `skills/prompt-optimization/SKILL.md` | **Create** | ~120 | Variant comparison, promotion, challenger generation |
| `skills/smart-exploration/SKILL.md` | **Modify** | ~15 | Add variant selection step before dispatch |
| `skills/smart-exploration/prompt-library.md` | **Modify** | ~10 | Add variant ID markers to each prompt |
| `skills/session-learnings/SKILL.md` | **Modify** | ~15 | Add prompt optimization trigger |
| `mcp/claude-flow-server/server.py` | **Modify** | ~60 | Add get_prompt_performance tool |
| `install.sh` | **Modify** | ~5 | Copy new files |
| **Total** | | ~525 | |

---

## Build Sequence

- [ ] **Step 1:** Create `memory/prompt-variants.json` seeded with current prompt-library prompts as v1 variants
- [ ] **Step 2:** Create `scripts/prompt-tracker.py` with score computation logic
- [ ] **Step 3:** Create `skills/prompt-optimization/SKILL.md`
- [ ] **Step 4:** Modify `skills/smart-exploration/SKILL.md` to add variant selection
- [ ] **Step 5:** Add variant ID markers to `prompt-library.md`
- [ ] **Step 6:** Extend `session-learnings/SKILL.md` with prompt optimization trigger
- [ ] **Step 7:** Add `get_prompt_performance` tool to MCP server
- [ ] **Step 8:** Update `install.sh`
- [ ] **Step 9:** Run tests, manual smoke test

---

## Trade-offs

1. **Event-based tracking (JSONL) vs. database:** JSONL is simple, append-only, human-readable, and consistent with existing failure-events.jsonl pattern. A DB would be overkill for ~50-100 events.

2. **Epsilon-greedy vs. Thompson sampling:** Epsilon-greedy is simpler to implement and debug. Thompson sampling converges faster but requires Bayesian stats. For 10+ session thresholds, epsilon-greedy is sufficient.

3. **F1 score vs. simple accuracy:** F1 captures both precision (noise reduction) and recall (miss detection). Simple "% files useful" would miss the false-negative problem entirely.

4. **Per-role variants vs. per-category:** Each explorer role (A and B) has its own variants because they serve different purposes (e.g., "route chain" vs. "middleware patterns"). Optimizing them independently prevents one role's improvement from masking the other's regression.

5. **Challenger generation requires approval:** Auto-generating prompts risks drift. User approval ensures prompt quality stays high while still automating the measurement and comparison work.
