# Quality Gate, Task Taxonomy, and Coverage Mapping

> **Inspired by:** [shinpr/linear-prism](https://github.com/shinpr/linear-prism) — structured quality gates, task typing, and dependency classification.

**Goal:** Sharpen the existing Phase 3/4/5 pipeline by adding requirement quality scoring, typed tasks with classified dependencies, and exhaustive coverage mapping.

**Approach:** Surgical Enhancement (Approach A) — modify 3 existing skills in-place, no new phases or skills.

**Ruled Out:**
- Modular reference files (Approach B) — adds indirection for what's essentially inline protocol additions
- New decomposition skill (Approach C) — violates compose-don't-replace, adds pipeline complexity
- Linear integration — project-tracker-specific, not needed
- Design Doc boundary scoping per service — adds complexity our pipeline doesn't need yet

---

## Change 1: Phase 3 Quality Gate

**File:** `skills/code-creation-workflow/SKILL.md`, Phase 3
**Placement:** Between Step 1 (resolve ambiguities) and Step 2 (synthesize requirements)

After ambiguities are resolved but before writing `$requirements`, score the resolved input on 4 axes:

### Quality Scoring Criteria

| Axis | Pass | Fail |
|------|------|------|
| **Objective Clarity** | Deliverable stated in one sentence as an outcome | Vague ("improve X"), unmeasurable, or describes activity not outcome |
| **Service Scope** | Affected services/components/files identifiable | No concrete files, modules, or systems can be named |
| **Testability** | Every behavior has a verifiable condition | Any requirement uses "should work well", "be fast", or other untestable language |
| **Completeness** | Edge cases, error paths, integration points addressed | Known edge cases from Phase 2 exploration are unresolved |

### Gate Logic

- **All pass** -> proceed to synthesize `$requirements`
- **Any fail** -> present failures to user with specific questions to resolve them. Loop until all pass.

This is NOT a new user approval gate. It's a pre-check that ensures the existing approval gate (end of Phase 3) is meaningful. Catching "vague objective" here prevents wasted architecture work in Phase 4.

---

## Change 2: Task Taxonomy in Plan Format

**File:** `skills/writing-plans/SKILL.md`, task template section

### New Task Header Fields

Each task gains `Type` and `Depends on` (with typed edges):

```markdown
### Task N: [Component Name]
**Type:** value_unit | shared_prerequisite | adr
**Depends on:** T2 (data), T4 (knowledge) | none
**Files:** ...
**Step 1:** ...
```

### Task Types

| Type | When | Example |
|------|------|---------|
| `value_unit` | Delivers one coherent, independently verifiable outcome | "Add tenant search endpoint" |
| `shared_prerequisite` | 2+ later tasks depend on this at a shared boundary | "Create base service class with audit logging" |
| `adr` | Technical decision that constrains multiple tasks | "Choose between WebSocket and SSE for real-time updates" |

### Dependency Types

| Type | Meaning | Parallelizable? |
|------|---------|-----------------|
| `data` | Needs schema/contract/interface from predecessor | No |
| `build` | Needs compiled output or deployed artifact | No |
| `knowledge` | Benefits from insights but can proceed with assumptions | Yes (record assumptions) |

### Granularity Criteria

Added as guidance in writing-plans for right-sizing tasks:

- **Too large (split):** spans unrelated service boundaries, mixed concerns in acceptance criteria, would need 2+ independent design docs
- **Too small (merge):** no independent acceptance criterion, only verifiable as part of parent task, config-only change meaningless without parent
- **Right-sized:** single service boundary or defined cross-service interaction, at least one independently verifiable acceptance criterion, dependency depth <= 2

### Ordering Rule

1. `shared_prerequisite` tasks first
2. `adr` tasks next
3. `value_unit` tasks in dependency order
4. Tasks with only `knowledge` dependencies marked as parallelizable

### Impact on Phase 5

`subagent-driven-development` already dispatches independent tasks in parallel. Typed dependencies make this explicit:
- `data`/`build` edges -> sequential execution
- `knowledge`-only edges -> concurrent dispatch (record assumptions)

---

## Change 3: Enhanced Coverage Mapping in Phase 4c

**File:** `skills/code-creation-workflow/SKILL.md`, Phase 4c section

Replaces the existing loose coverage check with a structured, exhaustive mapping.

### Coverage Mapping Protocol

```
REQUIREMENTS COVERAGE MAP:

For each acceptance criterion in $requirements:
  -> List which task(s) cover it (by task ID + type)
  -> If covered by shared_prerequisite only: flag WARNING
     (prerequisites enable but don't verify user-facing behavior)
  -> If not covered by any task: flag UNCOVERED

Summary table:
  AC-1: "WHEN user searches THEN results filter" -> T3 (value_unit) checkmark
  AC-2: "WHEN no results THEN empty state shown"  -> T3 (value_unit) checkmark
  AC-3: "WHEN API fails THEN error message"       -> UNCOVERED

SCOPE BOUNDARY ENFORCEMENT:
  For each OUT item in $requirements:
    -> Scan task titles + file lists for overlap
    -> Flag SCOPE CREEP if any task implements excluded scope

EDGE CASE COVERAGE:
  For each edge case in $requirements:
    -> Must map to at least one test skeleton (Phase 4d) or explicit test note
    -> Flag UNTESTED if missing

TASK GRANULARITY CHECK:
  For each task in $plan:
    -> If value_unit spans 3+ unrelated service boundaries: flag TOO LARGE
    -> If value_unit has no independent acceptance criterion: flag TOO SMALL
    -> If shared_prerequisite and only one task depends on it: flag UNNECESSARY SPLIT
```

### Outcome Logic

- **All mapped, no flags** -> proceed
- **1-2 minor flags** (e.g., one debatable TOO SMALL) -> log and proceed
- **Any UNCOVERED criterion or SCOPE CREEP** -> present to user, revise plan, re-approve
- **Multiple granularity flags** -> present recommendations (split/merge specific tasks), revise plan

### What This Adds Over Current Phase 4c

Current Phase 4c checks file paths and API contracts exist (factual accuracy). This enhancement adds:
- Structured requirement-to-task traceability (every AC maps to a task)
- Granularity validation using task types
- Scope creep scanning against the OUT list from Phase 3
- Prerequisite-only coverage warnings

---

## Summary of Changes

| Skill File | Change | Size |
|-----------|--------|------|
| `code-creation-workflow/SKILL.md` Phase 3 | Add quality gate scoring + block/clarify/proceed | ~30 lines |
| `writing-plans/SKILL.md` | Add task type + dependency type to format, granularity guidance, ordering rule | ~50 lines |
| `code-creation-workflow/SKILL.md` Phase 4c | Replace loose coverage check with structured mapping + granularity check | ~40 lines |

No new files. No new phases. No new skills. Three surgical edits to existing skills.
