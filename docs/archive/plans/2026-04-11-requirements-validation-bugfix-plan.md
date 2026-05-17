# Requirements Phase, Validation Gate, Bug Fix Workflow — Implementation Plan

**Companion:** [Design: Requirements Phase, Validation Gate, Bug Fix Workflow](2026-04-11-requirements-validation-bugfix-design.md)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add structured requirements output to Phase 3, extend Phase 4c with requirements coverage checks, create a standalone `/bug-fix` orchestrator skill, and wire bug-path routing into Phase 1 Discovery.

**Architecture:** Three surgical edits to `skills/code-creation-workflow/SKILL.md` (Phase 1 Discovery, Phase 3, Phase 4c) plus one new file (`skills/bug-fix/SKILL.md`). No new phases, no new dependencies, no structural changes to the pipeline.

**Tech Stack:** Markdown skill files (SKILL.md format with YAML frontmatter)

---

### Task 1: Upgrade Phase 3 — Structured Requirements Output

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md:440-500` (Phase 3: Clarification section)

**Step 1: Read current Phase 3 section**

Read lines 440-500 of `skills/code-creation-workflow/SKILL.md` to confirm exact boundaries.

**Step 2: Replace Phase 3 section**

Replace the Phase 3 section (from `## Phase 3: Clarification (Hard Gate)` through the end of the PRP subsection, stopping before `## Phase 4:`) with the upgraded version below. The key changes are:
- Rename to "Phase 3: Clarification + Requirements (Hard Gate)"
- Add a new "### Step 2: Synthesize Structured Requirements" subsection after the existing clarification Q&A
- Add the `$requirements` document template
- Add a user approval gate for the structured requirements
- Update the PRP export to reference `$requirements` instead of duplicating content

The replacement content for Phase 3:

```markdown
## Phase 3: Clarification + Requirements (Hard Gate)

<HARD-GATE>
All ambiguities must be resolved and requirements formalized before architecture work begins.
</HARD-GATE>

### Step 1: Resolve Ambiguities

Review exploration findings against the original request. Identify **every** underspecified aspect:

- **Edge cases** — What happens when input is empty, duplicated, or malformed?
- **Error handling** — What should the user see when things fail?
- **Integration points** — Which existing systems does this touch?
- **Scope boundaries** — What is explicitly NOT included?
- **Performance** — Will this hit large datasets or high concurrency?
- **Backward compatibility** — Does this change existing behavior?

Present an organized question list to the user. Group questions by category. Wait for answers before proceeding.

**If no ambiguities exist** (rare — usually means the request is very well-specified), state that explicitly and proceed to Step 2.

### Step 2: Synthesize Structured Requirements

After all ambiguities are resolved, synthesize the answers into a structured requirements document. This is the `$requirements` output contract — it flows downstream to Phase 4 (architecture references it), Phase 4c (validates plan coverage against it), and Phase 6 (reviewers check adherence).

**Format:**

```
## Requirements: <Feature Name>

### User Stories
- As a [role], I want [feature], so that [benefit]
(1-5 stories covering the core functionality)

### Acceptance Criteria (EARS format)
- WHEN [trigger] IF [condition] THEN [outcome]
(Every testable behavior — these become the coverage checklist in Phase 4c)

### Scope Boundaries
- IN: [explicitly included]
- OUT: [explicitly excluded]
(OUT items are enforced as scope creep detection in Phase 4c)

### Edge Cases (resolved)
- [case]: [resolution]
(Each resolved edge case from Step 1 — checked for test coverage in Phase 4c)

### Non-Functional Requirements (if applicable)
- Performance: [constraints]
- Backward compat: [notes]
```

**Present to user for approval.** The structured requirements are the contract for everything downstream. If the user provides feedback, revise and re-present.

```
◆ USER APPROVES structured requirements before architecture ◆
```

### Optional: Export Context Packet (PRP)

After requirements are approved, optionally save a **Product Requirement Prompt (PRP)** — a reusable context packet that survives across sessions.

**Trigger conditions** (export if ANY apply):
- Feature is complex enough to span multiple sessions
- User says "save context", "export this", or "I'll continue later"
- Task involves 3+ integration points or schema changes

**PRP format** — write to `plans/PRP-<feature-slug>.md`:

```
# PRP: <Feature Name>
**Created:** <date> | **Status:** ready-for-implementation

## Requirements
(Reference or inline the structured $requirements from Step 2)

## Codebase Intelligence
- **Key files:** <5-10 files from exploration with their roles>
- **Patterns to follow:** <discovered conventions from Phase 2>
- **Integration points:** <systems this touches>

## Constraints & Edge Cases
(Reference the Edge Cases section from $requirements)

## Ruled Out
- <approach/tool/path> — <why it failed or was abandoned>
- <investigation that hit a dead end> — <what was discovered>
<!-- Prevents future sessions from re-exploring dead ends -->

## Implementation Notes
- <API docs fetched (if applicable)>
- <defensive patterns required>
- <test strategy hints>
```

**How it's consumed:** Phase 1 Discovery detects PRP files via the PLAN PATH branch. A PRP provides richer context than a bare plan — it includes the codebase intelligence that would otherwise require re-running Phase 2 exploration.

If not triggered, skip — most single-session features don't need this.
```

**Step 3: Update the Phase Output Contracts table**

Find the Phase output contracts table (around line 800). Update the Phase 3 row from:

```
| Phase 3 | `$requirements` | Resolved requirements, edge cases, scope boundaries | Phases 4, 5, reviewer prompts |
```

to:

```
| Phase 3 | `$requirements` | Structured document: user stories, acceptance criteria (EARS), scope boundaries (IN/OUT), resolved edge cases, non-functional requirements | Phases 4, 4c, 5, reviewer prompts |
```

**Step 4: Verify the edit**

Grep for "Phase 3" in SKILL.md and confirm:
- Section header says "Clarification + Requirements"
- Step 1 (Resolve Ambiguities) and Step 2 (Synthesize Structured Requirements) both exist
- The `$requirements` format template is present
- User approval gate exists after Step 2

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: formalize Phase 3 requirements output with structured document"
```

---

### Task 2: Extend Phase 4c — Requirements Coverage Checks

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md:646-679` (Phase 4c section)

**Step 1: Read current Phase 4c section**

Read lines 640-680 of `skills/code-creation-workflow/SKILL.md` to confirm exact content after Task 1's edits.

**Step 2: Add requirements validation checks to Phase 4c**

After the existing verification code block (the one ending with `check for breaking changes in shared interfaces`), and before the `**Outcome:**` section, insert the new requirements coverage checks:

```markdown
### Requirements Coverage Validation

Cross-reference `$requirements` (from Phase 3) against `$plan` to catch gaps before implementation:

```
ACCEPTANCE CRITERIA COVERAGE:
  For each acceptance criterion in $requirements:
    → Is there at least one plan step that addresses it?
    → Is there a test skeleton (Phase 4d) or test note for it?
    → If not: flag as UNCOVERED CRITERION

SCOPE BOUNDARY ENFORCEMENT:
  For each scope boundary (OUT items) in $requirements:
    → Does any plan step implement something marked OUT?
    → If yes: flag as SCOPE CREEP

EDGE CASE COVERAGE:
  For each edge case in $requirements:
    → Is it addressed in the plan (either in a step or as a test)?
    → If not: flag as UNTESTED EDGE CASE
```
```

**Step 3: Update the Outcome section**

Replace the existing Outcome section with an expanded version that includes requirements validation results:

Old:
```
**Outcome:**
- **All claims verified** → Proceed to Phase 4d (test skeletons) or Phase 5.
- **Minor mismatches** (renamed variable, moved function) → Fix the plan silently. Log the corrections.
- **Material mismatches** (deleted file, changed API contract, restructured module) → Re-present the affected plan steps to the user with corrections. Get re-approval before proceeding.
```

New:
```
**Outcome:**
- **All claims verified + all requirements covered** → Proceed to Phase 4d (test skeletons) or Phase 5.
- **Minor mismatches** (renamed variable, moved function) → Fix the plan silently. Log the corrections.
- **Minor coverage gaps** (1-2 criteria clearly handled implicitly by existing plan steps) → Log and proceed.
- **Material mismatches** (deleted file, changed API contract, restructured module) → Re-present the affected plan steps to the user with corrections. Get re-approval before proceeding.
- **Material coverage gaps** (uncovered acceptance criteria, scope creep detected, untested edge cases) → Present gaps to user, revise plan to address them, get re-approval before proceeding.
```

**Step 4: Verify the edit**

Grep for "ACCEPTANCE CRITERIA COVERAGE" and "SCOPE CREEP" in SKILL.md to confirm both blocks exist within Phase 4c.

**Step 5: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: extend Phase 4c with requirements coverage validation"
```

---

### Task 3: Create Bug Fix Skill

**Files:**
- Create: `skills/bug-fix/SKILL.md`

**Step 1: Create the directory**

```bash
mkdir -p skills/bug-fix
```

**Step 2: Write the skill file**

Create `skills/bug-fix/SKILL.md` with the following content:

```markdown
---
name: bug-fix
description: Dedicated bug fix orchestrator — Reproduce → Diagnose → Fix (TDD) → Verify. Composes existing debugging skills (investigator, systematic-debugging, TDD) into a streamlined pipeline. Use when fixing bugs, regressions, or unexpected behavior instead of code-creation-workflow.
user-invocable: true
---

# Bug Fix Workflow

## Overview

4-step pipeline for bug fixes that skips the feature-oriented phases (requirements, architecture, parallel exploration) and goes straight to the problem. Composes existing debugging skills into an orchestrated flow.

**Announce:** "Running bug-fix workflow — reproduce, diagnose, fix, verify."

**This is NOT for:** New features, refactors, or improvements. Use `/code-creation-workflow` for those.

---

## Context Loading (Lightweight)

No full Phase 0 context load. Load only what the bug area needs:

1. **CLAUDE.md** — always (project boundaries and terminology)
2. **coding-best-practices** — always (baseline reference)
3. **Defensive skill** matching the affected area:
   - UI bug → `defensive-ui-flows`
   - Backend bug → `defensive-backend-flows`
   - Both → load both
4. **Domain skill** — only if relevant (e.g., data skill if bug is in a model, API skill if bug is in a route)
5. **MEMORY.md** — check for known gotchas in the affected area (memory-injection)

---

## Step 1: Reproduce

<HARD-GATE>
A bug without a reproduction is a guess. Write the failing test before investigating.
</HARD-GATE>

### Process

1. **Understand the symptom**
   - User description, error message, stack trace, or failing behavior
   - If user provides a GitHub issue, read it for reproduction steps
   - If user provides logs, extract the error chain

2. **Write a failing test** (TDD — Red phase)
   - The test demonstrates the bug — it should FAIL on current code
   - Test the behavior, not the implementation
   - If the bug is in UI, write a test that exercises the relevant endpoint/service instead
   - Use existing test patterns from the project (read a nearby test file for conventions)

3. **Run the test — confirm it fails**
   - If it passes: the test doesn't capture the bug. Revise.
   - If it errors on setup: fix the test setup, not the implementation.

4. **If reproduction is impossible:**
   - Check deployment logs (`railway get-logs`, app logs, error tracking)
   - Check if the bug is environment-specific (local vs staging vs prod)
   - If still can't reproduce: tell the user and ask for more information. Don't guess.

### Output: $bug_report

```
Bug: <one-line description>
Symptom: <what's happening>
Expected: <what should happen>
Reproduction: <test name and file path>
Affected area: <file paths, endpoints, or feature area>
```

---

## Step 2: Diagnose

<HARD-GATE>
No fixes without root cause. Follows the systematic-debugging principle: "symptom fixes are failure."
</HARD-GATE>

### Process

1. **Check MEMORY.md for known gotchas**
   - Read MEMORY.md index for entries relevant to the bug area
   - Known gotchas (e.g., `is_primary_contact` not `is_primary`, `datetime.utcnow()` deprecation) save diagnosis time
   - If a gotcha matches: note it and verify against the actual code

2. **Trace from symptom to root cause**

   **Simple bugs** (single file, clear error message):
   - Read the file where the error occurs
   - Trace the call chain: entry point → handler → service → model
   - Identify where behavior diverges from expectation

   **Complex bugs** (multi-file, unclear cause, environment-specific):
   - Dispatch the **investigator** skill for structured evidence collection
   - The investigator collects from 6 source types (code, git, config, deps, docs, external) and outputs an evidence matrix
   - Use the evidence matrix to form hypotheses

3. **Assess blast radius**
   - What else might be affected by the root cause?
   - Are there other callers of the broken code path?
   - Could the fix have side effects?

### Output: $diagnosis

```
Root cause: <what's actually wrong and why>
Affected files: <specific file paths>
Blast radius: <what else might be affected>
Fix approach: <1-2 sentence description of the minimal fix>
```

---

## Step 3: Fix (TDD)

### Process

1. **Failing test already exists** (from Step 1)
   - If diagnosis revealed the test needs adjusting, update it now
   - Re-run to confirm it still fails

2. **Implement the minimal fix**
   - Fix the root cause identified in Step 2 — nothing more
   - Apply defensive patterns:
     - Backend: no silent swallows, guard clauses, log or re-raise
     - UI: guard feedback, state flags, overlay inline
   - Follow existing code patterns (read the surrounding code)

3. **Run the failing test — confirm it passes** (Green phase)

4. **Run the full test suite — check for regressions**
   - If regressions: the fix has side effects. Revisit the blast radius from $diagnosis.
   - Fix regressions before proceeding.

5. **Run static analysis on changed files**
   ```
   ruff check <changed-files>        # Python lint
   semgrep --severity ERROR <files>   # Semantic analysis (if configured)
   ```
   Fix any ERROR-level issues before proceeding.

### Output: $diff

The git diff of all changes (fix + test).

---

## Step 4: Verify

### Review Dispatch

Dispatch a subset of code-creation-workflow's Phase 6 reviewers on `$diff`:

**Always run:**

| Agent | `subagent_type` | Model | Focus |
|-------|-----------------|-------|-------|
| CodeRabbit | `coderabbit:code-reviewer` | **sonnet** | Bugs, logic errors, conventions, patterns |
| Silent Failure Hunter | `pr-review-toolkit:silent-failure-hunter` | **sonnet** | Swallowed errors, empty catches |
| Security Reviewer | `security-reviewer` | **sonnet** | Auth, data exposure, injection |
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | **sonnet** | Test coverage gaps, untested error paths |

**Conditional (only if fix touches these areas):**

| Condition | Agent | `subagent_type` | Model |
|-----------|-------|-----------------|-------|
| Alembic migration modified | Migration Reviewer | `migration-reviewer` | **sonnet** |
| Google API code modified | Google API Reviewer | `google-api-reviewer` | **sonnet** |
| Async code paths modified | Async Reviewer | `async-reviewer` | **sonnet** |

**Skipped:** Tier 4 lightweight checks (defensive-pattern-verifier, invariant-checker) and Tier 5 design review — these are feature-oriented and add noise for targeted fixes.

### Review-Fix-Recheck Loop

Same pattern as code-creation-workflow Phase 6:

```
For each HIGH+ finding:
  1. Fix the issue
  2. Re-run the SPECIFIC reviewer that flagged it
  3. Did it pass?
     YES → mark resolved, next finding
     NO  → fix again (max 3 iterations)
     3 failures → escalate to user
```

### Verification Gate

Before claiming done, run `verification-before-completion`:
- All tests pass
- No unresolved HIGH+ review findings
- The original failing test from Step 1 now passes
- No regressions in the full test suite

### Output

Verified fix ready for commit. Present summary to user:
```
Bug: <description>
Root cause: <from $diagnosis>
Fix: <what was changed>
Tests: <passing count> passing, <new count> new
Review: <findings summary — resolved/escalated>
```

---

## Relationship to Other Skills

| Skill | Relationship |
|-------|-------------|
| `code-creation-workflow` | Bug-fix is the bug counterpart. Phase 1 Discovery auto-routes bug tasks here. |
| `investigator` | Dispatched in Step 2 for complex bugs. Evidence matrix feeds diagnosis. |
| `systematic-debugging` | Methodology reference. Step 2 follows its "no fixes without root cause" principle. |
| `test-driven-development` | Used in Steps 1 and 3. Failing test first, then fix to green. |
| `memory-injection` | Step 2 checks MEMORY.md for known gotchas before tracing code. |
| `verification-before-completion` | Final gate in Step 4. Same as code-creation-workflow. |
| `shipping-workflow` | After bug-fix completes, user can invoke `/ship` to commit → PR → merge. |
```

**Step 3: Verify the skill file**

Check that the file exists and has valid YAML frontmatter:
```bash
head -5 skills/bug-fix/SKILL.md
```

Expected:
```
---
name: bug-fix
description: Dedicated bug fix orchestrator...
user-invocable: true
---
```

**Step 4: Commit**

```bash
git add skills/bug-fix/SKILL.md
git commit -m "feat: add dedicated bug-fix orchestrator skill"
```

---

### Task 4: Add Bug Path Routing to Phase 1 Discovery

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md:239-303` (Phase 1 Discovery section)

**Step 1: Read current Phase 1 Discovery section**

Read lines 239-303 to confirm exact content after Tasks 1-2 edits.

**Step 2: Add Bug Path to the Discovery flowchart**

In the ASCII flowchart (the block starting with `User says "implement X"`), insert a new check **before** the "Is this a SMALL change?" check:

```
User says "implement X" / "fix Y"
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │ Is this a BUG FIX?                           │
   │ (error report, regression, "broken",         │
   │  stack trace, bug issue reference)            │
   │                                               │
   │ YES → BUG PATH                                │
   │   Invoke /bug-fix skill                       │
   │   (Reproduce → Diagnose → Fix → Verify)       │
   │                                               │
```

This goes at the top of the flowchart, before the existing FAST PATH check. The rest of the flowchart (FAST/PLAN/CLONE/LITE/FULL) remains unchanged.

**Step 3: Add Bug Path to the path criteria list**

After the existing path criteria, add:

```
- **Bug path:** Error report, regression, stack trace, "fix this bug", GitHub issue tagged as bug. Routes to `/bug-fix` skill — the dedicated bug fix orchestrator.
```

**Step 4: Add Bug Path row to the Artifact Requirements table**

Add a new row to the table at lines ~298-303:

```
| **Bug** | 1-5 | No | No | No | No (test in Step 1) | Tier 1-3 (via /bug-fix) |
```

**Step 5: Verify the edit**

Grep for "BUG PATH" and "Bug path" in SKILL.md to confirm both the flowchart entry and the criteria entry exist.

**Step 6: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: add Bug Path routing to Phase 1 Discovery"
```

---

### Task 5: Final Verification Pass

**Files:**
- Read: `skills/code-creation-workflow/SKILL.md` (verify all edits coherent)
- Read: `skills/bug-fix/SKILL.md` (verify standalone correctness)

**Step 1: Verify Phase 3 changes**

```bash
grep -n "Phase 3" skills/code-creation-workflow/SKILL.md
```

Expected: "Phase 3: Clarification + Requirements (Hard Gate)" appears once.

**Step 2: Verify Phase 4c changes**

```bash
grep -n "ACCEPTANCE CRITERIA COVERAGE\|SCOPE CREEP\|UNTESTED EDGE CASE" skills/code-creation-workflow/SKILL.md
```

Expected: All three labels appear within the Phase 4c section.

**Step 3: Verify Bug Path routing**

```bash
grep -n "BUG PATH\|Bug path\|bug-fix" skills/code-creation-workflow/SKILL.md
```

Expected: Bug Path appears in flowchart, criteria list, and artifact table.

**Step 4: Verify bug-fix skill**

```bash
grep -n "Step 1:\|Step 2:\|Step 3:\|Step 4:" skills/bug-fix/SKILL.md
```

Expected: All 4 steps (Reproduce, Diagnose, Fix, Verify) present.

**Step 5: Verify output contracts table consistency**

Read the Phase Output Contracts table and confirm Phase 3 row references structured format and Phase 4c row includes "requirements coverage."

**Step 6: Run any project linting/validation if available**

```bash
./scripts/quick_ci.sh 2>/dev/null || echo "No CI script or not applicable"
```

**Step 7: No commit needed — this is verification only**
