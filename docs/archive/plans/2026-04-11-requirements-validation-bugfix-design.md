# Design: Requirements Phase, Validation Gate, Bug Fix Workflow

**Created:** 2026-04-11 | **Status:** approved
**Companion:** [Requirements Phase, Validation Gate, Bug Fix Workflow — Implementation Plan](2026-04-11-requirements-validation-bugfix-plan.md)

## Context

Inspired by Pimzino's `claude-code-spec-workflow`, three enhancements to claude-flow's pipeline that catch issues earlier and provide a dedicated path for bug fixes.

## Change 1: Upgrade Phase 3 → "Clarification + Requirements"

### Problem

Phase 3 produces `$requirements` as an informal output — resolved ambiguities and scope boundaries stored loosely in conversation context. This makes downstream validation (Phase 4c, Phase 6) harder because there's no structured artifact to check against.

### Design

Formalize the `$requirements` output contract into a structured document. Phase 3 behavior is unchanged (ask clarifying questions, resolve ambiguities) — but after answers are collected, the executor synthesizes them into this format:

```markdown
## Requirements: <Feature Name>

### User Stories
- As a [role], I want [feature], so that [benefit]

### Acceptance Criteria (EARS format)
- WHEN [trigger] IF [condition] THEN [outcome]

### Scope Boundaries
- IN: [explicitly included]
- OUT: [explicitly excluded]

### Edge Cases (resolved)
- [case]: [resolution]

### Non-Functional Requirements (if applicable)
- Performance: [constraints]
- Backward compat: [notes]
```

### Integration

- Presented to user for approval at the existing Phase 3 gate (no new gate)
- `$requirements` output contract updated to reference this structure
- Phase 4 architecture references acceptance criteria
- Phase 4c validates plan coverage against acceptance criteria
- Phase 6 reviewers receive `$requirements` for adherence checking
- PRP export (optional) references `$requirements` rather than duplicating it
- Workflow paths: Fast/Clone/Lite skip this (unchanged)

### Files Modified

- `skills/code-creation-workflow/SKILL.md` — Phase 3 section rewritten

---

## Change 2: Extend Phase 4c — Requirements Validation Gate

### Problem

Phase 4c verifies factual accuracy (file paths exist, functions are where the plan says). But it doesn't check whether the plan actually covers all requirements — a plan could pass 4c while missing acceptance criteria or violating scope boundaries.

### Design

Add three mechanical checks to the existing Phase 4c verification pass:

**Acceptance Criteria Coverage:**
```
For each acceptance criterion in $requirements:
  → Is there at least one plan step that addresses it?
  → Is there a test skeleton (Phase 4d) or test note for it?
  → If not: flag as UNCOVERED
```

**Scope Boundary Enforcement:**
```
For each scope boundary (OUT items) in $requirements:
  → Does any plan step violate it? (implements something marked OUT)
  → If yes: flag as SCOPE CREEP
```

**Edge Case Coverage:**
```
For each edge case in $requirements:
  → Is it addressed in the plan (either in a step or as a test)?
  → If not: flag as UNTESTED EDGE CASE
```

### Outcome Triage

Same pattern as existing Phase 4c:
- **All covered** → Proceed to Phase 4d / Phase 5
- **Minor gaps** (1-2 criteria clearly handled implicitly) → Log and proceed
- **Material gaps** (missing acceptance criteria, scope creep) → Present to user, revise plan, get re-approval

### Why No Opus Advisor

The check is mechanical — cross-referencing two documents. No judgment calls needed. Keeps Phase 4c cheap and fast.

### Files Modified

- `skills/code-creation-workflow/SKILL.md` — Phase 4c section extended

---

## Change 3: Dedicated Bug Fix Skill (`/bug-fix`)

### Problem

`code-creation-workflow` is optimized for features. Bug fixes get shoehorned into Fast Path (no reproduce-first discipline, no structured diagnosis) or Full Workflow (unnecessary requirements/architecture overhead). No dedicated orchestrator exists.

### Existing Debugging Tools (Composed, Not Replaced)

| Tool | Role in /bug-fix |
|------|-----------------|
| `superpowers:systematic-debugging` | Methodology for Step 2 (Diagnose) — "no fixes without root cause" |
| `engineering:debug` | Alternative methodology for complex debugging sessions |
| `skills/investigator` | Dispatched in Step 2 for complex bugs — evidence matrix output |
| `skills/test-driven-development` | Used in Step 1 (failing test) and Step 3 (fix → green) |
| `skills/memory-injection` | Step 2 checks MEMORY.md for known gotchas |
| Phase 6 reviewers | Dispatched in Step 4 (Verify) — same agents as code-creation-workflow |
| `skills/verification-before-completion` | Final gate before claiming done |

### The 4-Step Pipeline

```
Step 1: REPRODUCE
  → Identify the bug (user description, error log, failing test)
  → Write a failing test that demonstrates the bug (TDD skill)
  → If can't reproduce: investigate logs, check deployment state
  → Output: $bug_report (what, where, reproduction steps, failing test)

Step 2: DIAGNOSE
  → Simple bugs: executor traces root cause directly
  → Complex bugs: dispatch /investigator for evidence matrix
  → Always: check MEMORY.md for known gotchas (memory-injection)
  → Methodology: follows systematic-debugging Phase 1 principles
  → Output: $diagnosis (root cause, affected files, blast radius)

Step 3: FIX (TDD)
  → Failing test exists from Step 1
  → Implement minimal fix → Green
  → Apply defensive patterns (loaded based on affected area)
  → Run full test suite for regressions
  → Output: $diff (the fix)

Step 4: VERIFY
  → Dispatch Phase 6 reviewers on $diff:
    - Tier 1: CodeRabbit (always)
    - Tier 2: Silent Failure Hunter, Security, Test Analyzer (always)
    - Tier 3: Conditional specialists (only if fix touches migrations/async/Google APIs)
    - Skip Tier 4-5 (lightweight checks and design review are feature-oriented)
  → Review-fix-recheck loop (same as code-creation-workflow)
  → verification-before-completion gate
  → Output: verified fix ready for commit
```

### Routing

Two entry points:
1. **Direct invocation:** User runs `/bug-fix` or says "fix this bug"
2. **Auto-routing from code-creation-workflow:** Phase 1 Discovery adds a "Bug Path" that detects bug-fix tasks and redirects to `/bug-fix` instead of proceeding through the feature pipeline

Detection signals for auto-routing:
- User says "fix", "bug", "broken", "regression", "error in"
- User pastes an error message or stack trace
- User references a GitHub issue tagged as a bug

### Context Loading (Lightweight)

No Phase 0 full context load. Instead, load only what the bug area needs:
- CLAUDE.md (always — project boundaries)
- Defensive skill matching the affected area (UI or backend)
- coding-best-practices (always)
- Domain skill only if relevant (e.g., data skill if bug is in a model)

### Files Created

- `skills/bug-fix/SKILL.md` — new skill

### Files Modified

- `skills/code-creation-workflow/SKILL.md` — Phase 1 Discovery gets "Bug Path" routing

---

## Phase Output Contract Updates

| Phase | Output | Change |
|-------|--------|--------|
| Phase 3 | `$requirements` | Now a structured document (user stories, acceptance criteria, scope, edge cases) |
| Phase 4c | verification result | Now includes requirements coverage, scope boundary, and edge case checks |
| `/bug-fix` Step 1 | `$bug_report` | New output (what, where, reproduction, failing test) |
| `/bug-fix` Step 2 | `$diagnosis` | New output (root cause, affected files, blast radius) |
| `/bug-fix` Step 3 | `$diff` | Same format as code-creation-workflow Phase 5 |

## What Does NOT Change

- Phase numbering (no new phases added)
- Phase 2 exploration (unchanged)
- Phase 4 architecture (unchanged, but now references structured $requirements)
- Phase 4d test skeletons (unchanged, but can reference acceptance criteria)
- Phase 5 implementation (unchanged)
- Phase 6 review tiers (unchanged — reused by /bug-fix)
- All existing workflow paths (Fast/Clone/Lite/Full — unchanged)
- PRP export (unchanged, references $requirements)
