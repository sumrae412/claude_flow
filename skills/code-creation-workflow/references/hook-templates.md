# Hook Templates Reference

Reference for Phase 0.5 (Bootstrap Project Hooks). Claude consults this to detect the project stack and select hooks from the registry.

> **Source of truth:** All hook definitions live in `hooks/hook-registry.json`. Phase 0.5 no longer hardcodes inline templates — it reads the registry and uses `install.sh --generate-hooks` to write the project's `.claude/settings.json` hook entries.

---

## Stack Detection

Check for these signal files/dirs at the project root. Each match adds a tag to the stack profile.

| Signal | Stack Tag |
|--------|-----------|
| `requirements.txt` OR `pyproject.toml` | `python` |
| `package.json` | `node` |
| `Cargo.toml` | `rust` |
| `go.mod` | `go` |
| `alembic/` OR `alembic.ini` | `alembic` |
| `**/models/*.py` OR `**/models.py` | `orm` |
| `**/services/` | `service-layer` |
| `**/templates/` (Jinja/Django/etc.) | `server-templates` |
| `static/css/` OR `public/` OR `src/styles/` | `static-assets` |
| `.env` | `has-env` |
| `Dockerfile` OR `docker-compose.yml` | `docker` |
| `ruff` in pyproject.toml `[tool.ruff]` | `ruff` |
| `eslint` in package.json deps or `.eslintrc*` | `eslint` |
| `flake8` in setup.cfg/tox.ini/pyproject.toml | `flake8` |
| `pytest` in pyproject.toml or `conftest.py` | `pytest` |
| `jest` in package.json deps or `jest.config.*` | `jest` |
| `tsconfig.json` | `typescript` |

---

## Hook Registry

All Tier 1 and Tier 2 hook templates are defined in **`hooks/hook-registry.json`** (repo root). Do not edit hook definitions here — update the registry instead.

### Registry Schema

Each entry in the `hooks` array has the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique hook identifier (kebab-case) |
| `tier` | number | `1` = universal, `2` = conditional (requires stack tags) |
| `trigger` | string | Claude hook event: `PreToolUse`, `PostToolUse`, `SessionStart`, `PreCompact` |
| `matcher` | array\|null | Tool matchers (e.g. `["Edit", "Write"]`, `["Bash(git commit*)"]`). `null` for session-level triggers. |
| `script` | string | Path to the hook script, relative to the repo root |
| `description` | string | Human-readable summary of what the hook does |
| `stack_tags` | array | *(Tier 2 only)* Stack tags that must be present for this hook to be generated |

### Tier 1 — Universal Hooks

These hooks are generated for every project regardless of stack. Current Tier 1 entries in the registry:

| id | trigger | description |
|----|---------|-------------|
| `secret-detection` | PreToolUse (Edit, Write) | Blocks edits introducing secrets |
| `large-file-warning` | PreToolUse (Edit) | Warns when editing files >500 lines |
| `missing-test-companion` | PostToolUse (Write) | Suggests test file for new source files |
| `dangerous-git-ops` | PreToolUse (Bash — force push/reset) | Blocks dangerous git commands |
| `uncommitted-work-guard` | PreToolUse (Bash — git checkout) | Warns on branch switch with uncommitted changes |
| `build-before-commit` | PreToolUse (Bash — git commit) | Runs lint/typecheck before commit |
| `todo-cleanup` | PostToolUse (Bash — git commit) | Surfaces TODO/FIXME/HACK after commit |
| `session-context-loader` | SessionStart | Loads context + handoff on start |
| `pre-compaction-backup` | PreCompact | Saves transcript before compression |
| `worktree-cleanup` | SessionStart | Cleans stale worktrees |

### Tier 2 — Conditional Hooks

These hooks are generated only when the detected stack profile includes the required tags. Current Tier 2 entries in the registry:

| id | trigger | required stack_tags | description |
|----|---------|---------------------|-------------|
| `lint-on-save-python` | PostToolUse (Edit *.py) | `ruff` OR `flake8` | Runs Python linter on save |
| `lint-on-save-js` | PostToolUse (Edit *.js/ts/jsx/tsx) | `eslint` | Runs ESLint on save |
| `test-on-save-python` | PostToolUse (Edit app/**/*.py) | `pytest` | Runs pytest on save |
| `test-on-save-js` | PostToolUse (Edit src/**/*.js/ts/tsx) | `jest` | Runs Jest on save |
| `migration-sequence-check` | PostToolUse (Write alembic/versions/*.py) | `alembic` | Checks Alembic migration sequence |
| `type-check-on-save` | PostToolUse (Edit *.ts/tsx) | `typescript` | Runs TypeScript type check on save |
| `docker-rebuild-reminder` | PostToolUse (Edit Dockerfile*/docker-compose*) | `docker` | Reminds to rebuild Docker image after config changes |

### Generating Hooks for a Project

After stack detection, Phase 0.5 generates hooks by running:

```bash
./install.sh --generate-hooks
```

This reads `hooks/hook-registry.json`, filters Tier 2 hooks against the detected stack tags, and writes the resulting hook entries into the project's `.claude/settings.json`.

To regenerate after updating the registry or adding stack tags, run the same command again — it is idempotent.

---

## Tier 3 — Project-Specific Hooks

Tier 3 hooks are not in the registry. They are project-specific and user-configured, defined directly in the project's `.claude/settings.json` after bootstrap. Examples include:

- Custom deployment guards (e.g. block edits to production config files)
- Project-specific commit message format enforcement
- Team-specific reminder hooks tied to internal tooling

These are outside the scope of Phase 0.5 automation and must be added manually.
