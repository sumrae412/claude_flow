# Memory Compilation & Knowledge Lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend claude-flow's memory system to consolidate scattered memory files into compiled concept articles, add 4 knowledge lint checks, and process pre-compaction snapshots for knowledge extraction.

**Architecture:** Compilation runs as an extension of the session-learnings background agent (compile-on-write). A new `/lint-memory` skill provides on-demand health checks. Memory-injection is updated to serve compiled articles alongside raw gotchas. No new hooks.

**Tech Stack:** Markdown skills (SKILL.md), bash (hooks), LLM judgment (clustering)

**Spec:** `docs/superpowers/specs/2026-04-10-memory-compilation-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `skills/lint-memory/SKILL.md` | New skill: runs 4 knowledge lint checks on demand |
| Modify | `skills/session-learnings/SKILL.md` | Add compilation step + lint checks 1-2 + pre-compaction processing |
| Modify | `skills/memory-injection/SKILL.md` | Add compiled article selection + injection format |
| Modify | `skills/code-creation-workflow/references/memory-injection.md` | Add compiled knowledge injection template |

---

### Task 1: Create the `/lint-memory` Skill

**Files:**
- Create: `skills/lint-memory/SKILL.md`

This is the simplest, most independent piece — build it first so we can test lint against existing memory dirs.

- [ ] **Step 1: Create the skill file with frontmatter and overview**

```markdown
---
name: lint-memory
description: Run health checks on project memory files — broken links, orphan memories, stale entries, contradictions
invocation: user
---

# Lint Memory

Run 4 health checks against the project's memory directory to catch broken links, orphan files, stale references, and contradictory entries.

## When to Use

- Periodically after significant work to ensure memory hygiene
- After manual edits to MEMORY.md or memory files
- When you suspect a memory entry may be outdated
```

- [ ] **Step 2: Add Check 1 — Broken Links**

Add to the skill:

```markdown
## Process

### Check 1: Broken Links (severity: error, auto-fixable)

Scan MEMORY.md and all files under `knowledge/` recursively (`knowledge/**/*.md`) for:
- Markdown links: `[text](path)` — verify `path` resolves to an existing file relative to the memory dir
- Wikilinks: `[[path]]` — verify `path.md` exists under `knowledge/`

**Action:**
1. Read MEMORY.md and all files under `knowledge/`
2. Extract all link targets using regex: `\[.*?\]\((.*?)\)` and `\[\[(.*?)\]\]`
3. For each target, check if the file exists (resolve relative to memory dir)
4. **Auto-fix:** Remove broken links from the file. If a MEMORY.md entry's only content is a broken link, remove the entire entry line.
5. Report: list of broken links found and fixed
```

- [ ] **Step 3: Add Check 2 — Orphan Memories**

```markdown
### Check 2: Orphan Memories (severity: warning, auto-fixable)

Find memory files matching `feedback_*.md` or `reference_*.md` in the memory dir that:
- Have no entry (semantic key or link) in MEMORY.md
- Are not listed in any `knowledge/concepts/*.md` article's `sources:` frontmatter

**Excludes:** `*.jsonl`, `*.json`, `failure-catalog.md`, `prompt-variants.json`, `MEMORY.md`, `knowledge/` dir contents.

**Action:**
1. List all `feedback_*.md` and `reference_*.md` files in memory dir
2. Read MEMORY.md — extract all file references (link targets and inline mentions)
3. Read all `knowledge/concepts/*.md` — extract `sources:` lists from frontmatter
4. Any file not referenced by either → orphan
5. **Auto-fix:** For each orphan, read the file, generate a semantic key from its filename (e.g., `feedback_silent_failures.md` → `silent-failures`), and add a 1-line index entry to MEMORY.md
6. Report: list of orphans found and indexed
```

- [ ] **Step 4: Add Check 3 — Stale Entries**

```markdown
### Check 3: Stale Entries (severity: warning, manual review required)

For each memory entry that references a specific file path, function name, or class name (detected by backtick-wrapped code references like \`property.py\`, \`def calculate_total\`, \`class Client\`):

**Action:**
1. Read all entries in MEMORY.md and all `knowledge/concepts/*.md` articles
2. Extract code references: patterns matching \`filename.ext\`, \`def func_name\`, \`class ClassName\`
3. For file references: check if file exists in the project directory
4. For function/class references: grep the project codebase for the identifier
5. **Cannot auto-fix.** Report: list of stale references with file path, the memory entry, and what's missing
6. Suggest: "Review these entries — the referenced code may have been renamed or removed"
```

- [ ] **Step 5: Add Check 4 — Contradictions**

```markdown
### Check 4: Contradictions (severity: error, manual review required)

Compare entries that share the same domain (using the domain mapping from `code-creation-workflow/references/memory-injection.md`) for conflicting claims.

**Action:**
1. Group memory entries by domain (models, services, ui, routes, etc.) using the domain mapping
2. For each domain group with 3+ entries, read all entries and use LLM judgment to identify pairs that make contradictory claims
3. **Cannot auto-fix.** Report: conflicting pairs with file paths, the contradictory statements, and which is likely correct based on current code state
4. Suggest: "Resolve by updating or removing the outdated entry"

### Output Format

Print a markdown report to the terminal:

\```
## Memory Lint Report

### Errors (must fix)
- **Broken link:** MEMORY.md line 15 → `feedback_old_file.md` (file not found) — FIXED
- **Contradiction:** `model-file-name` says X, `knowledge/concepts/data-model.md` says Y

### Warnings (should fix)
- **Orphan:** `feedback_new_pattern.md` not indexed — FIXED (added to MEMORY.md)
- **Stale:** `class-aware-grep` references \`grep_classes()\` — function not found in codebase

### Summary
- 2 errors (1 auto-fixed, 1 needs review)
- 2 warnings (1 auto-fixed, 1 needs review)
\```
```

- [ ] **Step 6: Add invocation notes and auto/manual split**

```markdown
## Invocation Modes

### Full lint (manual — `/lint-memory`)
Runs all 4 checks. Checks 3-4 are expensive (codebase grep + LLM judgment).

### Quick lint (auto — during compilation)
Only checks 1-2 run during session-learnings compilation step. These are fast and deterministic.

## Notes

- Graceful no-op if memory dir doesn't exist or has no memory files
- All auto-fixes are reported before being applied
- The skill does NOT commit changes — the caller (session-learnings or user) decides when to commit
```

- [ ] **Step 7: Commit**

```bash
git add skills/lint-memory/SKILL.md
git commit -m "feat: add /lint-memory skill with 4 health checks"
```

---

### Task 2: Extend Session-Learnings with Compilation Step

**Files:**
- Modify: `skills/session-learnings/SKILL.md`

This is the core change — adding compilation logic to the background agent prompt in Step 2.

- [ ] **Step 1: Read current session-learnings SKILL.md**

Read `skills/session-learnings/SKILL.md` to confirm current structure before editing.

- [ ] **Step 2: Add compilation step overview to the skill description**

After the existing overview section (the paragraph ending with "proposes updates to skills and CLAUDE.md"), add:

```markdown
After writing individual memory files, the agent also runs a **compilation step** that consolidates related memories into concept articles under `memory/knowledge/concepts/`. This reduces fragmentation and creates cross-referenced knowledge. See Step 2b below.
```

- [ ] **Step 3: Add Step 2b — Compilation to the background agent prompt (part 1: core logic)**

Inside the agent prompt template, find the existing commit instruction (line 72):
```
cd $MEMORY_DIR && git add MEMORY.md && git commit -m "session-learnings: <summary>" && git push
```
Insert the following BEFORE that line (after the memory-writing instructions on line 71, before the commit):

```markdown
## Step 2b: Compile Memory (after writing individual files, before commit)

After writing/updating individual memory files, run the compilation step:

### 2b.1: Inventory

Read all `feedback_*.md` and `reference_*.md` files in the memory directory.
Read all existing `knowledge/concepts/*.md` articles if the directory exists.
Ignore: MEMORY.md, `*.jsonl`, `*.json`, `failure-catalog.md`, `prompt-variants.json`.

### 2b.2: Cluster (LLM judgment)

Group the memory files into topic clusters. Apply these rules:
- Each memory file belongs to at most ONE cluster
- If a file doesn't fit any cluster, leave it unclustered
- Prefer fewer, broader clusters over many narrow ones
- Name each cluster with a kebab-case slug

Produce a clustering in this format:
```json
{
  "clusters": [
    {"slug": "error-handling-patterns", "files": ["feedback_silent_failures.md", "feedback_error_handling.md"], "summary": "Patterns for handling errors silently vs explicitly"},
  ],
  "unclustered": ["reference_api_keys.md"]
}
```

### 2b.3: Merge or Update

For each cluster:
- If `knowledge/concepts/<slug>.md` already exists: update its Key Points with any new information from the source files. Add new sources to the `sources:` frontmatter. Update the `updated:` date.
- If no matching article exists: create `knowledge/concepts/<slug>.md` with this format:

```markdown
---
title: "<Title from slug>"
sources:
  - <source-file-1.md>
  - <source-file-2.md>
compiled: <today's date>
updated: <today's date>
---

# <Title>

## Key Points
- <consolidated key points from all source files>

## Related
- [[concepts/<other-related-concept>]] — <why related>
```

- If two concept articles share overlapping source files or related topics, add `## Related` cross-links between them.

```

- [ ] **Step 4: Add Step 2b — Compilation to the background agent prompt (part 2: lint, index, commit)**

Insert immediately after the content from Step 3 (still before the existing commit line):

```markdown
### 2b.4: Quick Lint (Checks 1-2 only)

Before committing, run the fast lint checks:
- **Check 1 (Broken Links):** Scan MEMORY.md and all files under `knowledge/` for links to non-existent files. Remove broken links.
- **Check 2 (Orphan Memories):** Find `feedback_*.md`/`reference_*.md` files not referenced in MEMORY.md or any compiled article. Add index entries.

### 2b.5: Update MEMORY.md Index

For each new or updated compiled article, ensure MEMORY.md has a link entry:
```
**<slug>:** → See [knowledge/concepts/<slug>.md](knowledge/concepts/<slug>.md)
```

### 2b.6: Create knowledge/concepts/ directory if needed

```bash
mkdir -p "$MEMORY_DIR/knowledge/concepts"
```
```

- [ ] **Step 5: Replace the commit instruction with new sequencing**

Find and replace the existing commit line (line 72 of the original file):
```
cd $MEMORY_DIR && git add MEMORY.md && git commit -m "session-learnings: <summary>" && git push
```

Replace with:

```markdown
### Commit Sequencing

1. Write raw memory files (Steps 1-2 above)
2. Attempt compilation (Step 2b above)
3. Stage and commit everything:
   ```bash
   cd $MEMORY_DIR && git add . && git commit -m "session-learnings: <summary>"
   ```
4. If compilation errored at any step:
   ```bash
   cd $MEMORY_DIR && git add MEMORY.md feedback_*.md reference_*.md
   git commit -m "[partial] session-learnings: <summary>"
   ```
   Log the compilation error to stderr.
5. Push: `git push || true`
```

- [ ] **Step 6: Add pre-compaction snapshot processing**

Insert into the agent prompt BEFORE the `## Code Context` section (line 77 of the original file, which starts `Run these commands to understand what changed`). This ensures snapshots are processed before the agent analyzes code and writes new memories:

```markdown
### Pre-Compaction Snapshot Processing

Before analyzing code changes, check for unprocessed pre-compaction snapshots:

```bash
ls $PROJECT/.claude/pre-compaction-*.md 2>/dev/null
```

If snapshots exist:
1. Read each snapshot file — extract the git state (branch, commits, diff summary)
2. Incorporate this context into your knowledge extraction. These snapshots represent work that happened before context compaction — the session may have lost visibility into this work.
3. After processing, delete the consumed snapshots:
   ```bash
   rm $PROJECT/.claude/pre-compaction-*.md
   ```
```

- [ ] **Step 7: Commit**

```bash
git add skills/session-learnings/SKILL.md
git commit -m "feat: extend session-learnings with memory compilation and pre-compaction processing"
```

---

### Task 3: Update Memory-Injection to Serve Compiled Articles

**Files:**
- Modify: `skills/memory-injection/SKILL.md`
- Modify: `skills/code-creation-workflow/references/memory-injection.md`

- [ ] **Step 1: Read current memory-injection files**

Read both `skills/memory-injection/SKILL.md` and `skills/code-creation-workflow/references/memory-injection.md` to confirm current structure.

- [ ] **Step 2: Add compiled article selection to memory-injection SKILL.md**

After the existing Step 4 (Extract Matching Gotcha Entries), add a new step:

```markdown
### Step 4b: Select Matching Compiled Articles

Check if `knowledge/concepts/` exists in the memory directory. If so:

1. Read all `knowledge/concepts/*.md` files
2. For each article, parse the `sources:` frontmatter list
3. If any source file's semantic key maps to a currently-resolved domain (from Step 3), the article is a match
4. Select up to 3 matching articles, prioritized by:
   - Number of matching source files (more matches = higher priority)
   - Recency (`updated:` date in frontmatter)
```

- [ ] **Step 3: Update the injection format in Step 5**

Modify the existing Step 5 (Format the PROJECT GOTCHAS Block) to include compiled articles:

```markdown
### Step 5: Format the Injection Block

Assemble two sections:

**Section 1 — Raw gotchas (existing format, unchanged):**
```
PROJECT GOTCHAS (verified for this codebase — do not ignore):
- [1-line entry for each matching key]
- [... up to 10 entries]
```

**Section 2 — Compiled knowledge (new):**
```
COMPILED KNOWLEDGE (from knowledge/concepts/):
- [article-slug]: [First 500 chars of Key Points section]
- [... up to 3 articles]
```

**Priority rules:**
- Raw gotchas are always injected first (terse, high-signal)
- Compiled articles supplement, never replace
- If total injection exceeds 2000 chars, truncate compiled article excerpts (not raw gotchas)
- If no compiled articles match, omit Section 2 entirely
```

- [ ] **Step 4: Update Step 6 (Return or Omit) in memory-injection SKILL.md**

The existing Step 6 (line 64) says "return the formatted `PROJECT GOTCHAS` block." Update to cover both sections:

```markdown
### Step 6: Return or Omit

If matches were found in Step 4 or Step 4b, return the formatted injection block (both `PROJECT GOTCHAS` and `COMPILED KNOWLEDGE` sections, omitting either section if it has no matches). If neither section has matches, omit the entire block — do not return an empty section.
```

- [ ] **Step 5: Update the memory-injection reference doc**

Add to `skills/code-creation-workflow/references/memory-injection.md` after the existing injection template:

```markdown
## Compiled Knowledge Injection

When `knowledge/concepts/` exists in the memory directory, compiled articles are injected after raw gotchas.

### Selection

A compiled article matches a domain when any of its `sources:` files map to that domain via the domain table above.

### Template

```
COMPILED KNOWLEDGE (from knowledge/concepts/):
- [sqlalchemy-gotchas]: Property model uses synonyms; always check `synonym()` calls before renaming columns. Session handling requires...
```

### Limits

- Max 3 articles per injection
- Each article excerpt: first 500 chars of `## Key Points` section
- Total injection (raw + compiled): max 2000 chars — truncate compiled excerpts if exceeded
```

- [ ] **Step 6: Commit**

```bash
git add skills/memory-injection/SKILL.md skills/code-creation-workflow/references/memory-injection.md
git commit -m "feat: update memory-injection to serve compiled knowledge articles"
```

---

### Task 4: Integration Test — Manual Walkthrough

**Files:** None (verification only)

- [ ] **Step 1: Verify directory structure expectations**

Check that the skill files reference consistent paths:
- `skills/lint-memory/SKILL.md` references `knowledge/concepts/`
- `skills/session-learnings/SKILL.md` references `knowledge/concepts/` and creates it with `mkdir -p`
- `skills/memory-injection/SKILL.md` references `knowledge/concepts/`

```bash
grep -n "knowledge/concepts" skills/lint-memory/SKILL.md skills/session-learnings/SKILL.md skills/memory-injection/SKILL.md
```

Expected: consistent path references across all three skills.

- [ ] **Step 2: Verify lint skill is invocable**

Check the skill frontmatter has `invocation: user` so it appears as `/lint-memory`.

```bash
head -5 skills/lint-memory/SKILL.md
```

Expected: frontmatter with `name: lint-memory` and `invocation: user`.

- [ ] **Step 3: Verify session-learnings compilation is positioned correctly**

Read the updated session-learnings skill and verify:
1. Pre-compaction snapshot processing comes before code context analysis (before memory writing)
2. Compilation (Step 2b) comes after memory writing
3. Quick lint (checks 1-2) comes after compilation
4. Commit sequencing has the graceful degradation fallback

```bash
grep -n "Step 2b\|Pre-Compaction\|Quick Lint\|Commit Sequencing" skills/session-learnings/SKILL.md
```

- [ ] **Step 4: Verify memory-injection has consistent limits**

Check that the 2000 char limit, 3 article max, and 500 char excerpt limit appear in both:
- `skills/memory-injection/SKILL.md`
- `skills/code-creation-workflow/references/memory-injection.md`

```bash
grep -n "2000\|500\|3 article\|3 compiled" skills/memory-injection/SKILL.md skills/code-creation-workflow/references/memory-injection.md
```

- [ ] **Step 5: Verify no spec drift**

Compare the implementation against key spec requirements:
- Compilation is additive (never deletes raw files)
- Raw files are source of truth
- Graceful degradation on compilation failure
- Orphan detection excludes operational files
- Connection articles NOT implemented (v2)
- Shared cross-project layer NOT implemented (v2)

Read each skill file and confirm these constraints are honored.

- [ ] **Step 6: Final commit if any fixes were needed**

```bash
git add -A && git commit -m "fix: address integration test findings" || echo "nothing to commit"
```
