---
name: writing-plans
description: Use when you have a spec or requirements for a multi-step task, before touching code
---

# Writing Plans

## Overview

Write comprehensive implementation plans assuming the engineer has zero context for our codebase and questionable taste. Document everything they need to know: which files to touch for each task, code, testing, docs they might need to check, how to test it. Give them the whole plan as bite-sized tasks. DRY. YAGNI. TDD. Frequent commits.

Assume they are a skilled developer, but know almost nothing about our toolset or problem domain. Assume they don't know good test design very well.

**Announce at start:** "I'm using the writing-plans skill to create the implementation plan."

**Context:** This should be run in a dedicated worktree (created by brainstorming skill).

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md` (project-local, git-tracked)

**Plan location priority:** Check `docs/plans/` in the project first, then `~/.claude/plans/` as fallback. To enable project-local plan storage for Claude Code's built-in plan mode, add `"plansDirectory": "docs/plans"` to your project's `.claude/settings.json`.

## Bite-Sized Task Granularity

**Each step is one action (2-5 minutes):**
- "Write the failing test" - step
- "Run it to make sure it fails" - step
- "Implement the minimal code to make the test pass" - step
- "Run the tests and make sure they pass" - step
- "Commit" - step

## Plan Document Header

**Every plan MUST start with this header:**

```markdown
# [Feature Name] Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

**Ruled Out:** [Approaches considered and rejected during design — prevents re-exploration]
- <approach> — <why rejected>

---
```

## Task Structure

````markdown
### Task N: [Component Name]
**Type:** value_unit | shared_prerequisite | adr
**Depends on:** T2 (data), T4 (knowledge) | none

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Test: `tests/exact/path/to/test.py`

**Step 1: Write the failing test**

```python
def test_specific_behavior():
    result = function(input)
    assert result == expected
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/path/test.py::test_name -v`
Expected: FAIL with "function not defined"

**Step 3: Write minimal implementation**

```python
def function(input):
    return expected
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/path/test.py::test_name -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/path/test.py src/path/file.py
git commit -m "feat: add specific feature"
```
````

## Task Types

| Type | When | Example |
|------|------|---------|
| `value_unit` | Delivers one coherent, independently verifiable outcome | "Add tenant search endpoint" |
| `shared_prerequisite` | 2+ later tasks depend on this at a shared boundary | "Create base service class with audit logging" |
| `adr` | Technical decision that constrains multiple tasks | "Choose between WebSocket and SSE for real-time updates" |

## Dependency Types

| Type | Meaning | Parallelizable? |
|------|---------|-----------------|
| `data` | Needs schema/contract/interface from predecessor | No — must complete first |
| `build` | Needs compiled output or deployed artifact | No — must complete first |
| `knowledge` | Benefits from insights but can proceed with assumptions | Yes — record assumptions |

## Task Ordering

1. `shared_prerequisite` tasks first
2. `adr` tasks next
3. `value_unit` tasks in dependency order
4. Tasks with only `knowledge` dependencies are parallelizable — note this explicitly in the plan

## Granularity Criteria

Right-size each task using these indicators:

- **Too large → split:** spans unrelated service boundaries, mixed concerns in acceptance criteria, would need 2+ independent design docs
- **Too small → merge:** no independent acceptance criterion, only verifiable as part of parent task, config-only change meaningless without parent
- **Right-sized:** single service boundary or defined cross-service interaction, at least one independently verifiable acceptance criterion, dependency depth ≤ 2

## Remember
- Exact file paths always
- Complete code in plan (not "add validation")
- Exact commands with expected output
- Reference relevant skills with @ syntax
- DRY, YAGNI, TDD, frequent commits

## Gate Validation: Verify Every Script/Command Path Against the Target Repo

Before handoff, enumerate every shell command and script path the plan references for gates, tests, or CI, and verify each exists in the **target repo** — not in whatever CLAUDE.md happens to be resident in context. Cross-project command import is a real failure mode: global CLAUDE.md may document `./scripts/quick_ci.sh`, `make test`, `npm run verify`, etc. from a different project, and a plan authored with that CLAUDE.md resident will quietly carry those commands into an unrelated codebase where they do not exist.

**Checklist before handoff:**

```bash
# For every script referenced in the plan, verify it exists in the target repo:
TARGET_REPO=/path/to/target/repo
for cmd in ./scripts/quick_ci.sh ./scripts/validate_all.sh ./scripts/release.py; do
    [ -x "$TARGET_REPO/$cmd" ] || echo "MISSING: $cmd"
done

# For every bare binary (pytest, npm test, cargo check, make), verify either:
#   - it is on PATH on a clean shell, or
#   - it is documented in the target repo's README/CLAUDE.md
command -v pytest >/dev/null || echo "MISSING binary: pytest"
```

If any commands are missing, either:
1. Replace them with their target-repo equivalents (check the target repo's `README.md`, `package.json` scripts, or its own `CLAUDE.md`), or
2. Drop the gate from the plan and substitute a repo-native check (e.g., `pytest` on a Python project with tests, `npm test` on a node project, `cargo check` on a Rust project — whichever the target repo uses).

**Signal for "which CLAUDE.md is this command from":** if a command feels standard but you cannot find the script in the target repo, grep across your global CLAUDE.md files — the command probably belongs to a sibling project. Only cross-project universal tools (git, pytest, npm, cargo, make itself) are safe to carry across projects without verification.

## Execution Handoff

After saving the plan, offer execution choice:

**"Plan complete and saved to `docs/plans/<filename>.md`. Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?"**

**If Subagent-Driven chosen:**
- **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development
- Stay in this session
- Fresh subagent per task + code review

**If Parallel Session chosen:**
- Guide them to open new session in worktree
- **REQUIRED SUB-SKILL:** New session uses superpowers:executing-plans
