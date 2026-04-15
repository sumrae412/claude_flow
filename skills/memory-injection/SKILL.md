---
name: memory-injection
description: Inject project-specific gotchas from MEMORY.md into subagent prompts. Used internally by claude-flow before dispatching Phase 2/4/5/6 subagents. Prevents known mistakes from recurring.
user-invocable: false
---

# Memory Injection

## Purpose

Reads the project's MEMORY.md, matches entries to the current task's file scope, and returns a `PROJECT GOTCHAS` block for the caller to append to subagent prompts. This prevents known mistakes from recurring across sessions and agents.

For the full domain → gotcha key mapping table, see `claude-flow/references/memory-injection.md`.

## Process

### Step 1: Find MEMORY.md

Check these locations in order:

1. `$PROJECT/.claude/memory/MEMORY.md`
2. `$PROJECT/MEMORY.md`

If neither exists → **graceful no-op**: skip injection entirely, return nothing. Do not error. (Bootstrap is owned by `claude-flow` Phase 0 Step 8 — do not duplicate it here.)

### Step 2: Accept Input

The caller provides a list of file paths that will be touched during this task. These come from:
- Phase 2 exploration findings (the deduplicated file list from context hydration)
- The plan's "files to create/modify" list (available by Phase 4 onward)

### Step 3+4: Match File Paths to Domains and Extract Gotcha Entries (script)

**Use the script — do not do this work in prose.** File-pattern matching and key lookup are mechanical operations. The LLM's job is to format and prioritize the result, not to walk the table.

```bash
python3 skills/claude-flow/scripts/match_memory_domains.py \
    <memory_dir> \
    --reference skills/claude-flow/references/memory-injection.md \
    file1.py file2.py file3.html
```

Or via stdin:

```bash
echo -e "file1.py\nfile2.py" | python3 skills/claude-flow/scripts/match_memory_domains.py <memory_dir>
```

Output (JSON) gives you everything you need:

```json
{
  "matched_domains": ["services", "models", "ui"],
  "matched_keys": ["client-sync-map", "is-primary-contact", "..."],
  "matched_entries": [
    {"key": "is-primary-contact", "line": "- [...](...) — ...", "topic_file": "is_primary_contact.md"}
  ],
  "skipped": ["alembic-cli-only"]
}
```

Notes on the script's behavior:
- A file can match multiple domains; all matched gotcha keys are returned (deduplicated)
- Keys present in the domain table but missing from MEMORY.md show up in `skipped` — surface them or ignore depending on caller intent
- The script handles glob portability (`models/*` matches both `app/models/foo.py` and `models/foo.py`)
- Stdlib only — no install needed

Examples (reference; the script enforces them):
- `services/client_service.py` → `services` domain
- `models/client.py` + `alembic/versions/abc.py` → `models` domain
- `templates/clients.html` + `static/app.css` → `ui` domain

When NOT to use the script: if `claude-flow/references/memory-injection.md` doesn't exist (e.g., a project hasn't installed claude-flow), fall back to a graceful no-op — don't try to match by hand.

### Step 4a: 1-Hop Expansion via `## Related`

After Step 4 produces its initial matches, walk the matched memory files for a `## Related` section and pull in neighbor entries. This surfaces connective tissue that file-pattern matching alone misses — e.g., a gotcha about Phase 3 quality gate is more useful if the design decision that introduced it also comes along.

**Convention:** Memory files may declare relationships with a plain-markdown footer (no frontmatter migration required):

```markdown
## Related
- [slug] — why it's related (one line)
- [other-slug] — ...
```

Where `slug` matches a filename in the memory directory without the `.md` extension (e.g. `fold_check_upstream` → `fold_check_upstream.md`).

**Expansion rules:**
1. For each file matched in Step 4, open it and grep for `## Related`. If absent, move on.
2. Parse `- [slug] — ...` bullets. Resolve each slug to a file path; skip if the file doesn't exist.
3. Collect expanded entries. Deduplicate against Step 4 matches (by filename).
4. Cap total expansion at **3 additional entries** across all matched files combined. These 3 entries are **additive** — they do NOT count toward Section 1's 10-entry cap (see Step 5). When more than 3 candidates exist, select deterministically:
   - **Score:** co-citation count = number of matched files whose `## Related` list names this slug.
   - **Rank:** descending by co-citation count.
   - **Tiebreak:** ascending alphabetical slug order (stable across runs).
   - **Fallback:** if fewer than 3 slugs are co-cited (score ≥ 2), fill remaining slots with singly-cited candidates using the same alphabetical tiebreak. If fewer than 3 candidates exist total, include all of them (the cap is a ceiling, not a target).
5. Emit expanded entries into Section 1 of the injection block, tagged as `[related]` so the subagent sees they were pulled via 1-hop:

```
PROJECT GOTCHAS (verified for this codebase — do not ignore):
- [direct match entry]
- [direct match entry]
- [related] [expanded entry from ## Related footer]
```

**When this is empty:** most existing memory files don't have `## Related` footers yet. That's fine — Step 4a is a graceful no-op in that case. The backfill compilation (Step 4b) provides relational coverage via compiled concept articles; Step 4a becomes more useful as new entries are written with `## Related` footers going forward.

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
- [... up to 10 direct-match entries]
- [related] [up to 3 additional entries from Step 4a, appended after direct matches]
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

**Priority when more than 10 raw gotcha entries match** (truncate to 10, highest priority first — this applies only to direct matches from Step 4; Step 4a `[related]` expansions and Step 4b compiled articles have their own caps and are not subject to this truncation):
1. Exact file match — the gotcha mentions a specific file being touched
2. Direct domain match — the file pattern matches the primary domain
3. Cross-cutting concern — the gotcha applies broadly (e.g., `no-aliases`, `counts-endpoint`)

If truncated, append: `[N more gotchas omitted — see MEMORY.md]`. The Section 1 render order is: up to 10 direct-match entries first, then up to 3 `[related]` entries appended. Total Section 1 entries therefore cap at 13 (10 + 3), not 10.

### Step 5b: Check Abandoned Approaches

Check if `$PROJECT/.claude/abandoned/` exists. If so:

1. Read all `.md` files in the directory
2. For each file, extract the "What was attempted" and "Why abandoned" sections
3. Include up to 3 most recent entries (sorted by filename = date order)

Format as a third section:

```
PREVIOUSLY RULED OUT (from .claude/abandoned/):
- <topic> (YYYY-MM-DD): <1-line summary of why abandoned>
- ...
```

**Priority rules:**
- Only include entries less than 30 days old (stale abandonments are less relevant)
- If more than 3 entries match, keep the 3 most recent
- This section supplements but never replaces Sections 1-2

### Step 6: Return or Omit

If matches were found in Step 4, Step 4b, or Step 5b, return the formatted injection block (all applicable sections: `PROJECT GOTCHAS`, `COMPILED KNOWLEDGE`, and `PREVIOUSLY RULED OUT`, omitting any section with no matches). If no section has matches, omit the entire block — do not return an empty section.

## Usage Points

This skill is invoked internally by `claude-flow` at four points:

| Phase | When | What's injected into |
|-------|------|---------------------|
| Phase 2 | After exploration completes, file list is known | All subsequent subagent prompts |
| Phase 4 | Architect subagent dispatch | Each architect's prompt |
| Phase 5 | Implementation subagent dispatch | Each implementation subagent's prompt |
| Phase 6 | Review subagent dispatch | Each reviewer's prompt |

The block returned at Phase 2 is reused for Phases 4–6 unless the file scope changes significantly (e.g., new files added during plan refinement).
