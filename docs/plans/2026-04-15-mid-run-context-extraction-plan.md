# Mid-Run Context Extraction (Phase 5 Step 3e) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a lightweight inline extraction step (Step 3e) to claude-flow's Phase 5 that captures reusable domain facts (SCHEMA / API / PATTERN / GOTCHA) after each task completes, persisting them in the `$diff` contract for downstream consumption.

**Architecture:** Extend the existing per-task TDD loop in `phases/phase-5-implementation.md` with a new Step 3e that runs inline (Sonnet executor, no subagent spawn) after the mutation gate but before static analysis. Output is a YAML structure of facts appended to a new optional `context_facts` field on the `$diff` contract. Facts injected into next-task subagent prompts as "known context" and consumed by Phase 6 reviewers and session-learnings.

**Tech Stack:** Markdown (skill files), YAML (contract format) — pure documentation/config change to the claude-flow skill. No code changes, no tests in the traditional sense — verification is by reading the updated docs.

**Ruled Out (per design doc):**
- Background subagent — 30s startup overhead, facts arrive too late
- Extending session-learnings mid-session — wrong granularity
- Context-pressure threshold trigger — facts lost before extraction fires
- Writing to MEMORY.md mid-run — too noisy, pollutes memory with task-specific details

**Source design:** `/Users/summerrae/claude_code/claude_flow/docs/plans/2026-04-15-mid-run-context-extraction-design.md`

---

## Files Touched (entire feature)

- Modify: `~/.claude/skills/claude-flow/phases/phase-5-implementation.md`
- Modify: `~/.claude/skills/claude-flow/contracts/diff.schema.md`
- Verify: `~/.claude/skills/claude-flow/SKILL.md` (router) — confirm no router-level reference to Step 3e needs adding (per progressive-disclosure design, phase steps live inside the phase file only)

**Note on dual-location skills:** This file lives in BOTH the plugin cache (`~/.claude/skills/claude-flow/`) AND the source repo (`/Users/summerrae/claude_code/claude_flow/skills/claude-flow/`). The cache copy is the runtime; the repo copy is version control. We edit cache for testing and sync to repo for commit. See CLAUDE.md gotcha "Plugin cache is NOT git-tracked".

---

## Task 1: Update `$diff` contract schema

**Files:**
- Modify: `~/.claude/skills/claude-flow/contracts/diff.schema.md`
- Verify: `/Users/summerrae/claude_code/claude_flow/skills/claude-flow/contracts/diff.schema.md` (sync target)

**Step 1: Read current contract**

Run: `cat ~/.claude/skills/claude-flow/contracts/diff.schema.md`
Expected: 16-line file with `files_changed`, `insertions`, `deletions`, `git_diff` fields plus a "## Notes" section.

**Step 2: Add `context_facts` field to the Schema section**

Replace the Schema section to add the new optional field after `git_diff`:

```markdown
## Schema

files_changed: string[]
insertions: number
deletions: number
git_diff: string          # full diff (unavoidable — reviewers need real content)
context_facts:            # Optional. Populated by Phase 5 Step 3e (mid-run extraction).
  - task: string          # Task identifier from $plan
    facts:                # Array of extracted facts (max 10 per task)
      - type: string      # SCHEMA | API | PATTERN | GOTCHA
        fact: string      # One-line reusable fact
```

**Step 3: Append `context_facts` documentation to the Notes section**

Add these bullets to the existing "## Notes" section:

```markdown
- context_facts is populated by Phase 5 Step 3e after each task; entries accumulate across tasks
- context_facts are consumed by: next-task executor (injected as "known context"), Phase 6 reviewers, and session-learnings (skips facts already captured)
- context_facts is OPTIONAL — absent or empty array is valid for documentation-only tasks or tasks with no novel discoveries
```

**Step 4: Verify the file is well-formed**

Run: `cat ~/.claude/skills/claude-flow/contracts/diff.schema.md`
Expected: file shows the new `context_facts` field in the schema and the new notes bullets.

**Step 5: Sync cache → repo**

```bash
cp ~/.claude/skills/claude-flow/contracts/diff.schema.md \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/contracts/diff.schema.md
diff ~/.claude/skills/claude-flow/contracts/diff.schema.md \
     /Users/summerrae/claude_code/claude_flow/skills/claude-flow/contracts/diff.schema.md
```

Expected: no diff output (files identical).

**Step 6: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add skills/claude-flow/contracts/diff.schema.md
git commit -m "feat(claude-flow): add context_facts field to \$diff contract"
```

---

## Task 2: Add Step 3e to Phase 5 with extraction prompt

**Files:**
- Modify: `~/.claude/skills/claude-flow/phases/phase-5-implementation.md` (insert Step 3e between current Step 3d and Step 4)
- Verify: `/Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-5-implementation.md` (sync target)

**Step 1: Read the current step sequence**

Run: `grep -n "^3[a-z]\.\|^4\." ~/.claude/skills/claude-flow/phases/phase-5-implementation.md | head -10`
Expected: Output shows current steps `3b. GUARD`, `3c. MUTATION GATE`, and `4. Run static analysis...` (note: there is NO `3d` in the current file — the design doc lists "3d: Visual verify gate (optional)" but it is not present in phase-5-implementation.md as of 2026-04-15).

**Step 2: Decide insertion anchor**

Step 3e is inserted AFTER the mutation gate (Step 3c) and BEFORE Step 4 (static analysis). The exact line range for Step 3c ends with the "Why separate from step 3b" paragraph followed by a blank line and then `4. Run static analysis on changed files...`. Insert Step 3e between them.

Use this command to find the precise insertion point:

```bash
grep -n "^4\. Run static analysis" ~/.claude/skills/claude-flow/phases/phase-5-implementation.md
```

Expected: returns one line number (e.g. line 191). Insert Step 3e immediately before this line.

**Step 3: Write Step 3e content**

Insert this block before the `4. Run static analysis` line:

```markdown
3e. CONTEXT EXTRACTION — capture reusable domain facts
    After tests pass and the mutation gate clears, before static analysis,
    extract reusable domain facts discovered during this task. Runs INLINE
    (Sonnet executor, no subagent spawn) so facts are available immediately
    for the next task and survive context compaction.

    Run this extraction prompt against the just-completed task:

    ```
    Review the task you just completed. Extract reusable domain facts in
    these categories:

    1. SCHEMA: Column names, table relationships, enum values discovered
    2. API: Endpoint signatures, response shapes, error codes encountered
    3. PATTERN: Code patterns that worked (import paths, service method
       signatures, conventions)
    4. GOTCHA: Anything that failed first and required a different approach

    Output as structured YAML matching the $diff.context_facts schema.
    Max 10 facts per task. Only NOVEL discoveries — skip facts already
    in $plan, $requirements, or earlier $diff.context_facts entries.
    ```

    Append the YAML output to $diff.context_facts under a new entry keyed
    by the current task identifier:

    ```yaml
    context_facts:
      - task: "<task-id-from-plan>"
        facts:
          - type: SCHEMA
            fact: "HouseholdMember.is_primary_contact (not is_primary)"
          - type: PATTERN
            fact: "household_service.ensure_client_for_member() required after create"
          - type: GOTCHA
            fact: "scalar_one_or_none() crashes on email lookup — use scalars().first()"
    ```

    Skip conditions (no facts to extract; do not block):
    - Task changed zero test files (documentation-only / config-only task)
    - Task is a pure refactor with no new domain knowledge
    - Extraction returned an empty array (no novel facts)

    Performance budget:
    - ~200 tokens in, ~100 tokens out per task
    - Estimated overhead: 5-10 seconds per task (no subagent spawn)
    - Hard cap: skip if extraction takes >30 seconds (log and continue)

    Consumption points (no action needed here — downstream consumers handle):
    - Next-task executor injects facts as "known context" in the task prompt
    - Phase 6 reviewers receive facts via $diff contract
    - Session-learnings dedupes against context_facts before promoting to MEMORY.md
    - GOTCHA-tagged facts are candidates for memory-injection promotion

    Why separate from session-learnings: session-learnings runs at end of
    workflow (or end of session) — facts captured there are lost across
    context compaction and unavailable to subsequent in-workflow tasks.
    Step 3e captures facts WHILE they are fresh and propagates them
    forward.

```

**Step 4: Update the step-sequence header at the top of Phase 5 (if present)**

Run: `grep -n "Step 3a\|Step 3b\|Step 3c\|Step 3d" ~/.claude/skills/claude-flow/phases/phase-5-implementation.md`

If a step-sequence summary block exists at the top of the phase 5 section that lists steps `3a`, `3b`, `3c`, (`3d`), add `3e` to it. If no such summary block exists, skip this step.

**Step 5: Verify the inserted block**

Run: `grep -n "^3[a-z]\.\|^4\. Run static analysis" ~/.claude/skills/claude-flow/phases/phase-5-implementation.md`
Expected: Output now includes `3e. CONTEXT EXTRACTION` between the mutation gate and Step 4.

Run: `wc -l ~/.claude/skills/claude-flow/phases/phase-5-implementation.md`
Expected: File grew by ~50 lines (was 285, should now be ~335).

**Step 6: Sync cache → repo**

```bash
cp ~/.claude/skills/claude-flow/phases/phase-5-implementation.md \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-5-implementation.md
diff ~/.claude/skills/claude-flow/phases/phase-5-implementation.md \
     /Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-5-implementation.md
```

Expected: no diff output.

**Step 7: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add skills/claude-flow/phases/phase-5-implementation.md
git commit -m "feat(claude-flow): add Phase 5 Step 3e context extraction"
```

---

## Task 3: Document next-task fact injection

**Files:**
- Modify: `~/.claude/skills/claude-flow/phases/phase-5-implementation.md` (add a paragraph in the "Fresh Context for Long Implementation Loops" subsection or in the parallel-subagent dispatch block)
- Verify: repo sync

**Why this task is needed:** Step 3e captures facts but the design doc says "Next task executor: Facts injected into task prompt as 'known context'." That injection is a separate behavior change from extraction. Without it, captured facts sit in `$diff` but never reach the next implementer subagent.

**Step 1: Find the subagent-dispatch block**

Run: `grep -n "subagent.*FRESH context\|Each subagent starts" ~/.claude/skills/claude-flow/phases/phase-5-implementation.md`
Expected: locates the section listing what each subagent receives at dispatch.

**Step 2: Add `context_facts` to the per-subagent context list**

Find the existing block (around lines 222-228 in the current file):

```
For parallel subagent dispatch:
  Each subagent starts with FRESH context:
  - The specific step(s) assigned to it
  - Key file paths + patterns (not full file contents)
  - Defensive patterns to apply
  No prior step history — the plan is the contract.
```

Replace it with:

```
For parallel subagent dispatch:
  Each subagent starts with FRESH context:
  - The specific step(s) assigned to it
  - Key file paths + patterns (not full file contents)
  - Defensive patterns to apply
  - $diff.context_facts entries from prior completed tasks
    (injected as "Known context from earlier tasks: ..." preamble)
  No prior step history — the plan is the contract.
```

**Step 3: Add a similar note to the sequential per-task dispatch (subagent-driven-development controller)**

Add this paragraph immediately after Step 3e's extraction block from Task 2, OR as a final bullet under "Consumption points":

> **Inter-task injection:** When dispatching the next task's subagent, prepend a "Known context from earlier tasks" section to the prompt containing all `$diff.context_facts` entries from prior tasks. This makes prior-task discoveries available without re-discovery.

(One of the two — the parallel-dispatch block update OR a sequential-dispatch bullet — is sufficient. Pick whichever is closer to the existing text.)

**Step 4: Verify**

Run: `grep -n "context_facts" ~/.claude/skills/claude-flow/phases/phase-5-implementation.md`
Expected: at least 3 matches (extraction block, contract schema reference, inter-task injection).

**Step 5: Sync cache → repo**

```bash
cp ~/.claude/skills/claude-flow/phases/phase-5-implementation.md \
   /Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-5-implementation.md
```

**Step 6: Commit**

```bash
cd /Users/summerrae/claude_code/claude_flow
git add skills/claude-flow/phases/phase-5-implementation.md
git commit -m "feat(claude-flow): inject context_facts into next-task subagent prompts"
```

---

## Task 4: Verification — read both files end-to-end

**Files:** None modified — verification only.

**Step 1: Re-read the contract**

Run: `cat ~/.claude/skills/claude-flow/contracts/diff.schema.md`

Verify:
- `context_facts` field present in Schema with `type: SCHEMA | API | PATTERN | GOTCHA` enum documented
- Notes section explains it is optional and lists consumers

**Step 2: Re-read Phase 5 Step 3e**

Run: `sed -n '/^3e\. CONTEXT EXTRACTION/,/^4\. Run static analysis/p' ~/.claude/skills/claude-flow/phases/phase-5-implementation.md`

Verify:
- Extraction prompt is present and matches the design doc
- Skip conditions documented (zero test files, pure refactor, empty extraction)
- Performance budget documented (200 tokens in, 100 out, 5-10s, 30s hard cap)
- Consumption points listed (next-task executor, Phase 6, session-learnings, memory-injection)
- "Why separate from session-learnings" rationale present

**Step 3: Verify cache and repo are in sync**

```bash
diff ~/.claude/skills/claude-flow/contracts/diff.schema.md \
     /Users/summerrae/claude_code/claude_flow/skills/claude-flow/contracts/diff.schema.md
diff ~/.claude/skills/claude-flow/phases/phase-5-implementation.md \
     /Users/summerrae/claude_code/claude_flow/skills/claude-flow/phases/phase-5-implementation.md
```

Expected: both diffs return empty.

**Step 4: Verify git history is clean**

```bash
cd /Users/summerrae/claude_code/claude_flow
git log --oneline -5
```

Expected: 3 commits matching the conventional-commit messages from Tasks 1-3.

---

## Done

The feature is shipped when:
- `$diff` contract documents `context_facts` field
- Phase 5 has Step 3e with full extraction prompt, skip conditions, and budget
- Phase 5 documents fact injection into next-task subagent prompts
- Cache and repo copies are in sync
- 3 commits land on the working branch

## Out of Scope (explicit deferrals)

- **Memory promotion automation:** The design says "GOTCHA facts are candidates for MEMORY.md promotion" — deferred to a future change in session-learnings or memory-injection skills.
- **Visual verify gate (Step 3d):** The design doc lists "Step 3d: Visual verify gate (optional)" in the new sequence but the current phase-5-implementation.md has no Step 3d. Adding it is a separate change; this plan inserts 3e between the existing 3c and Step 4.
- **Code changes to consumers:** This plan documents that next-task executor / Phase 6 reviewers / session-learnings / memory-injection consume `context_facts`. Wiring the actual consumption logic in those skills is out of scope for this plan — the design treats this as documentation-driven coordination across skills.
- **Tests:** This is a documentation/config change to a skill (Markdown only). No automated test exists for skill content correctness; verification is by reading the rendered phase file.
