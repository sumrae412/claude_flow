---
name: smart-exploration
description: Task-typed exploration prompts for Phase 2. Classifies the task and returns tuned subagent prompts instead of generic ones. Used internally by code-creation-workflow.
user-invocable: false
---

# Smart Exploration

## Overview

This skill is used internally by `code-creation-workflow` during **Phase 2 (Exploration)**. Rather than dispatching generic explorer subagents, it first classifies the task type, then selects targeted prompts from the prompt library that are tuned for that category of work.

The result is exploration that surfaces the exact context each task type needs — rather than broadly scanning the codebase and hoping the right patterns turn up.

---

## How Phase 2 Uses This Skill

`code-creation-workflow` dispatches **2–3 explorer subagents** in parallel during Phase 2. Before constructing those subagent prompts, consult this skill to:

1. **Classify** the task into one of the categories below.
2. **Select variants** using the prompt optimization system (see Variant Selection below). If the tracker is unavailable, fall back to `prompt-library.md` directly.
3. **Substitute** any `[FEATURE]`, `[AREA]`, or `[TARGET]` placeholders with specifics from the user's request.
4. **Dispatch** those prompts as the Phase 2 Agent tool calls.
5. **Record** which variant IDs were dispatched (needed for outcome tracking).

### Variant Selection

The prompt optimization system A/B tests explorer prompts to find which wording produces the best exploration results. Before dispatching:

```bash
# Select variant for Explorer A
python3 ~/.claude/scripts/prompt-tracker.py select explorer <category> A

# Select variant for Explorer B
python3 ~/.claude/scripts/prompt-tracker.py select explorer <category> B
```

Each returns `{"variant_id": "...", "prompt": "..."}`. Use the returned prompt instead of the one in prompt-library.md. Record the variant_id so outcomes can be attributed later.

**After Phase 2 completes:** Record which files each explorer found. Store this list — it will be compared against files actually used in Phase 5 to compute the exploration quality score.

**After Phase 5 completes:** Record outcome via:

```bash
python3 ~/.claude/scripts/prompt-tracker.py record '{
  "session_id": "<session>",
  "task_category": "<category>",
  "variant_id": "<variant_id>",
  "explorer_role": "<A or B>",
  "files_found": ["file1.py", "file2.py"],
  "files_used_in_impl": ["file1.py", "file3.py", "file4.py"],
  "phase5_retries": 2,
  "plan_steps": 8
}'
```

**Fallback:** If `prompt-tracker.py` is not available or errors, use the prompts from `prompt-library.md` directly. The optimization system is additive — the workflow works without it.

If 2 prompts are listed for a category, dispatch both in parallel. If only 1 is listed, dispatch it as a single explorer.

---

## Registry-Informed Variant Selection

When the swarm registry exists at `.claude/swarm/agent-registry.json`, rank prompt variants by `findings_used_rate` before selecting which to dispatch.

1. Check for registry file. If absent, skip to step 4.
2. For each candidate variant in the target category, look up its `variant_id` in the registry (variant IDs are tagged in `prompt-library.md` under each explorer heading).
3. Sort candidates by `findings_used_rate` descending. Dispatch the top-ranked variant as Explorer A and the second-ranked as Explorer B.
4. **Fallback:** If the registry file does not exist, has no entries for this category, or errors on read, use the default ordering from `prompt-library.md` (Explorer A first, Explorer B second).

Registry lookups are read-only during variant selection. Record `dispatched` events after dispatch using the variant_id returned — this is what feeds the registry data used in future selections.

---

## Task Categories

| Category | When to Use |
|----------|-------------|
| `endpoint` | Adding or modifying API routes, controllers, handlers, or REST/GraphQL endpoints |
| `ui` | Frontend or template changes — components, pages, CSS, state management |
| `data` | Models, database migrations, queries, schema changes, ORM relationships |
| `integration` | Connecting to or modifying external APIs, webhooks, third-party services |
| `refactor` | Restructuring existing code without changing behavior — moving, renaming, abstracting |
| `bugfix` | Debugging a defect — tracing an error, unexpected behavior, or regression |
| `config` | Configuration, environment variables, infrastructure, deployment changes |
| `exploration` | Spike, prototype, or proof-of-concept — validate a hypothesis with minimal overhead. Lighter prompts focused on feasibility and key risks rather than full production patterns |
| `general` | Fallback when the task doesn't fit a specific category |

---

## How to Classify

Use both signals together:

1. **The user's request** — look for keywords like "add endpoint", "fix bug", "migrate", "refactor", "config", "component", "API", etc.
2. **Files or areas mentioned** — routes/controllers suggest `endpoint`; templates/components suggest `ui`; models/migrations suggest `data`; external service calls suggest `integration`.

When both signals agree, classification is confident. When they conflict or the request is ambiguous, default to `general`.

**Examples:**

- "Add a `/payments/refund` endpoint" → `endpoint`
- "Fix the broken invoice total calculation" → `bugfix`
- "Add a `refunded_at` column to invoices" → `data`
- "Refactor the auth middleware into a shared utility" → `refactor`
- "Wire up the Stripe webhook handler" → `integration`
- "Update the dashboard summary card component" → `ui`
- "Move the DB connection string to an env var" → `config`
- "Try out a different approach to caching" → `exploration`
- "Spike whether we can use WebSockets for this" → `exploration`
- "Help me understand how this feature works" → `general`

---

## Placeholder Substitution

Each prompt in the library contains one or more placeholders:

- `[FEATURE]` — the specific feature or capability being added/changed
- `[AREA]` — the area of the codebase (e.g., "billing", "dashboard", "auth")
- `[TARGET]` — the specific function, class, or module being refactored or debugged

Always fill these in from the user's request before dispatching. If the request is vague, use the most specific description available (e.g., "the payments module" rather than "some code").

---

## Prompt Library Reference

See `prompt-library.md` in this skill directory for the complete set of subagent dispatch prompts organized by category.

---

## Fallback Behavior

If the category is unclear after reviewing both signals, use the `general` prompts. Do not guess aggressively — a well-scoped general exploration is more useful than a narrowly-scoped exploration aimed at the wrong category.
