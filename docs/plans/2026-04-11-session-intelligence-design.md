# Session Intelligence — 5 Improvements Design

**Date:** 2026-04-11
**Status:** APPROVED

## Overview

Five improvements to claude-flow inspired by academic workflow patterns (plan-first development, orchestrator protocols, exploration sandboxes). Each addresses a gap in the current workflow's ability to preserve decisions, adapt reviewers, and handle experimental work.

## 1. Mid-Session Decision Journal

### Problem
Session-handoff captures state at session end, but design decisions made mid-session (why approach A over B, what tradeoffs were accepted) get lost to context compaction.

### Design
- **New Tier 1 hook:** `decision-journal.sh` on `PostToolUse` for `Edit` and `Write`
- Tracks an edit counter. Every 10 file edits, outputs a reminder prompting Claude to journal decisions to `.claude/session-log.md`
- Session log format:

```markdown
# Session Log — YYYY-MM-DD
## Decisions
- [HH:MM] Chose X over Y because Z
- [HH:MM] Changed approach from A to B after discovering C
## Ruled Out
- Approach X — reason
```

- `session-handoff` updated to read and incorporate `.claude/session-log.md`
- `session-context-loader` surfaces the session log on next session start

### Files
- New: `hooks/tier1/decision-journal.sh`
- Edit: `hooks/hook-registry.json` (add entry)
- Edit: `skills/session-handoff/SKILL.md` (read session-log)
- Edit: `hooks/tier1/session-context-loader.sh` (surface session-log)

---

## 2. Project-Local Plan Storage

### Problem
Claude Code's built-in plan mode saves to `~/.claude/plans/` which isn't git-tracked and doesn't survive across machines.

### Design
- Update `install.sh` to suggest adding `"plansDirectory": "docs/plans"` to project settings when detected
- Update `writing-plans` skill to check project-local `docs/plans/` first, then global fallback
- Document in README as a recommended setup step

### Files
- Edit: `install.sh` (add plansDirectory suggestion)
- Edit: `skills/writing-plans/SKILL.md` (dual-location check)
- Edit: `README.md` (document setup)

---

## 3. Declarative Reviewer Registry

### Problem
Phase 6 reviewer selection logic is hardcoded in code-creation-workflow. Adding new reviewers requires editing the skill text.

### Design
- New config file: `reviewer-registry.json` mapping file patterns to reviewer agents
- Two tiers: `always` (run every time) and `conditional` (run when file patterns match the diff)
- Conditional reviewers support both `file_patterns` (glob) and `content_pattern` (regex + threshold)
- Phase 6 reads this registry instead of inline if/else logic
- Users add project-specific reviewers via `.claude/reviewer-registry.json`

```json
{
  "version": "1.0",
  "reviewers": [
    {
      "id": "code-reviewer",
      "tier": "always",
      "subagent_type": "coderabbit:code-reviewer",
      "description": "General code quality and correctness"
    },
    {
      "id": "silent-failure-hunter",
      "tier": "always",
      "subagent_type": "pr-review-toolkit:silent-failure-hunter",
      "description": "Catches swallowed exceptions"
    },
    {
      "id": "security-reviewer",
      "tier": "always",
      "subagent_type": "security-reviewer",
      "description": "Auth, data privacy, common vulnerabilities"
    },
    {
      "id": "test-coverage-analyzer",
      "tier": "always",
      "subagent_type": "pr-review-toolkit:pr-test-analyzer",
      "description": "Test coverage gaps"
    },
    {
      "id": "migration-reviewer",
      "tier": "conditional",
      "file_patterns": ["alembic/**/*.py", "**/migrations/**/*.py", "**/*.sql"],
      "subagent_type": "migration-reviewer",
      "description": "Migration safety checks"
    },
    {
      "id": "async-reviewer",
      "tier": "conditional",
      "file_patterns": ["**/*.py"],
      "content_pattern": "async def|await ",
      "threshold": 3,
      "subagent_type": "async-reviewer",
      "description": "Async anti-patterns"
    },
    {
      "id": "api-doc-auditor",
      "tier": "conditional",
      "file_patterns": ["**/routes/**", "**/api/**", "**/endpoints/**"],
      "subagent_type": "api-doc-auditor",
      "description": "API documentation and schema consistency"
    }
  ]
}
```

Phase 6 logic becomes: read registry → partition into always/conditional → filter conditional by diff → dispatch all matching reviewers in parallel.

### Files
- New: `reviewer-registry.json` (root-level config)
- Edit: `skills/code-creation-workflow/SKILL.md` (Phase 6 reads registry)
- Edit: `install.sh` (copy registry to `~/.claude/`)

---

## 4. Exploration Path in Phase 1

### Problem
No structured way to experiment with ideas before committing to the full workflow. Users either skip the workflow or run the full pipeline for throwaway experiments.

### Design
New EXPLORE PATH in Phase 1 Discovery triage:

```
Is this EXPLORATORY?
("try this", "experiment with", "see if X works",
 "prototype", "spike", "proof of concept")

YES → EXPLORE PATH
  1. Create explorations/<topic>/ directory
  2. Write explorations/<topic>/README.md (goal, hypothesis, success criteria)
  3. Code freely — no TDD, no Phase 6 review
  4. At decision point:
     a. Graduate → full workflow from Phase 4 (exploration findings skip Phase 2)
     b. Archive → explorations/ARCHIVE/<topic>-abandoned.md with reasons
```

**Quality bar:** 60/100 (vs 80/100 production). No test requirement, no multi-agent review. Defensive patterns still loaded, secret detection still active, basic lint still runs.

**Graduation:** "This works, let's ship it" → exploration findings become Phase 2 input, skip parallel explorers, flow into normal pipeline from Phase 4.

**Archive:** One-paragraph ABANDONED.md → becomes "Ruled Out" reference for future sessions.

### Files
- Edit: `skills/code-creation-workflow/SKILL.md` (add EXPLORE PATH to Phase 1)
- Edit: `hooks/tier1/session-context-loader.sh` (surface explorations/ on start)

---

## 5. Abandon/Archive Workflow

### Problem
When work is abandoned mid-session, there's no structured way to capture why. Next session may re-explore the same dead end.

### Design
Extend session-handoff with explicit abandon mode:

- New argument: `/session-handoff --abandon` (or "abandon this", "this didn't work")
- Modified flow:
  1. Gather same state as normal handoff
  2. Prompt: "What was the approach? Why abandoned? What was learned?"
  3. Write to `.claude/abandoned/<YYYY-MM-DD-topic>.md`:

```markdown
# Abandoned: <topic>
**Date:** YYYY-MM-DD
**Branch:** feature/xyz (deleted / kept for reference)

## What was attempted
Brief description of the approach

## Why abandoned
- Reason 1

## What was learned
- Insight for future attempts
```

- `session-context-loader` checks `.claude/abandoned/` on start, surfaces recent entries
- `memory-injection` includes recent abandoned entries in subagent context
- Exploration archive (#4) uses this same abandon flow

### Files
- Edit: `skills/session-handoff/SKILL.md` (add --abandon mode)
- Edit: `hooks/tier1/session-context-loader.sh` (surface abandoned/)
- Edit: `skills/memory-injection/SKILL.md` (include abandoned context)

---

## Ruled Out

- **Standalone /explore skill separate from Phase 1** — User preferred integrated routing over a separate entry point. Keeps the workflow as the single orchestrator.
- **Automatic decision journaling (no prompt, just log)** — Claude can't reliably auto-detect "this was a design decision" vs "this was a routine edit." Periodic reminders are more reliable than auto-detection.
- **Heavy reviewer registry with scoring/weighting** — YAGNI. Simple always/conditional tiers cover the use case. Scoring can be added later if needed.
- **Session log as a database/JSONL** — Markdown is human-readable, grep-able, and git-friendly. Structured formats add complexity without proportional benefit for this use case.

## Implementation Order

1. Decision journal hook (standalone, no dependencies)
2. Reviewer registry (standalone, no dependencies)
3. Abandon/archive workflow (extends session-handoff)
4. Exploration path (depends on #3 for archive flow)
5. Project-local plan storage (standalone, smallest change)

Items 1, 2, and 5 are independent and can be implemented in parallel.
