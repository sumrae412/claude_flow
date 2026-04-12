# Phase 4c: Pre-Implementation Plan Verification

<!-- Loaded: after Phase 4 (full path only) | Dropped: after verification -->

<HARD-GATE>
After user approves the plan and before any implementation begins, verify the plan's factual claims against the actual codebase. The Phase 4b stress-test catches logical issues — this step catches factual inaccuracies (stale file paths, renamed functions, changed API contracts).
</HARD-GATE>

**Skip condition:** Fast path, clone path, and lite path skip this. Only runs on the Full workflow path where there's a meaningful gap between exploration and implementation.

---

## File Path Verification (Script-Based — Zero Tokens)

Run the verification script instead of LLM reasoning:

```bash
python scripts/verify_plan.py <plan-file> --project-root . --json
```

The script extracts file paths, function references, and pattern claims from the plan markdown, then verifies each against the codebase using grep/glob. Returns JSON with ok/missing/warning counts.

**Interpret results:**
- Exit 0 (all ok): proceed to coverage mapping below
- Exit 1 (missing refs): read the JSON output, fix plan references for material mismatches, re-present to user for minor ones
- Pattern claims (listed but not auto-verified): spot-check the top 2-3 manually

**What the script checks:**
- File paths: exist for Modify/Test/Read, don't already exist for Create
- Function/class refs: `symbol()` in `file.py` — grep confirms definition exists
- Pattern claims: extracted for manual review (not auto-verifiable)

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
