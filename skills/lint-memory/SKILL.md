---
name: lint-memory
description: Run health checks on project memory files — broken links, orphan memories, stale entries, contradictions
user-invocable: true
---

# Lint Memory

## Overview

Run 4 health checks against a project's memory directory to catch broken references, forgotten files, stale code pointers, and contradictory entries. Use this skill to keep memory clean and trustworthy.

The 4 checks, in order:

| # | Check | Severity | Auto-fixable |
|---|-------|----------|--------------|
| 1 | Broken Links | error | yes |
| 2 | Orphan Memories | warning | yes |
| 3 | Stale Entries | warning | no (manual review) |
| 4 | Contradictions | error | no (manual review) |

### When to Use

- Manually via `/lint-memory` — runs all 4 checks
- Automatically during session-learnings compilation — runs checks 1-2 only (quick lint)
- After bulk editing or reorganizing memory files
- Before committing memory changes to catch issues early

## Preconditions

- Locate the project memory directory (the directory containing `MEMORY.md`)
- If the memory directory does not exist, report "No memory directory found" and exit gracefully — this is a no-op, not an error

## Check 1 — Broken Links

**Severity:** error
**Auto-fixable:** yes

### What to scan

- `MEMORY.md`
- All files under `knowledge/` recursively (`knowledge/**/*.md`)

### What to look for

1. **Markdown links** — `[text](path)` where `path` is a relative file reference (skip URLs starting with `http://` or `https://`)
2. **Wikilinks** — `[[path]]` or `[[path|display text]]`

### How to check

For each link target, resolve the path relative to the memory directory and verify the target file exists on disk.

### Auto-fix

Remove the broken link from the source file:
- For markdown links `[text](broken-path)` — replace with just `text` (keep the display text, drop the link)
- For wikilinks `[[broken-path]]` — replace with `broken-path` (keep the text, drop the brackets)
- For wikilinks `[[broken-path|display]]` — replace with `display`

Report every removal before applying it.

## Check 2 — Orphan Memories

**Severity:** warning
**Auto-fixable:** yes

### What to scan

Find all `*.md` files at the top level of the memory directory (one level deep, not recursive). Memory files are named by topic slug (e.g. `compose_dont_replace.md`, `evidence_before_diagnosis.md`), not by `feedback_*` / `reference_*` prefix, so the glob must match reality.

### Exclusions

Skip these files entirely — they are not expected to be referenced:
- `*.jsonl`
- `*.json`
- `failure-catalog.md`
- `prompt-variants.json`
- `MEMORY.md`
- Everything inside subdirectories (`knowledge/`, `episodic/`, `abandoned/`, etc.) — compiled articles and runtime state are not orphan candidates

### What constitutes "orphan"

A file is orphaned if it is NOT referenced by any of:
1. `MEMORY.md` (as a link or plain text filename mention)
2. Any compiled article's `sources:` frontmatter field (`knowledge/**/*.md`)

### Auto-fix

For each orphan file:
1. Generate a semantic key from the filename: strip the `.md` extension, replace underscores/hyphens with spaces (the full topic slug IS the key — do not strip any prefix).
2. Append an index entry to `MEMORY.md`:
   ```
   - **<semantic key>**: [<filename>](<filename>)
   ```

Report every addition before applying it.

## Check 3 — Stale Entries

**Severity:** warning
**Auto-fixable:** no (manual review required)

### What to scan

All top-level `*.md` files in the memory directory (same glob as Check 2, same exclusions), plus `MEMORY.md`.

### What to look for

Backtick-wrapped code references that point to specific codebase artifacts. Use these heuristics to distinguish code references from prose:

- **File references** — backtick content contains `/` or ends in a known source extension (`.py`, `.js`, `.ts`, `.yaml`, `.json`, `.css`, `.html`, `.sh`, `.md`). E.g. `` `src/utils/auth.py` ``, `` `config/settings.yaml` ``
- **Function references** — backtick content starts with `def ` or `function `. E.g. `` `def validate_token` ``, `` `function handleSubmit` ``
- **Class references** — backtick content starts with `class `. E.g. `` `class UserService` ``, `` `class PaymentProcessor` ``

**Ignore** backtick terms that don't match these patterns (e.g. `` `True` ``, `` `pip install` ``, `` `git rebase` ``).

### How to check

1. **File references:** Check if the referenced file exists in the project (resolve relative to project root)
2. **Function references:** Search for the function definition in the codebase (grep for `def func_name` or `function func_name` or `func_name(` at definition sites)
3. **Class references:** Search for the class definition in the codebase (grep for `class ClassName`)

### Output

For each stale reference, report:
- Source file (the memory file containing the reference)
- The stale reference text
- What was expected (file not found / function not found / class not found)

This check cannot auto-fix because removing or updating code references requires human judgment about whether the memory entry itself is still relevant.

## Check 4 — Contradictions

**Severity:** error
**Auto-fixable:** no (manual review required)

### How it works

1. **Group entries by domain** using the domain mapping defined in `skills/claude-flow/references/memory-injection.md`. Each memory file's semantic key or filename determines its domain.

2. **Filter groups** — only check domains with 3 or more entries. Domains with fewer entries rarely contradict.

3. **Detect contradictions** — for each qualifying domain group, use LLM judgment to identify entries that make conflicting claims. Examples:
   - One entry says "always use approach A" while another says "never use approach A"
   - One entry documents a workaround for a bug, another says the bug was fixed
   - One entry recommends a library, another warns against using it

### Output

For each contradiction found, report:
- Domain name
- The conflicting entries (filenames + relevant excerpts)
- Brief explanation of the contradiction

This check cannot auto-fix because resolving contradictions requires human judgment about which entry is correct or whether both need updating.

## Output Format

Produce a markdown report with this structure:

```markdown
# Memory Lint Report

## Errors
<!-- Check 1 (Broken Links) and Check 4 (Contradictions) findings -->
- [broken-link] `MEMORY.md`: link to `missing-file.md` — target not found (auto-fixed: removed link)
- [contradiction] Domain "auth": `feedback_jwt_rotation.md` says "rotate every 24h" vs `feedback_token_expiry.md` says "rotate every 7d"

## Warnings
<!-- Check 2 (Orphan Memories) and Check 3 (Stale Entries) findings -->
- [orphan] `feedback_api_retry_logic.md` — not referenced anywhere (auto-fixed: added to MEMORY.md)
- [stale] `reference_db_schema.md`: references `src/models/legacy_user.py` — file not found

## Summary
- Errors: N (M auto-fixed)
- Warnings: N (M auto-fixed)
- Clean: yes/no
```

## Invocation Modes

### Full Lint (manual `/lint-memory`)

Run all 4 checks in order. Produce the complete report.

### Quick Lint (auto during compilation)

Run checks 1-2 only (Broken Links + Orphan Memories). Skip checks 3-4 to keep compilation fast. Produce an abbreviated report with just the Errors and Warnings from those two checks.

## Important Notes

- **Graceful no-op:** If the memory directory does not exist, report that and exit cleanly. Do not error.
- **Report before fix:** All auto-fixes must be reported to the user before being applied. List what will change, then apply.
- **No commits:** This skill does NOT commit any changes. The caller (user or compilation pipeline) decides when to commit.
- **Path resolution:** All link targets are resolved relative to the memory directory, not the project root. File references in Check 3 are resolved relative to the project root.

---

## Next Steps

- **Found stale code references?** Update memory files manually, then re-run `/lint-memory` to confirm.
- **Fixed broken links or orphans?** Use `/session-learnings` to capture the cleanup as a session event.
- **Memory growing too large?** Review MEMORY.md for entries that duplicate CLAUDE.md content or are no longer load-bearing — remove them.
