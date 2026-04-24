# Proposal: `dispatcher` skill — native-primitives supervisor

**Status:** Draft. Lives in this repo; intended destination is the
`claude-skills/` checkout once the reviewer endorses it.

## Why

The claude_flow `CLAUDE.md` explicitly forbids wrapping the system in an
external orchestrator (LangGraph / CrewAI / etc.). But the "supervisor
pattern" — a lead agent dynamically delegating to sub-agents chosen by their
strengths — is a real need. This skill implements it using only Claude
Code's native primitives: the `Agent` tool and the existing
`reviewer-registry.json`.

The mechanical work — classifying the task, scoring candidate agents,
returning picks with rationale — is already implemented in
[scripts/dispatch.py](../../scripts/dispatch.py). This skill is the
user-facing surface that tells the orchestrator how to call it and what to
do with the result.

## Relationship to existing pieces

| Piece | Role |
|-------|------|
| `reviewer-registry.json` | Registry of sub-agent strengths (existing) |
| `claude-skills/claude-flow/scripts/select_reviewers.py` | Phase-6-specific file-pattern reviewer selector (existing) |
| **`scripts/dispatch.py`** | **General dispatcher — classifies task, ranks agents (new)** |
| **`skills/dispatcher/SKILL.md`** | **User-facing invocation surface (this doc)** |
| `claude-flow` skill Phase 6 | Primary caller — uses dispatcher to fan out reviewers |

The dispatcher does NOT replace `select_reviewers.py`. That script does
deterministic file-glob matching for Phase 6's cascade. The dispatcher
generalizes: any task shape, any registry, ranked by description overlap
AND file patterns AND optional explicit shape hints.

## Proposed SKILL.md

Ship this file to `claude-skills/dispatcher/SKILL.md`:

````markdown
---
name: dispatcher
description: Pick the right sub-agent(s) for a task by shape, file patterns, and agent strengths. Use when you have a task and want a ranked recommendation of which Agent tool sub-agents to dispatch — especially for review, exploration, or architecture work where multiple candidates exist. Reads reviewer-registry.json by default; extensible to any registry with the same schema.
user-invocable: true
---

# Dispatcher — Native-Primitives Supervisor

Claude Code already gives you dynamic delegation via the `Agent` tool. The
missing piece is a principled way to choose *which* sub-agent to dispatch
when several could apply. This skill is that piece — read-only, ~200 lines
of Python, no external orchestrator.

## When to use

- You're about to dispatch a review / exploration / architecture subagent
  and you want a ranked recommendation instead of picking from memory.
- You want to fan out to multiple complementary sub-agents but don't want
  to enumerate them by hand.
- You're writing a new skill and want it to delegate to the "right"
  sub-agent without hardcoding the choice.

Don't use for:
- Small/trivial tasks (pick the sub-agent directly — overhead not worth it).
- Bug fixes (the `bug-fix` skill is already a dedicated pipeline).

## How it works

1. Gather the task description (required) and optionally a list of file
   paths the task touches.
2. Call the dispatcher:

   ```bash
   python scripts/dispatch.py \
       --task "audit this migration for concurrent-write safety" \
       --registry reviewer-registry.json \
       alembic/versions/0042_add_column.py
   ```

3. The dispatcher emits JSON:

   ```json
   {
     "task_description": "...",
     "shape": "review",
     "file_paths": ["alembic/..."],
     "picks": [
       {
         "agent_id": "migration-reviewer",
         "subagent_type": "migration-reviewer",
         "model": "sonnet",
         "cascade_tier": 3,
         "confidence": 0.85,
         "rationale": "matched 1/1 files by glob; description overlap=0.22"
       },
       ...
     ]
   }
   ```

4. Dispatch the top-K picks via the `Agent` tool, in one message with
   parallel tool-use blocks (see the `dispatching-parallel-agents` skill).

## Registry schema

The dispatcher reads `reviewer-registry.json` as-is. All existing fields
(id, description, tier, cascade_tier, file_patterns, subagent_type, model)
are honored. Two optional fields extend the registry without breaking it:

- `strengths: [str]` — agent-authored keyword list that supplements
  `description` for ranking.
- `shape: "review" | "explore" | "architect" | "fix" | "grade"` — explicit
  task-shape hint. Agents without this default to REVIEW if they have a
  reviewer `tier`, else UNKNOWN.

Adding agents that aren't reviewers (e.g. an explorer) is as simple as:

```json
{
  "id": "code-explorer",
  "description": "Deep codebase exploration and dependency mapping",
  "subagent_type": "feature-dev:code-explorer",
  "model": "sonnet",
  "shape": "explore",
  "strengths": ["dependency", "trace", "execution path"]
}
```

## Ranking signal

Confidence is the sum of:
- **0.5** if any `file_patterns` match any provided file path.
- **0.5 × description-overlap** (Jaccard-ish on tokenized description +
  strengths vs task description, stopwords removed).
- **+0.1** for `always`-tier reviewers when the task is REVIEW (baseline).
- **+0.05** for agents whose explicit `shape` matches the task shape.

Agents that score 0 are dropped. The top-K picks are returned sorted by
confidence descending.

## Dispatching the picks

Once you have picks, dispatch them in a single parallel Agent-tool message:

```
# For each pick in picks[:k], emit an Agent tool-use block with
# subagent_type=pick.subagent_type. Inject memory per the
# memory-injection skill before any pick that touches project code.
```

## Limits (read before trusting)

- Classification is keyword-heuristic. An ambiguous task ("check this")
  lands in UNKNOWN — still useful for finding shape-hinted agents, but the
  baseline boosts don't fire. When classification is wrong, fall back to
  explicit delegation.
- Dispatcher has no memory. Prompt-variant A/B (`scripts/prompt-tracker.py`)
  remains the path for optimizing *which* variant of a given sub-agent to
  use — dispatch picks the sub-agent; the tracker picks its prompt.
- No LLM call. Ranking is deterministic and cheap. If the registry
  descriptions are terse, scores will be noisy — write richer descriptions
  or add `strengths`.
````

## Acceptance criteria before merging to claude-skills

- [ ] Dispatcher script has tests (done — see `tests/test_dispatch.py`).
- [ ] Integration test against the real `reviewer-registry.json` passes
      (done — `test_dispatch_against_real_registry_for_migration_file`).
- [ ] Phase 6 of the `claude-flow` skill either keeps using
      `select_reviewers.py` unchanged OR explicitly cites the dispatcher —
      we don't want two parallel selection mechanisms drifting apart.
- [ ] At least one non-reviewer agent (`shape: explore` / `shape:
      architect`) added to a registry so dispatch's general-purpose claim
      is exercised in practice, not just in tests.

## Auto-activation gate

The supervisor is only useful when the registry actually offers a choice.
Calling `dispatch()` returns a `dispatch_recommended: bool` that is True
only when ≥2 candidates match the task's shape. Callers (Phase 2, Phase 4,
any future phase) should gate on this:

```bash
# Phase 2/4 shell snippet — skip supervisor when there's nothing to pick among
python scripts/dispatch.py --task "$task" --registry ... --require-multiple
case $? in
  0) # dispatch_recommended: act on the ranked picks
     ;;
  3) # one (or zero) candidate — use it directly, skip the supervisor
     ;;
esac
```

This is the "activate when worth activating" mechanism discussed in the
2026-04-22 decision thread — it means Phase 2 and Phase 4 can adopt the
dispatcher today without it doing anything until a non-reviewer registry
grows to ≥2 agents. Until then, it's a no-op. No cross-repo churn,
self-activating once populated.

## Out of scope

- LLM-based ranking (defer until keyword overlap demonstrably misses).
- Cross-skill delegation policies (who calls the dispatcher — caller's
  choice, not the dispatcher's).
- Learning / feedback loop (separate proposal; would hook
  `prompt-tracker.py` event shape).
