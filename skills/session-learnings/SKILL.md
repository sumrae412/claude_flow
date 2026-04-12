---
name: session-learnings
description: Use proactively after committing significant work to capture session lessons — dispatches a background agent that writes MEMORY.md directly (auto-committed) and proposes updates to skills and CLAUDE.md
---

# Session Learnings

## Overview

After major commits, dispatch a background agent to reflect on what was learned and propose updates to skills and project docs. The agent analyzes both **code diffs** and **session conversation** to find new patterns, bug lessons, user corrections, and conventions that should be documented.

After writing individual memory files, the agent also runs a **compilation step** that consolidates related memories into concept articles under `memory/knowledge/concepts/`. This reduces fragmentation and creates cross-referenced knowledge. See Step 2b below.

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
- Abandoned approaches: [check .claude/abandoned/ for records created this session —
  ensure they are reflected in MEMORY.md entries so future sessions don't re-explore]
- Failure events: [read memory/episodic/failure-events.jsonl for this session's events —
  count by type, note any failure:unresolved, list novel patterns added to catalog]
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
      MEMORY_DIR=$(find ~/.claude/projects/ -name "MEMORY.md" -maxdepth 3 | head -1 | xargs dirname 2>/dev/null)
      # If not found, ask user for MEMORY_DIR before proceeding.
      # Note: MEMORY.md should already exist — claude-flow Phase 0 Step 8 bootstraps it.
      # Do not duplicate bootstrap logic here; if missing, it indicates the workflow was skipped.
      MEMORY_FILE=$MEMORY_DIR/MEMORY.md

    For MEMORY.md updates: READ the file, EDIT it directly, then commit and push
    (see commit sequencing below after Step 2b).

    For skills and CLAUDE.md updates: PROPOSE only (do not edit). These need
    user approval. Write proposals to your output as structured text.

    ## Step 2b: Memory Compilation

    After writing individual memory files (feedback_*.md, reference_*.md), run
    this compilation step to consolidate related memories into concept articles.

    ### 2b.0 Create directory
    ```bash
    mkdir -p "$MEMORY_DIR/knowledge/concepts"
    ```

    ### 2b.1 Inventory
    Read all `feedback_*.md` and `reference_*.md` files in $MEMORY_DIR.
    Read existing `knowledge/concepts/*.md` articles.
    Ignore: MEMORY.md, *.jsonl, *.json, failure-catalog.md, prompt-variants.json.

    **If no `feedback_*.md` or `reference_*.md` files exist, skip Steps 2b.2 through 2b.5.**

    ### 2b.2 Cluster (LLM judgment)
    Group memory files into topic clusters. Rules:
    - One cluster per file max (no file in multiple clusters)
    - Leave unclustered if no good fit (do not force)
    - Prefer broader clusters over narrow ones
    - Each cluster has a slug (kebab-case) and a human-readable title

    Output as JSON:
    ```json
    {
      "clusters": [
        { "slug": "error-handling-patterns", "title": "Error Handling Patterns", "files": ["feedback_001.md", "reference_003.md"] },
        { "slug": "ui-state-management", "title": "UI State Management", "files": ["feedback_004.md"] }
      ],
      "unclustered": ["reference_007.md"]
    }
    ```

    ### 2b.3 Merge or Update
    For each cluster, check if `knowledge/concepts/<slug>.md` already exists.
    - If exists: update it — merge new key points, update `sources` list, set `updated` date.
    - If new: create `knowledge/concepts/<slug>.md` with this format:

    ```markdown
    ---
    title: "<Title>"
    sources:
      - <file1.md>
      - <file2.md>
    compiled: <date>
    updated: <date>
    ---
    # <Title>
    ## Key Points
    - ...
    ## Related
    - [[concepts/<other>]] — <why>
    ```

    Add cross-links (`## Related`) between articles that share sources or topics.

    ### 2b.4 Quick Lint (Checks 1-2 only)
    Before committing, scan for:
    1. **Broken links:** Any `[[concepts/<slug>]]` that points to a non-existent file? Fix or remove.
    2. **Orphan memories:** Any `feedback_*.md` or `reference_*.md` not listed in any concept's `sources`? Note them but do not force-cluster.

    ### 2b.5 Update MEMORY.md Index
    For each compiled concept article, ensure MEMORY.md contains an index entry:
    ```
    **<slug>:** → See [knowledge/concepts/<slug>.md](knowledge/concepts/<slug>.md)
    ```
    If the entry already exists, leave it. If missing, append it.

    ## Commit Sequencing
    After writing raw memory files and running compilation:
    1. Write raw memory files (existing behavior — feedback_*.md, reference_*.md, MEMORY.md edits)
    2. Attempt compilation (Step 2b above)
    3. If compilation succeeded:
       ```bash
       cd $MEMORY_DIR && git add . && git commit -m "session-learnings: <summary>"
       ```
    4. If compilation errored (partial write, lint failures, etc.):
       ```bash
       cd $MEMORY_DIR && git add MEMORY.md feedback_*.md reference_*.md && git commit -m "[partial] session-learnings: <summary>"
       ```
    5. Push regardless:
       ```bash
       git push || true
       ```

    ## Pre-Compaction Snapshot Processing
    Before analyzing code, check for pre-compaction snapshots that captured
    context from sessions that were about to compact:
    1. Check for files: `ls $PROJECT/.claude/pre-compaction-*.md 2>/dev/null`
       (The pre-compaction-backup hook writes snapshots to `$PROJECT/.claude/`)
    2. For each snapshot found:
       - Read the file to extract git state (branch, recent commits, dirty files)
       - Extract any session context or learnings the prior session captured
       - Incorporate this context into your knowledge extraction — these represent
         work-in-progress that the prior session could not finish documenting
    3. Delete consumed snapshots after extraction:
       ```bash
       rm -f $PROJECT/.claude/pre-compaction-*.md
       ```

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
    - skills/*.md, claude_flow/** → meta (skill/workflow changes — check claude_flow repo, not active project)

    Note: If changes were made to files under `~/.claude/skills/` or `claude_flow/`, the canonical repo is `claude_flow` at `/Users/summerrae/claude_code/claude_flow/`. Run git commands there, not in the active project repo.

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
        "claude-flow"). Verify: `--mode` vs `--reviewer` flags,
        option numbering (finishing options 1-4), delegation targets
        (which skill handles which option).

    ## Policy Detection (REQUIRED when 3+ files changed for the same reason)
    9. **Cross-cutting policy:** If the same rule/correction was applied to
       3 or more files, this is a policy decision. Propose a memory entry
       documenting: what the policy is, why it was established, and which
       files were updated. Future sessions need this context immediately,
       not buried across individual skill files.

    ## Failure Event Analysis (REQUIRED when episodic/failure-events.jsonl has entries)

    Read memory/episodic/failure-events.jsonl and analyze:

    10. **Pattern frequency:** Which error_classes appear most? Should any become
        a defensive pattern in the relevant skill (e.g., defensive-backend-flows)?
        Threshold: 5+ occurrences across sessions → propose skill promotion.

    11. **Catalog health:** Are there catalog entries that haven't been hit in
        30+ days? Flag them for review (may be stale or too specific).

    12. **Unresolved failures:** Any failure:unresolved events? These represent
        gaps in the self-debugging system. Propose: new catalog entry with
        the manual resolution the user applied, OR a skill update to prevent
        the failure class entirely.

    ## Prompt Optimization (REQUIRED when episodic/exploration-events.jsonl has entries)

    Check if this session recorded exploration events:

    13. **Update metrics:** Run `python3 ~/.claude/scripts/prompt-tracker.py update-metrics`
        to recompute variant scores from all events.
        Note: `prompt-tracker.py` lives at `~/.claude/scripts/prompt-tracker.py`.
        If not found, check `~/claude_code/claude_flow/scripts/prompt-tracker.py`
        (canonical source) and run `./install.sh` to install it.

    14. **Check for promotions:** Run `python3 ~/.claude/scripts/prompt-tracker.py report`
        and check if any variant pair is ready for promotion (10+ sessions each,
        F1 gap > 0.05). If so, invoke the `prompt-optimization` skill to handle
        promotion and challenger generation.

    15. **Miss patterns:** Report the top 5 most commonly missed files. If a file
        type appears 3+ times in misses (e.g., config files, test fixtures),
        propose adding it as a hint to the relevant explorer prompt variant.

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
| "I'll run session-learnings at the end" | "End" never comes if there are more commits. Run it after each significant commit cluster, not at session close. |

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
