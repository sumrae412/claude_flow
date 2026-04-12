# Code Creation Workflow

Unified orchestrator for all feature development. Supersedes brainstorming, writing-plans, executing-plans, test-driven-development, plancraft, and feature-dev.

## Phases

```
Phase 0    Context Loading — load project identity, core skill, classify task
Phase 0.5  Bootstrap Hooks — auto-detect stack, generate hooks (one-time)
Phase 1    Discovery — fast-path escape for small changes
Phase 2    Exploration — 2-3 parallel code-explorer subagents
Phase 3    Clarification + Requirements — resolve ambiguities, synthesize structured requirements (hard gate)
Phase 4    Architecture — 2 parallel code-architect proposals → user picks
Phase 5    Implementation — TDD per step, parallel dispatch for independent work
Phase 6    Quality + Ship — parallel reviewers → verify → /ship
```

## Hook Bootstrap (Phase 0.5)

On first run in a project (no `.claude/hooks.json` exists), the workflow auto-generates Claude Code hooks tailored to the project's stack.

### How It Works

```
Project root
    │
    ▼
┌─────────────────────────┐
│  Detect stack signals    │  requirements.txt → python
│  (files, dirs, configs)  │  package.json    → node
│                          │  alembic/        → alembic
│  Build tag set:          │  .env            → has-env
│  {python, ruff, orm...}  │  **/services/    → service-layer
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Generate hooks.json     │
│                          │
│  Tier 1 (always):        │
│  - Session start context │
│  - Pre-compaction save   │
│  - Post-commit memory    │
│  - Worktree cleanup      │
│  - Worktree remove guard │
│                          │
│  Tier 2 (conditional):   │
│  - .env protection       │  ← has-env
│  - Linter on save        │  ← ruff / flake8 / eslint
│  - db.commit() guard     │  ← service-layer + orm
│  - UI skill reminder     │  ← server-templates / static-assets
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Copy scripts + config   │
│                          │
│  scripts/hooks/          │
│  ├── cleanup-worktrees.sh│
│  ├── session-start-      │
│  │   context.sh          │
│  ├── pre-compaction-     │
│  │   save.sh             │
│  ├── post-commit-        │
│  │   memory-update.sh    │
│  ├── guard-worktree-     │
│  │   remove.sh           │
│  └── hook-config.sh      │  ← generated sidecar
│      (project-specific   │     with stack tags,
│       linter cmd, file   │     file categories,
│       categories)        │     skill suggestions
└─────────────────────────┘
```

### Portability

The hook system is designed to work on any machine:

- **Templates** live in this repo (`references/hook-templates.md`) — the source of truth for what hooks exist and when they apply.
- **Scripts** live in this repo (`../../scripts/hooks/`) — copied into each project during bootstrap.
- **Generated artifacts** (`.claude/hooks.json`, `scripts/hooks/hook-config.sh`) are project-specific and committed to the target project.

On a new machine: clone this repo to `~/claude-config/`, install the claude-flow skill, and the next time you run it on any project it will auto-bootstrap hooks.

### Stack Detection Reference

| Signal File/Dir | Tag |
|-----------------|-----|
| `requirements.txt` / `pyproject.toml` | `python` |
| `package.json` | `node` |
| `Cargo.toml` | `rust` |
| `go.mod` | `go` |
| `alembic/` / `alembic.ini` | `alembic` |
| `**/models/*.py` / `**/models.py` | `orm` |
| `**/services/` | `service-layer` |
| `**/templates/` | `server-templates` |
| `static/css/` / `public/` / `src/styles/` | `static-assets` |
| `.env` | `has-env` |
| `Dockerfile` / `docker-compose.yml` | `docker` |
| `[tool.ruff]` in pyproject.toml | `ruff` |
| eslint in deps or `.eslintrc*` | `eslint` |
| flake8 in config | `flake8` |
| pytest in config or `conftest.py` | `pytest` |
| jest in deps or `jest.config.*` | `jest` |
| `tsconfig.json` | `typescript` |

### File Layout

```
skills/claude-flow/
├── SKILL.md                          # Main workflow definition
├── README.md                         # This file
└── references/
    └── hook-templates.md             # Template library for hook generation

scripts/hooks/
├── cleanup-worktrees.sh              # Prune orphaned worktrees on session start
├── session-start-context.sh          # Load context + skill suggestions
├── pre-compaction-save.sh            # Save state before context compaction
├── post-commit-memory-update.sh      # Update memory files after commits
└── guard-worktree-remove.sh          # Safety check before worktree removal
```
