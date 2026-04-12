# Phase 4c: Pre-Implementation Plan Verification

<!-- Loaded: after Phase 4 (full path only) | Dropped: after verification -->

<HARD-GATE>
After user approves the plan and before any implementation begins, verify the plan's factual claims against the actual codebase. The Phase 4b stress-test catches logical issues — this step catches factual inaccuracies (stale file paths, renamed functions, changed API contracts).
</HARD-GATE>

**Skip condition:** Fast path, clone path, and lite path skip this. Only runs on the Full workflow path where there's a meaningful gap between exploration and implementation.

---

## File Path Verification

The executor (Sonnet) runs a mechanical verification pass — no subagent needed:

```
For each file path in the plan:
  → Does the file exist? (glob/ls)
  → Are the referenced functions/classes/methods actually in that file? (grep)
  → If a file is listed as "create new": does a file with that name already exist?

For each pattern claim ("follows existing X pattern"):
  → Grep to confirm the pattern exists in the referenced location
  → If the pattern was discovered in Phase 2 but the file has since changed
    (unlikely but possible in multi-session work), flag it

For each API contract claim (endpoint signatures, model fields, service methods):
  → Verify the signature/fields exist as described
  → Check parameter types and return types match

For integration points:
  → Verify the interface hasn't changed since Phase 2 exploration
  → If another session's work landed between Phase 2 and now (e.g., a merged PR),
    check for breaking changes in shared interfaces
```

<!-- Task taxonomy (types + dependency types) defined in writing-plans/SKILL.md. Keep in sync. -->

---

## Requirements Coverage Mapping

Cross-reference `$requirements` (from Phase 3) against `$plan` to catch gaps before implementation:

```
REQUIREMENTS COVERAGE MAP:

For each acceptance criterion in $requirements:
  → List which task(s) cover it (by task ID + type)
  → If covered by a shared_prerequisite only: flag WARNING
    (prerequisites enable but don't verify user-facing behavior)
  → If not covered by any task: flag UNCOVERED

Summary table format:
  AC-1: "WHEN user searches THEN results filter" → T3 (value_unit) ✓
  AC-2: "WHEN no results THEN empty state shown"  → T3 (value_unit) ✓
  AC-3: "WHEN API fails THEN error message"       → UNCOVERED ✗
```

---

## Scope Boundary Enforcement

```
SCOPE BOUNDARY ENFORCEMENT:
  For each scope boundary (OUT items) in $requirements:
    → Scan task titles + file lists for overlap
    → If any task implements something marked OUT: flag SCOPE CREEP
```

---

## Edge Case Coverage Check

```
EDGE CASE COVERAGE:
  For each edge case in $requirements:
    → Must map to at least one test skeleton (Phase 4d) or explicit test note
    → If missing: flag UNTESTED EDGE CASE
```

---

## Task Granularity Check

```
TASK GRANULARITY CHECK:
  For each task in $plan:
    → If type is value_unit and spans 3+ unrelated service boundaries: flag TOO LARGE
    → If type is value_unit and has no independent acceptance criterion: flag TOO SMALL
    → If type is shared_prerequisite and only one task depends on it: flag UNNECESSARY SPLIT
```

---

## Outcome Actions

- **All mapped, no flags** → Proceed to Phase 4d (test skeletons) or Phase 5.
- **1-2 minor flags** (e.g., one debatable TOO SMALL) → Log and proceed.
- **Any UNCOVERED criterion or SCOPE CREEP** → Present gaps to user, revise plan, get re-approval.
- **Multiple granularity flags** → Present recommendations (split/merge specific tasks), revise plan, get re-approval.
- **Minor mismatches** (renamed variable, moved function) → Fix the plan silently. Log the corrections.
- **Material mismatches** (deleted file, changed API contract, restructured module) → Re-present the affected plan steps to the user with corrections. Get re-approval before proceeding.

**Why this exists:** Plans are drafted against Phase 2 exploration findings. Between exploration and implementation, the codebase can drift (especially in multi-session work or when other contributors merge changes). A 30-60 second mechanical check prevents building on false assumptions — the most expensive kind of bug to find in Phase 6.
