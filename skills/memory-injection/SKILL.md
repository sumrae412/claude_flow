---
name: memory-injection
description: Inject project-specific gotchas from MEMORY.md into subagent prompts. Used internally by code-creation-workflow before dispatching Phase 2/4/5/6 subagents. Prevents known mistakes from recurring.
user-invocable: false
---

# Memory Injection

## Purpose

Reads the project's MEMORY.md, matches entries to the current task's file scope, and returns a `PROJECT GOTCHAS` block for the caller to append to subagent prompts. This prevents known mistakes from recurring across sessions and agents.

For the full domain → gotcha key mapping table, see `code-creation-workflow/references/memory-injection.md`.

## Process

### Step 1: Find MEMORY.md

Check these locations in order:

1. `$PROJECT/.claude/memory/MEMORY.md`
2. `$PROJECT/MEMORY.md`

If neither exists → **graceful no-op**: skip injection entirely, return nothing. Do not error. (Bootstrap is owned by `code-creation-workflow` Phase 0 Step 8 — do not duplicate it here.)

### Step 2: Accept Input

The caller provides a list of file paths that will be touched during this task. These come from:
- Phase 2 exploration findings (the deduplicated file list from context hydration)
- The plan's "files to create/modify" list (available by Phase 4 onward)

### Step 3: Match File Paths to Domains

Compare each file path against the domain table in `code-creation-workflow/references/memory-injection.md`. A file can match multiple domains. Collect all matched domains.

Examples:
- `services/client_service.py` → `services` domain
- `models/client.py` + `alembic/versions/abc.py` → `models` domain
- `templates/clients.html` + `static/app.css` → `ui` domain

### Step 4: Extract Matching Gotcha Entries

For each matched domain, look up the gotcha keys listed in the domain table. Find the corresponding 1-line entries in MEMORY.md by semantic key. Extract only the entries whose keys appear in the matched domains' key lists.

### Step 4b: Select Matching Compiled Articles

Check if `knowledge/concepts/` exists in the memory directory. If so:

1. Read all `knowledge/concepts/*.md` files
2. For each article, parse the `sources:` frontmatter list
3. Map each source file path to domains using the same file-pattern matching from Step 3. If any resolved domain overlaps with the task's resolved domains, the article is a match
4. Select up to 3 matching articles, prioritized by:
   - Number of matching source files (more matches = higher priority)
   - Recency (`updated:` date in frontmatter)

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
- If total injection exceeds 2000 chars, truncate compiled article excerpts with `... [truncated]` (not raw gotchas)
- If no compiled articles match, omit Section 2 entirely

**Priority when more than 10 raw gotcha entries match** (truncate to 10, highest priority first — this applies only to Section 1; compiled articles have their own cap of 3):
1. Exact file match — the gotcha mentions a specific file being touched
2. Direct domain match — the file pattern matches the primary domain
3. Cross-cutting concern — the gotcha applies broadly (e.g., `no-aliases`, `counts-endpoint`)

If truncated, append: `[N more gotchas omitted — see MEMORY.md]`

### Step 6: Return or Omit

If matches were found in Step 4 or Step 4b, return the formatted injection block (both `PROJECT GOTCHAS` and `COMPILED KNOWLEDGE` sections, omitting either section if it has no matches). If neither section has matches, omit the entire block — do not return an empty section.

## Usage Points

This skill is invoked internally by `code-creation-workflow` at four points:

| Phase | When | What's injected into |
|-------|------|---------------------|
| Phase 2 | After exploration completes, file list is known | All subsequent subagent prompts |
| Phase 4 | Architect subagent dispatch | Each architect's prompt |
| Phase 5 | Implementation subagent dispatch | Each implementation subagent's prompt |
| Phase 6 | Review subagent dispatch | Each reviewer's prompt |

The block returned at Phase 2 is reused for Phases 4–6 unless the file scope changes significantly (e.g., new files added during plan refinement).
