---
name: session-learnings
description: Use proactively after committing significant work to capture session lessons — dispatches a background agent that writes MEMORY.md directly (auto-committed) and proposes updates to skills and CLAUDE.md
---

# Session Learnings

## Overview

After major commits, dispatch a background agent to reflect on what was learned and propose updates to skills and project docs. The agent analyzes both **code diffs** and **session conversation** to find new patterns, bug lessons, user corrections, and conventions that should be documented.

**Core principle:** The conversation is the richest source of learnings. Code diffs show *what* changed; session events show *why* and *what went wrong first*.

## When to Use

Proactively invoke after:
- Committing a significant feature or bug fix
- A debugging investigation that uncovered root causes
- The user correcting your approach ("that's wrong, do it this way")
- Discovering a new convention or component pattern
- The user explicitly asking to update skills

Do NOT invoke after:
- Trivial commits (typo fixes, version bumps)
- Work that only touched files already fully documented in skills
- Mid-task commits where more work follows immediately

## The Process

### Step 1: Compile Session Context

Before dispatching the background agent, compile a structured summary from the conversation:

```
SESSION CONTEXT:
- User corrections: [list times user said something was wrong or needed changing]
- Bugs investigated: [root causes found, what was misleading]
- Patterns established: [user said "make this the default", "always do X"]
- Gotchas hit: [security hooks, env quirks, API limitations, workarounds]
- Investigation conclusions: ["feature never existed", "regression from cherry-pick"]
- New components built: [UI components, utilities, patterns that others should reuse]
- Spec review catches: [things spec reviewer found missing before implementation]
- Code quality catches: [N+1 queries, race conditions, duplicate code found in review]
- Cross-cutting changes: [same rule applied to 3+ files = policy; needs memory entry]
- Skills modified: [which skills were edited and why — triggers cross-reference audit]
```

### Step 2: Dispatch Background Agent

Use the Task tool with `run_in_background: true`:

```
Task tool:
  subagent_type: general-purpose
  run_in_background: true
  prompt: |
    You are a session-learnings analyst. Your job is to analyze code changes
    and session events, then update MEMORY.md directly and propose updates
    to skills and project docs.

    ## Write Access
    You have DIRECT WRITE ACCESS to the project memory repo:
      MEMORY_DIR=~/.claude/projects/-Users-summerrae-courierflow/memory
      MEMORY_FILE=$MEMORY_DIR/MEMORY.md

    For MEMORY.md updates: READ the file, EDIT it directly, then commit and push:
      cd $MEMORY_DIR && git add MEMORY.md && git commit -m "session-learnings: <summary>" && git push

    For skills and CLAUDE.md updates: PROPOSE only (do not edit). These need
    user approval. Write proposals to your output as structured text.

    ## Code Context
    Run these commands to understand what changed:
    - git log --oneline -10
    - git diff HEAD~N..HEAD --stat  (where N = number of session commits)
    - Read any skill files that match changed domains

    ## Session Context
    [paste compiled session context from Step 1]

    ## Domain Mapping
    Map changed files to skill domains:
    - CSS/HTML/templates → defensive-ui-flows, project UI standards skill
    - routes/*.py, services/*.py → defensive-backend-flows
    - models/*.py, alembic/ → coding-best-practices
    - tests/ → coding-best-practices (testing section)
    - .claude/skills/ → meta (skills changed directly)

    ## Available Skills
    Personal: ls ~/.claude/skills/
    Project: ls .claude/skills/ (if exists)

    ## Reflection Questions (per matched domain)
    For each relevant skill, read its current content and ask:
    1. Are there new patterns in committed code not documented here?
    2. Did we hit a bug/gotcha that should become a defensive pattern?
    3. Did the user correct the agent's approach? What rule prevents it?
    4. Did we discover a convention/component for project standards?
    5. Were there investigation lessons worth documenting?

    Also check CLAUDE.md:
    6. Are there new bash commands, env quirks, or conventions for CLAUDE.md?

    ## Cross-Reference Audit (REQUIRED when skills were modified)
    When ANY skill was edited this session, run these checks:

    7. **Parallel entry points:** For each modified skill, grep other skills
       for references to the same outcome (e.g., "merge", "ship", "finish").
       If another skill reaches the same outcome via a different path, does
       it also include the change? Example: shipping-workflow and
       cleanup both ship code — a stage added to
       one must be checked against the other.

    8. **Contradictory guidance:** Grep all skills for terms related to the
       change (e.g., "pre-existing", "--no-verify", "out of scope"). Flag
       any skill that still contradicts the new rule.

    8b. **Specific patterns to check:** For each modified skill, grep ALL
        other skills for the skill's name (e.g., "debate-team",
        "code-creation-workflow"). Verify: `--mode` vs `--reviewer` flags,
        option numbering (finishing options 1-4), delegation targets
        (which skill handles which option).

    ## Policy Detection (REQUIRED when 3+ files changed for the same reason)
    9. **Cross-cutting policy:** If the same rule/correction was applied to
       3 or more files, this is a policy decision. Propose a memory entry
       documenting: what the policy is, why it was established, and which
       files were updated. Future sessions need this context immediately,
       not buried across individual skill files.

    ## Output Format
    For EACH proposed update, write:

    ### [target-name] — [1-line reason]
    **File:** [full path]
    **Action:** Add pattern | Update section | Add checklist item | Add line
    **Content:**
    > [the proposed addition — match the style of the existing file]
    > [keep concise: 1-10 lines per proposal]

    If no updates are needed for a domain, say so explicitly.
    End with: "## Summary: N proposals across M targets"
```

### Step 3: Present Results

When the background agent completes (check via TaskOutput):

1. Read the agent's output
2. Present a concise summary: "Session learnings found **N updates** across **M targets**"
3. Note which MEMORY.md updates were **already applied** (written + committed + pushed by the agent)
4. List remaining skill/CLAUDE.md proposals with their 1-line reasons
5. Ask: "Apply all / select which ones / skip?" (for the proposals only)

### Step 4: Apply Approved Proposals

For each approved skill/CLAUDE.md proposal:
- Read the target file
- Make the edit (matching existing style — patterns numbered sequentially, checklist items appended, etc.)
- Confirm each edit succeeded

**MEMORY.md is auto-applied** by the background agent (no approval needed — it's the agent's own learnings repo).
**Skills and CLAUDE.md require approval.** The background agent proposes; the user decides.

## Red Flags

| Thought | Reality |
|---------|---------|
| "Nothing notable happened this session" | User corrections alone are worth capturing |
| "The code diff tells the whole story" | Session context (corrections, investigations) is richer |
| "I'll remember this for next time" | You won't. Next session starts fresh. Document it now. |
| "This is too minor to document" | Minor gotchas (security hooks, worktree quirks) save the most time |
| "I already updated skills manually" | Run the agent anyway — it may catch things you missed |
| "I only changed one skill" | Other skills may reach the same outcome via a different path. Cross-reference audit catches these. |
| "The change is self-documenting" | If 3+ files changed for the same reason, it's a policy. Future sessions won't read all those files — they need a memory entry. |
| "I'll run multiple agents in parallel for speed" | Parallel subagents doing git commits in the same worktree cause conflicts. Serialize commits or use separate worktrees per agent. |

## Example Session Context

From a real session that built a bulk action bar:

```
SESSION CONTEXT:
- User corrections: "The bulk options menu does not have rounded edges —
  make sure it does" (user provided screenshot showing expected pill shape)
- Bugs investigated: User reported "bulk select was removed from workflows
  page" — systematic investigation showed feature NEVER existed in any
  git version. CSS classes existed but were used by a different JS file.
- Patterns established: "Update the UI skills to make this the default
  style" — bulk action bar with rounded edges is now standard.
- Gotchas hit: Security hook blocked innerHTML=''. Fixed with
  while(el.firstChild) el.removeChild(el.firstChild).
- New components built: Floating bulk action bar (.wf-bulk-bar),
  card selection with progressive disclosure (.card-select-checkbox)
```

This produced 3 skill updates (defensive-ui-flows patterns #23-25) and 1 project skill update (courierflow-ui-standards bulk action bar section).
