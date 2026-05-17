# Memory Compilation & Knowledge Lint

**Date:** 2026-04-10
**Status:** Design approved
**Inspired by:** [claude-memory-compiler](https://github.com/coleam00/claude-memory-compiler) (Karpathy's LLM Knowledge Base architecture)

## Problem

Claude-flow's memory system grows linearly — each session-learnings run appends individual memory files. Over time this creates fragmentation: related knowledge is scattered across `feedback_silent_failures.md`, `feedback_error_handling.md`, and inline MEMORY.md entries. There's no consolidation, no cross-referencing between related memories, and no way to detect when memories become stale or contradictory.

## Solution

Three additions to the existing memory system:

1. **Memory compilation** — consolidate related memory files into concept articles
2. **Knowledge lint** — 4 health checks to catch broken links, orphans, staleness, and contradictions
3. **Pre-compaction knowledge extraction** — enrich pre-compaction snapshots so session-learnings can process them

All three integrate into the existing session-learnings skill. No new hooks required.

## Scope

- **v1 (this spec):** Project-scoped compilation only. Each project compiles its own memories.
- **v2 (future):** Shared cross-project layer at `~/.claude/knowledge/` for patterns appearing in 2+ projects. Deferred because concurrent compilation across projects requires a concurrency model (file locking, conflict resolution) that adds complexity without proven value yet.
- Approach A (compile-on-write): compilation runs as an extension of session-learnings, not a separate pipeline

---

## 1. Directory Structure

### Per-project (new `knowledge/` subdir)

```
<project>/memory/
├── MEMORY.md                    # Existing index (format unchanged)
├── feedback_*.md                # Existing raw memory files (untouched)
├── reference_*.md               # Existing raw memory files (untouched)
├── knowledge/                   # NEW — compiled articles
│   └── concepts/                # Consolidated knowledge per topic
│       ├── sqlalchemy-gotchas.md
│       └── auth-middleware-patterns.md
```

> **v2:** Shared cross-project layer at `~/.claude/knowledge/` with its own `index.md`. Deferred — see Scope.

### Compiled article format (concept)

```markdown
---
title: "SQLAlchemy Gotchas"
sources:
  - feedback_silent_failures.md
  - feedback_model_patterns.md
compiled: 2026-04-10
updated: 2026-04-10
---

# SQLAlchemy Gotchas

[Consolidated knowledge from multiple memory files]

## Key Points
- ...

## Related
- [[concepts/auth-middleware-patterns]] — shares session handling concerns
```

> **Note:** Connection articles (cross-cutting insights linking 2+ concepts) are deferred to v2. In v1, concept articles use `## Related` cross-links to reference each other.

### MEMORY.md evolution

Existing entries unchanged. Compiled articles added as links:

```markdown
**sqlalchemy-gotchas:** → See [knowledge/concepts/sqlalchemy-gotchas.md](knowledge/concepts/sqlalchemy-gotchas.md)
```

---

## 2. Compilation Logic

Runs as an extension of the session-learnings background agent, after it writes/updates individual memory files and before it commits.

### Algorithm

1. **Inventory** — Read all `feedback_*.md` and `reference_*.md` files in `memory/` (ignoring MEMORY.md, `knowledge/` dir, `*.jsonl`, `*.json`, and `failure-catalog.md`). Read existing `knowledge/concepts/*.md`.

2. **Cluster (LLM judgment)** — The agent reads the inventory and groups memory files into topic clusters. This is an LLM judgment step, not a deterministic algorithm. The agent is prompted with:

   ```
   Given these memory files and their contents, group them into topic clusters.
   Each cluster should represent a single coherent concept (e.g., "error handling patterns",
   "data model gotchas", "deployment procedures").

   Rules:
   - A memory file can belong to at most ONE cluster
   - If a file doesn't fit any cluster, leave it unclustered (it stays as a standalone memory)
   - Prefer fewer, broader clusters over many narrow ones
   - Name each cluster with a kebab-case slug (e.g., "error-handling-patterns")

   Output format (JSON):
   {
     "clusters": [
       {"slug": "error-handling-patterns", "files": ["feedback_silent_failures.md", "feedback_error_handling.md"], "summary": "..."},
       ...
     ],
     "unclustered": ["reference_api_keys.md", ...]
   }
   ```

   Example: `feedback_silent_failures.md` + `feedback_error_handling.md` + try/catch pattern entries → cluster "error-handling-patterns".

3. **Merge or update** — For each cluster:
   - If a matching `knowledge/concepts/<slug>.md` article exists → update it with new information, add source to frontmatter
   - If no match → create new concept article
   - Cross-references: if two concept articles share overlapping source files or related topics, add `## Related` links between them

4. **Update index** — Add links to new/updated compiled articles in MEMORY.md.

5. **Commit** — See commit sequencing below.

### Commit Sequencing

```
1. Write raw memory files (session-learnings existing behavior)
2. Attempt compilation (steps 1-4 above)
3. git add . && git commit   (covers both raw + compiled)
4. If compilation errored at any step:
   - git add only raw memory files
   - git commit with "[partial] session-learnings: <summary>"
   - Log compilation error to stderr
```

### Constraints

- Compilation is **additive** — never deletes or modifies raw memory files
- Raw files are source of truth; compiled articles are derived
- If compilation fails or times out, raw memory files are still committed (graceful degradation — see commit sequencing above)

---

## 3. Knowledge Lint (4 Checks)

### Invocation

- **Manual:** New `/lint-memory` skill
- **During compilation:** Checks 1-2 run automatically (fast, deterministic) after merge/update, before commit. Agent auto-fixes what it can, reports the rest.
- **Checks 3-4:** Only run when `/lint-memory` is invoked explicitly (expensive, require LLM judgment or codebase scanning).

### Checks

#### Check 1: Broken Links (auto, auto-fixable)
Scan MEMORY.md and all `knowledge/*.md` for markdown links and `[[wikilinks]]`. Verify each target file exists. **Severity:** error. **Fix:** remove dead links.

#### Check 2: Orphan Memories (auto, auto-fixable)
Find `memory/*.md` files matching `feedback_*.md` or `reference_*.md` patterns that have no entry in MEMORY.md and aren't referenced by any compiled article. Excludes operational data files (`*.jsonl`, `*.json`, `failure-catalog.md`, `prompt-variants.json`). **Severity:** warning. **Fix:** add index entry to MEMORY.md.

#### Check 3: Stale Entries (manual only)
For memories referencing specific files/functions (detected by code-like patterns), grep the codebase to check references still exist. Example: memory says "model file is `property.py`" but file was renamed. **Severity:** warning. **Fix:** flag for human review.

#### Check 4: Contradictions (manual only)
Compare entries within the same concept domain for conflicting claims. Requires LLM judgment. Example: one entry says "always use `is_active` filter," another says "skip `is_active`, use `status` only." **Severity:** error. **Fix:** flag for human review.

### Output

Markdown report printed to terminal. Non-auto-fixable issues listed with file paths and excerpts.

---

## 4. Pre-Compaction Knowledge Extraction

### Current behavior (unchanged trigger, unchanged hook)

`pre-compaction-backup.sh` fires on PreCompact, writes `.claude/pre-compaction-<timestamp>.md`. **The hook script itself is not modified** — it continues to capture git state (branch, commits, status, recent diff).

### What changes: session-learnings processes snapshots

The hook captures what a bash script can see (filesystem/git state). The knowledge extraction happens later, when session-learnings runs:

1. Session-learnings background agent checks for any `.claude/pre-compaction-*.md` files created since the last compilation
2. It reads the git state from those snapshots (files touched, branches, diffs) and incorporates this context into its knowledge extraction — giving it visibility into work that happened before context compaction
3. After processing, it deletes the consumed snapshot files

No separate Agent SDK call from the hook. No new conversation context needed by the hook. The hook captures git state; session-learnings adds the intelligence.

---

## 5. Memory-Injection Integration

The existing memory-injection skill maps file-path domains (models, services, ui, routes, etc.) to specific semantic keys in MEMORY.md. Compiled articles need equivalent treatment.

### Selection criteria

When memory-injection resolves a domain (e.g., "models"), it:
1. Collects matching 1-line gotcha entries from MEMORY.md (existing behavior, unchanged)
2. **NEW:** Checks if any `knowledge/concepts/*.md` articles list matching source files in their `sources:` frontmatter. If a source file's semantic key maps to the resolved domain, the concept article is selected.

### Injection format

Compiled articles are injected differently from raw gotchas:

```
PROJECT GOTCHAS (from MEMORY.md):
- model-file-name: Model file is `property.py` not `household.py`
- synonym-aliases: `property_id = synonym("household_id")` used throughout

COMPILED KNOWLEDGE (from knowledge/concepts/):
- [sqlalchemy-gotchas]: Key Points section (truncated to first 500 chars)
```

### Priority rules

- Raw gotchas are always injected first (they're terse, high-signal)
- Compiled articles supplement, never replace, raw gotchas
- If total injection exceeds 2000 chars, truncate compiled article excerpts (not raw gotchas)
- Max 3 compiled articles per injection to avoid context bloat

---

## What Changes

| Component | Change |
|-----------|--------|
| `session-learnings/SKILL.md` | Extended: compilation step after writing memories, lint checks 1-2 before commit, pre-compaction snapshot processing |
| `memory/knowledge/concepts/` | New directory: compiled concept articles |
| New skill: `/lint-memory` | Runs all 4 lint checks on demand |
| `memory-injection/SKILL.md` | Updated: injects compiled article excerpts alongside raw gotchas (see Section 5) |
| `MEMORY.md` format | Extended: links to compiled articles alongside existing entries |

## What Doesn't Change

- Raw memory file creation (session-learnings still writes individual files)
- MEMORY.md semantic key format
- Hook triggers and hook scripts (no new hooks, no hook modifications)
- Memory-injection domain mapping (extended, not replaced)
- Failure catalog (separate system, untouched)
- `pre-compaction-backup.sh` (unchanged — session-learnings processes its output)

## Deferred to v2

- Shared cross-project layer (`~/.claude/knowledge/`) — requires concurrency model
- Connection articles (`knowledge/connections/`) — concept `## Related` links sufficient for v1
