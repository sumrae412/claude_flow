# Mid-Run Context Extraction (Phase 5 Step 3e)

**Date:** 2026-04-15
**Status:** Approved
**Inspiration:** Board game cafe "document-back-into-project" feedback loop pattern

---

## Problem

During Phase 5 implementation, each task step generates valuable domain facts — discovered column names, API response shapes, error patterns, working query structures. Currently these facts exist only in the executor's conversation context and are lost when:
- Context compaction fires at 60-80% threshold
- A new subagent is dispatched for the next task (fresh context)
- The session ends without running session-learnings

## Solution: Post-Task Extraction Step

After each task completes (tests pass + lint clean), a lightweight inline extraction step runs before the next task begins.

## Phase 5 Step Sequence (updated)

```
Step 1: Setup (branch, deps)
Step 2: Per-task TDD loop
  Step 3a: Tests (red → green)
  Step 3b: GUARD (regression check)
  Step 3c: Mutation gate
  Step 3d: Visual verify gate (optional)
  → NEW: Step 3e: Context extraction
Step 4: Static analysis (lint, type check)
Step 5: Inter-task verification gate
→ Next task
```

## Extraction Mechanics

The executor (Sonnet inline, not a subagent) runs a structured extraction prompt after each task:

```
Review the task you just completed. Extract reusable domain facts in these categories:

1. SCHEMA: Column names, table relationships, enum values discovered
2. API: Endpoint signatures, response shapes, error codes encountered
3. PATTERN: Code patterns that worked (import paths, service method signatures)
4. GOTCHA: Anything that failed first and required a different approach

Output as structured YAML. Max 10 facts. Only novel discoveries, not things already in $plan or $requirements.
```

## Output Format

Facts appended to `$context_facts` section within `$diff` contract:

```yaml
context_facts:
  - task: "task-1-add-user-model"
    facts:
      - type: SCHEMA
        fact: "HouseholdMember.is_primary_contact (not is_primary)"
      - type: PATTERN
        fact: "household_service.ensure_client_for_member() required after create"
      - type: GOTCHA
        fact: "scalar_one_or_none() crashes on email lookup — use scalars().first()"
```

## Contract Change

Add `context_facts` as optional field to `diff.schema.md`:

```yaml
context_facts:       # Optional. Populated by Phase 5 Step 3e.
  - task: string     # Task identifier from $plan
    facts:           # Array of extracted facts
      - type: SCHEMA | API | PATTERN | GOTCHA
        fact: string # One-line reusable fact
```

## Consumption Points

| Consumer | How it uses facts |
|----------|------------------|
| Next task executor | Facts injected into task prompt as "known context" |
| Phase 6 reviewers | Facts travel via `$diff` contract |
| Session-learnings | Skips facts already captured — no duplication |
| Memory injection | GOTCHA facts are candidates for MEMORY.md promotion |

## Memory Promotion Heuristic

After Phase 5, facts tagged GOTCHA that match existing MEMORY.md domains get flagged for automatic promotion. Unmatched facts go to session-learnings for manual review.

## Performance Budget

- Runs as Sonnet inline (no subagent spawn = ~0s overhead)
- ~200 tokens in, ~100 tokens out per task
- Estimated overhead: 5-10 seconds per task
- Skipped if task had zero test files changed (documentation-only tasks)

## Ruled Out

- Background subagent — 30s startup overhead, facts arrive too late
- Extending session-learnings mid-session — wrong granularity
- Context pressure threshold trigger — facts lost before extraction fires
- Writing to MEMORY.md mid-run — too noisy, pollutes memory with task-specific details
