---
name: bug-fix
description: Dedicated bug fix orchestrator — Reproduce → Diagnose → Fix (TDD) → Verify. Composes existing debugging skills (investigator, systematic-debugging, TDD) into a streamlined pipeline. Use when fixing bugs, regressions, or unexpected behavior instead of claude-flow.
user-invocable: true
---

# Bug Fix Workflow

## Overview

4-step pipeline for bug fixes that skips the feature-oriented phases (requirements, architecture, parallel exploration) and goes straight to the problem. Composes existing debugging skills into an orchestrated flow.

**Announce:** "Running bug-fix workflow — reproduce, diagnose, fix, verify."

**This is NOT for:** New features, refactors, or improvements. Use `/claude-flow` for those.

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

Dispatch a subset of claude-flow's Phase 6 reviewers on `$diff`:

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

Same pattern as claude-flow Phase 6:

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
| `claude-flow` | Bug-fix is the bug counterpart. Phase 1 Discovery auto-routes bug tasks here. |
| `investigator` | Dispatched in Step 2 for complex bugs. Evidence matrix feeds diagnosis. |
| `systematic-debugging` | Methodology reference. Step 2 follows its "no fixes without root cause" principle. |
| `test-driven-development` | Used in Steps 1 and 3. Failing test first, then fix to green. |
| `memory-injection` | Step 2 checks MEMORY.md for known gotchas before tracing code. |
| `verification-before-completion` | Final gate in Step 4. Same as claude-flow. |
| `shipping-workflow` | After bug-fix completes, user can invoke `/ship` to commit → PR → merge. |

---

## Next Steps

- **Bug is fixed and verified?** Use `/ship` to commit, push, create PR, run review, and merge to main.
- **Fix revealed a deeper architectural issue?** Use `/claude-flow` to address it through the full 6-phase pipeline.
- **Capture what you learned?** Use `/session-learnings` to persist the debugging insights to memory.
