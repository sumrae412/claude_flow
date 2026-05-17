# Platform Layer: Hooks + Skills + MCP + Agent SDK

**Created:** 2026-04-05 | **Status:** approved

## Summary

Evolve claude-flow from a single workflow skill into a platform with thick guardrails, observable state, and headless automation. Four components: expanded hook coverage, targeted new skills, an MCP server for workflow visibility, and an Agent SDK PR reviewer.

## Audience

Personal-first, shareable later. Architect for reuse but optimize for Summer's workflow and projects.

## Component 1: Hook Expansion

### Problem

Current hook coverage is thin (5 hooks). Most common mistakes go uncaught. The Phase 0.5 hook bootstrap concept exists in the SKILL.md but the actual hook library is sparse.

### Design

Three tiers of hooks, all shell scripts in `hooks/`, with a `hook-registry.json` mapping hooks to tiers, stack tags, and trigger types.

```
hooks/
  tier1/                    # Universal (every project)
  tier2/                    # Stack-specific (installed when tags match)
  hook-registry.json        # Maps hooks → tiers, stack tags, triggers
```

#### Tier 1 — Universal (~10 hooks)

| Hook | Trigger | Behavior |
|------|---------|----------|
| secret-detection | PreToolUse:Edit, PreToolUse:Write | Scan for API keys, tokens, passwords. Block + warn. |
| large-file-warning | PreToolUse:Edit | Warn if editing >500 line file without Read in session |
| missing-test-companion | PostToolUse:Write | When creating `foo.py`, warn if no `test_foo.py` exists |
| dangerous-git-ops | PreToolUse:Bash | Block `git push --force`, `git reset --hard`, `git checkout .` |
| uncommitted-work-guard | PreToolUse:Bash(git checkout*) | Warn on branch switch with uncommitted changes |
| build-before-commit | PreToolUse:Bash(git commit*) | Run lint/typecheck before commit |
| todo-cleanup | PostToolUse:Bash(git commit*) | Scan diff for leftover TODO/FIXME/HACK after commit |
| session-context-loader | SessionStart | Load CLAUDE.md + suggest skills from recent git activity |
| pre-compaction-backup | PreCompact | Save transcript summary before compression |
| worktree-cleanup | SessionStart | Clean stale worktrees |

#### Tier 2 — Stack-Specific (~7 hooks)

| Hook | Stack Tag | Behavior |
|------|-----------|----------|
| lint-on-save | ruff / eslint / flake8 | Run linter on saved file, auto-fix |
| test-on-save | pytest / jest | Run matching test after source edit |
| migration-sequence-check | alembic | Verify migration based on current head |
| import-order | python | Warn if imports unsorted (isort) |
| type-check-on-save | typescript | Run `tsc --noEmit` on saved file |
| docker-rebuild-reminder | docker | Remind to rebuild after Dockerfile/compose edit |
| dependency-audit | node / python | Run `npm audit` or `pip-audit` after dependency changes |

#### Tier 3 — Project-Specific

User-configured in project `.claude/hooks.json`. Phase 0.5 bootstrap detects opportunities and suggests them. Examples: CourierFlow eager loading check, column name conventions, custom forbidden patterns.

#### hook-registry.json Schema

```json
{
  "hooks": [
    {
      "id": "secret-detection",
      "tier": 1,
      "trigger": "PreToolUse",
      "matcher": "Edit",
      "script": "tier1/secret-detection.sh",
      "description": "Block edits that introduce API keys, tokens, or passwords",
      "stack_tags": null
    },
    {
      "id": "lint-on-save",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": "Edit(*.py)",
      "script": "tier2/lint-on-save.sh",
      "description": "Run ruff/flake8 after editing Python files",
      "stack_tags": ["ruff", "flake8"]
    }
  ]
}
```

The install script reads this registry, detects the project's stack tags, and generates the appropriate hooks.json entries.

---

## Component 2: New Skills (4)

### 2a. session-handoff

**Problem:** Sessions end mid-feature and the next session re-discovers context.

**Behavior:** Writes `$PROJECT/.claude/handoff.md` on session end (via Stop hook) or manually via `/session-handoff`:
- Current phase and step
- Files modified with one-line change summaries
- Open questions / unresolved blockers
- Next 3 steps from the plan

The SessionStart hook detects handoff.md and surfaces it: "Resuming from Phase 5, Step 3."

### 2b. smart-exploration

**Problem:** Phase 2 explorer prompts are generic regardless of task type.

**Behavior:** Prompt library indexed by task classification (endpoint, UI, data, integration, refactor). Phase 2 classifies the task first, then selects tuned exploration prompts:
- Endpoint: "Trace route → service → model for nearest similar endpoint"
- UI: "Map component tree, CSS architecture, state management"
- Data: "Trace model relationships, migration history, query patterns"
- Integration: "Find external API call sites, auth patterns, error handling"

### 2c. hook-doctor

**Problem:** Hooks break silently — typos, missing scripts, wrong paths.

**Behavior:** Diagnostic skill invoked via `/hook-doctor`:
1. List all configured hooks (settings.json + project hooks.json)
2. Test each script exists and is executable
3. Dry-run with mock inputs
4. Report: ✅ working, ⚠️ warning, ❌ broken

### 2d. memory-injection

**Problem:** MEMORY.md bootstrap (Phase 0 Step 7) creates the file, but nothing reads it back into subagent prompts.

**Behavior:** Reference consulted when dispatching subagents. Before each Phase 2/4/5/6 dispatch:
1. Read MEMORY.md index
2. Match entries to current task (file paths, keywords, domain)
3. Inject relevant snippets as "Known gotchas" in subagent prompts

---

## Component 3: MCP Server

### Problem

Workflow state is invisible from outside the active session. Can't query phase, plan status, or memory from other sessions, CI, or tools.

### Design

Python FastMCP server exposing workflow state as resources and tools. File-based — reads handoff.md, plans/, MEMORY.md, hooks.json. No database, no daemon.

#### Resources

| Resource | URI | Returns |
|----------|-----|---------|
| Current handoff | `claude-flow://handoff` | Latest handoff.md (phase, step, blockers) |
| Plan status | `claude-flow://plan/{project}` | Plan with step completion status |
| Memory index | `claude-flow://memory/{project}` | MEMORY.md index |
| Hook health | `claude-flow://hooks/{project}` | Hook registry status |
| Session history | `claude-flow://sessions/{project}` | Last 5 session summaries |

#### Tools

| Tool | Behavior |
|------|----------|
| `get_workflow_state` | Current phase, step, plan progress, blockers |
| `search_memory` | Keyword search across project memory files |
| `run_hook_doctor` | Hook diagnostics, return health report |
| `get_exploration_prompts` | Task type → smart-exploration prompt set |

#### Installation

Ships in `mcp/claude-flow-server/`. Install script registers it in settings.json under `mcpServers`:
```json
{
  "claude-flow": {
    "command": "python3",
    "args": ["~/.claude/mcp/claude-flow/server.py"]
  }
}
```

---

## Component 4: Agent SDK PR Reviewer

### Problem

Phase 6 review catches bugs that vanilla Claude misses, but only runs interactively. Want it on every PR via GitHub Actions.

### Design

TypeScript Agent SDK app that runs a subset of Phase 6 headlessly.

#### Flow

```
PR opened/updated
  → GitHub Actions triggers claude-flow-pr-review
  → App reads PR diff via gh API
  → App reads project context via MCP server (workflow state + memory)
  → Dispatches review agents sequentially:
      1. Code reviewer (bugs, logic errors)
      2. Silent failure hunter (swallowed errors, empty catches)
      3. Security reviewer (auth, injection, data exposure)
      4. Conditional: migration/async/API reviewers (by file type in diff)
  → Deduplicates + triages findings
  → Posts as PR review comment:
      CRITICAL/HIGH → request changes
      MEDIUM → comment
      LOW/NITPICK → collapsed summary
```

#### What runs vs. what's skipped

| Phase 6 Tier | Headless | Reason |
|-------------|----------|--------|
| Tier 1 Core | ✅ | All work on diffs |
| Tier 2 Conditional | ✅ | Triggered by file types |
| Tier 3 Domain | ✅ if configured | Project-specific |
| Tier 4 Design review | ❌ | Needs dev server + browser |
| Tier 5 UX polish | ❌ | Needs live UI |
| Random exploration | ❌ | Too expensive per PR |
| De-slopification | ❌ | Better interactive |

#### Overshoot technique

All review prompts carry the same framing: "find at least 30 issues." Pushes past the 20-25 issue plateau.

#### Cost control

- Only Tier 1 + applicable Tier 2 (4-6 agents per PR)
- Sonnet for all agents
- Small PRs (<50 lines): single combined reviewer
- Configurable via claude-flow.yml: max agents, skip tiers, cost cap

#### Project structure

```
agent-sdk/
  pr-reviewer/
    src/
      index.ts          # Entrypoint — read PR, orchestrate agents
      reviewers.ts      # Review prompts (from SKILL.md Phase 6)
      triage.ts         # Dedup + severity classification
      github.ts         # Post as PR comments
    package.json
    tsconfig.json
.github/
  workflows/
    claude-flow-review.yml
```

---

## What doesn't change

- SKILL.md phases 0-6 structure — unchanged (additions only)
- Existing hooks — kept, new hooks added alongside
- Existing skills — kept, new skills added
- Project .claude/hooks.json format — unchanged
- Symlink install pattern — kept

## Implementation order

1. Hook expansion (highest leverage, stated pain point)
2. New skills (session-handoff, smart-exploration, hook-doctor, memory-injection)
3. MCP server (enables observability + feeds into PR reviewer)
4. Agent SDK PR reviewer (depends on MCP server for context)

## Open questions

None — all resolved during design.
