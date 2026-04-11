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

- Project-scoped compilation (each project compiles its own memories)
- Shared cross-project layer at `~/.claude/knowledge/` for patterns appearing in 2+ projects
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
│   ├── concepts/                # Consolidated knowledge per topic
│   │   ├── sqlalchemy-gotchas.md
│   │   └── auth-middleware-patterns.md
│   └── connections/             # Cross-cutting insights linking 2+ concepts
│       └── auth-and-session-management.md
```

### Shared cross-project layer

```
~/.claude/knowledge/             # NEW — cross-project patterns
├── index.md                     # Shared knowledge index
├── concepts/                    # Patterns valid across all projects
└── connections/                 # Cross-project insights
```

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

### Connection article format

```markdown
---
title: "Auth and Session Management"
connects:
  - concepts/auth-middleware-patterns
  - concepts/sqlalchemy-gotchas
sources:
  - feedback_auth_patterns.md
  - feedback_session_handling.md
compiled: 2026-04-10
updated: 2026-04-10
---

# Auth and Session Management

## The Connection
[What links these concepts — the non-obvious relationship]

## Key Insight
[Actionable takeaway]
```

### MEMORY.md evolution

Existing entries unchanged. Compiled articles added as links:

```markdown
**sqlalchemy-gotchas:** → See [knowledge/concepts/sqlalchemy-gotchas.md](knowledge/concepts/sqlalchemy-gotchas.md)
```

---

## 2. Compilation Logic

Runs as an extension of the session-learnings background agent, after it writes/updates individual memory files and before it commits.

### Algorithm

1. **Inventory** — Read all `*.md` files in `memory/` (excluding MEMORY.md and the `knowledge/` dir). Read existing `knowledge/concepts/*.md` and `knowledge/connections/*.md`.

2. **Cluster** — Group memory files by topic similarity. The agent uses semantic keys from MEMORY.md plus file content to identify clusters. Example: `feedback_silent_failures.md` + `feedback_error_handling.md` + try/catch pattern entries → single "error-handling-patterns" concept.

3. **Merge or update** — For each cluster:
   - If a matching `knowledge/concepts/` article exists → update it with new information, add source to frontmatter
   - If no match → create new concept article
   - If the cluster spans 2+ existing concepts → create a `knowledge/connections/` article

4. **Promote to shared** — If a concept appears in 2+ projects (check `~/.claude/knowledge/index.md`), copy/merge to `~/.claude/knowledge/concepts/`. Shared layer contains only project-agnostic patterns.

5. **Update index** — Add links to new/updated compiled articles in MEMORY.md. Update `~/.claude/knowledge/index.md` if shared articles changed.

6. **Commit** — Single commit covering raw memory files + compiled articles.

### Constraints

- Compilation is **additive** — never deletes or modifies raw memory files
- Raw files are source of truth; compiled articles are derived
- If compilation fails or times out, raw memory files are still committed (graceful degradation)

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
Find `memory/*.md` files with no entry in MEMORY.md and not referenced by any compiled article. **Severity:** warning. **Fix:** add index entry to MEMORY.md.

#### Check 3: Stale Entries (manual only)
For memories referencing specific files/functions (detected by code-like patterns), grep the codebase to check references still exist. Example: memory says "model file is `property.py`" but file was renamed. **Severity:** warning. **Fix:** flag for human review.

#### Check 4: Contradictions (manual only)
Compare entries within the same concept domain for conflicting claims. Requires LLM judgment. Example: one entry says "always use `is_active` filter," another says "skip `is_active`, use `status` only." **Severity:** error. **Fix:** flag for human review.

### Output

Markdown report printed to terminal. Non-auto-fixable issues listed with file paths and excerpts.

---

## 4. Pre-Compaction Knowledge Extraction

### Current behavior (unchanged trigger)

`pre-compaction-backup.sh` fires on PreCompact, writes `.claude/pre-compaction-<timestamp>.md`.

### Enhanced snapshot format

```markdown
## Git State
(existing: branch, commits, status)

## Session Context Markers
- Files touched this session: [list from git diff]
- Key decisions made: [extracted from conversation if available]
- Unfinished work: [task list state if available]
```

### Integration with session-learnings

When the session-learnings background agent runs after a commit, it also checks for any `.claude/pre-compaction-*.md` files created since the last compilation. It incorporates their context markers into knowledge extraction, then deletes the processed snapshot files.

No separate Agent SDK call from the hook. The hook enriches data; session-learnings processes it.

---

## What Changes

| Component | Change |
|-----------|--------|
| `session-learnings/SKILL.md` | Extended: compilation step after writing memories, lint checks 1-2 before commit |
| `memory/knowledge/` | New directory: compiled concept and connection articles |
| `~/.claude/knowledge/` | New directory: shared cross-project patterns |
| `pre-compaction-backup.sh` | Enhanced: structured context markers in snapshot |
| New skill: `/lint-memory` | Runs all 4 lint checks on demand |
| `memory-injection/SKILL.md` | Updated: also injects relevant compiled articles into subagent prompts |
| `MEMORY.md` format | Extended: links to compiled articles alongside existing entries |

## What Doesn't Change

- Raw memory file creation (session-learnings still writes individual files)
- MEMORY.md semantic key format
- Hook triggers (no new hooks)
- Memory-injection domain mapping (extended, not replaced)
- Failure catalog (separate system, untouched)
