# Memory Injection for Subagents

> **Maintenance:** Update this file when gotcha semantic keys are added/removed in MEMORY.md.
> Domain tags map file patterns to relevant project gotchas. When a new gotcha is added to MEMORY.md,
> add its semantic key to the appropriate domain(s) below.

## How It Works

1. After Phase 2 exploration, the orchestrator knows which files will be touched
2. Match file patterns against the domain table below
3. Extract the matching 1-line gotcha entries from MEMORY.md by semantic key
4. Include them in the `[PROJECT_GOTCHAS]` section of every subsequent subagent prompt
5. **If no domains match, omit the PROJECT_GOTCHAS section entirely** (graceful fallback)

## Domain → Gotcha Mapping

| Domain | File Patterns | Gotcha Keys |
|--------|--------------|-------------|
| models | `models/*`, `alembic/*` | `model-file-name`, `synonym-aliases`, `builtin-property`, `enum-uppercase`, `is-primary-contact`, `alembic-cli-only`, `eventmeta-no-userid`, `competing-heads` |
| services | `services/*` | `client-sync-map`, `phone-dedup`, `no-aliases`, `client-dual-filter`, `total-vs-active`, `counts-endpoint` |
| ui | `templates/*`, `*.css`, `*.js` | `tenant-stats-keys`, `one-pattern-per-page`, `counts-endpoint` |
| routes | `routes/*` | `client-dual-filter`, `counts-endpoint`, `no-aliases` |
| deploy | Railway operations, `requirements.txt` | `boto3-chain`, `verify-deploy` |
| git | merge/PR operations | `worktree-merge`, `competing-heads`, `conflict-duplicates`, `name-collision`, `superseded-pr`, `class-aware-grep` |
| testing | `tests/*` | `test-db`, `pg-only`, `db-module-path` |

## Injection Template

Add to the universal subagent prompt after `[TASK_DESCRIPTION + EXPLORATION_FINDINGS]`:

```
PROJECT GOTCHAS (verified for this codebase — do not ignore):
- [1-line entry from MEMORY.md for each matching key]
- [... max ~10 entries, prioritize exact file matches over directory matches]
```

## Priority When >10 Matches

If domain filtering produces more than 10 entries:
1. Exact file match (gotcha mentions a specific file being touched) — highest
2. Direct domain match (file pattern matches the primary domain) — medium
3. Cross-cutting concern (gotcha applies broadly, e.g., `no-aliases`) — lowest

Truncate at 10 with a note: `[N more gotchas omitted — see MEMORY.md]`

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
