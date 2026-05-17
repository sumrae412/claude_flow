# Platform Layer Implementation Plan

**Companion:** [Platform Layer: Hooks + Skills + MCP + Agent SDK (design)](2026-04-05-platform-layer-design.md)

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add hook expansion (3 tiers, ~20 hooks), 4 new skills, a FastMCP server for workflow observability, and an Agent SDK PR reviewer for headless Phase 6.

**Architecture:** File-based state (no database). Hooks are shell scripts registered via hook-registry.json. MCP server reads existing files (handoff.md, plans/, MEMORY.md). Agent SDK app is a standalone TypeScript project triggered by GitHub Actions.

**Tech Stack:** Bash (hooks), Markdown (skills), Python/FastMCP (MCP server), TypeScript/Claude Agent SDK (PR reviewer)

---

## Component 1: Hook Expansion

### Task 1: Create hook-registry.json

**Files:**
- Create: `hooks/hook-registry.json`

**Step 1: Create the hooks directory**

```bash
mkdir -p hooks/tier1 hooks/tier2
```

**Step 2: Write hook-registry.json**

Create `hooks/hook-registry.json` with all hook definitions. Each entry specifies id, tier, trigger type, matcher pattern, script path, description, and required stack tags (null for universal).

```json
{
  "version": "1.0",
  "hooks": [
    {
      "id": "secret-detection",
      "tier": 1,
      "trigger": "PreToolUse",
      "matcher": ["Edit", "Write"],
      "script": "tier1/secret-detection.sh",
      "description": "Block edits that introduce API keys, tokens, or passwords"
    },
    {
      "id": "large-file-warning",
      "tier": 1,
      "trigger": "PreToolUse",
      "matcher": ["Edit"],
      "script": "tier1/large-file-warning.sh",
      "description": "Warn when editing files >500 lines"
    },
    {
      "id": "missing-test-companion",
      "tier": 1,
      "trigger": "PostToolUse",
      "matcher": ["Write"],
      "script": "tier1/missing-test-companion.sh",
      "description": "Suggest creating test file when writing new source files"
    },
    {
      "id": "dangerous-git-ops",
      "tier": 1,
      "trigger": "PreToolUse",
      "matcher": ["Bash(git push --force*)", "Bash(git reset --hard*)", "Bash(git checkout .*)"],
      "script": "tier1/dangerous-git-ops.sh",
      "description": "Block force push, hard reset, and checkout-discard"
    },
    {
      "id": "uncommitted-work-guard",
      "tier": 1,
      "trigger": "PreToolUse",
      "matcher": ["Bash(git checkout*)"],
      "script": "tier1/uncommitted-work-guard.sh",
      "description": "Warn on branch switch with uncommitted changes"
    },
    {
      "id": "build-before-commit",
      "tier": 1,
      "trigger": "PreToolUse",
      "matcher": ["Bash(git commit*)"],
      "script": "tier1/build-before-commit.sh",
      "description": "Run lint/typecheck before allowing commit"
    },
    {
      "id": "todo-cleanup",
      "tier": 1,
      "trigger": "PostToolUse",
      "matcher": ["Bash(git commit*)"],
      "script": "tier1/todo-cleanup.sh",
      "description": "Surface leftover TODO/FIXME/HACK after commit"
    },
    {
      "id": "session-context-loader",
      "tier": 1,
      "trigger": "SessionStart",
      "matcher": null,
      "script": "tier1/session-context-loader.sh",
      "description": "Load CLAUDE.md, handoff.md, and suggest skills on session start"
    },
    {
      "id": "pre-compaction-backup",
      "tier": 1,
      "trigger": "PreCompact",
      "matcher": null,
      "script": "tier1/pre-compaction-backup.sh",
      "description": "Save transcript summary before context compression"
    },
    {
      "id": "worktree-cleanup",
      "tier": 1,
      "trigger": "SessionStart",
      "matcher": null,
      "script": "tier1/worktree-cleanup.sh",
      "description": "Remove stale worktrees from previous sessions"
    },
    {
      "id": "lint-on-save-python",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Edit(*.py)"],
      "script": "tier2/lint-on-save-python.sh",
      "description": "Run ruff or flake8 after editing Python files",
      "stack_tags": ["ruff", "flake8"]
    },
    {
      "id": "lint-on-save-js",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Edit(*.js)", "Edit(*.ts)", "Edit(*.jsx)", "Edit(*.tsx)"],
      "script": "tier2/lint-on-save-js.sh",
      "description": "Run eslint after editing JS/TS files",
      "stack_tags": ["eslint"]
    },
    {
      "id": "test-on-save-python",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Edit(app/**/*.py)", "Edit(src/**/*.py)"],
      "script": "tier2/test-on-save-python.sh",
      "description": "Run matching pytest test after editing Python source",
      "stack_tags": ["pytest"]
    },
    {
      "id": "test-on-save-js",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Edit(src/**/*.js)", "Edit(src/**/*.ts)", "Edit(src/**/*.tsx)"],
      "script": "tier2/test-on-save-js.sh",
      "description": "Run matching jest test after editing JS/TS source",
      "stack_tags": ["jest"]
    },
    {
      "id": "migration-sequence-check",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Write(alembic/versions/*.py)", "Write(**/migrations/*.py)"],
      "script": "tier2/migration-sequence-check.sh",
      "description": "Verify migration is based on current head revision",
      "stack_tags": ["alembic"]
    },
    {
      "id": "type-check-on-save",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Edit(*.ts)", "Edit(*.tsx)"],
      "script": "tier2/type-check-on-save.sh",
      "description": "Run tsc --noEmit after editing TypeScript files",
      "stack_tags": ["typescript"]
    },
    {
      "id": "docker-rebuild-reminder",
      "tier": 2,
      "trigger": "PostToolUse",
      "matcher": ["Edit(Dockerfile*)", "Edit(docker-compose*)"],
      "script": "tier2/docker-rebuild-reminder.sh",
      "description": "Remind to rebuild after Dockerfile or compose changes",
      "stack_tags": ["docker"]
    }
  ]
}
```

**Step 3: Commit**

```bash
git add hooks/hook-registry.json
git commit -m "feat: add hook registry with tier 1 and tier 2 definitions"
```

---

### Task 2: Write Tier 1 hook scripts

**Files:**
- Create: `hooks/tier1/secret-detection.sh`
- Create: `hooks/tier1/large-file-warning.sh`
- Create: `hooks/tier1/missing-test-companion.sh`
- Create: `hooks/tier1/dangerous-git-ops.sh`
- Create: `hooks/tier1/uncommitted-work-guard.sh`
- Create: `hooks/tier1/build-before-commit.sh`
- Create: `hooks/tier1/todo-cleanup.sh`
- Create: `hooks/tier1/session-context-loader.sh`
- Create: `hooks/tier1/pre-compaction-backup.sh`
- Create: `hooks/tier1/worktree-cleanup.sh`

**Step 1: Write secret-detection.sh**

Scans the file being edited for common secret patterns: API keys (sk_live, AKIA, ghp_, etc.), tokens, passwords in plaintext. Exits with code 1 (blocks) if found. Must handle `.env.example` as allowlisted.

```bash
#!/usr/bin/env bash
# PreToolUse:Edit,Write — block edits introducing secrets
set -e
FILE="${CLAUDE_FILE_PATH:-}"
[ -z "$FILE" ] && exit 0
[ ! -f "$FILE" ] && exit 0

# Allowlist: example files, test fixtures, docs
case "$FILE" in
  *.example|*.md|*.txt|*test*|*fixture*|*mock*) exit 0 ;;
esac

# Pattern: common secret prefixes and password assignments
if grep -qEn '(sk_live_|sk_test_|AKIA[0-9A-Z]{16}|ghp_[a-zA-Z0-9]{36}|password\s*=\s*["\x27][^"\x27]{8,}|Bearer [a-zA-Z0-9._\-]{20,})' "$FILE" 2>/dev/null; then
  echo "🚫 BLOCKED: Possible secret detected in $FILE"
  echo "Review the file and use .env for secrets instead."
  exit 1
fi
```

**Step 2: Write each remaining tier 1 script**

Each script follows the same pattern: read `$CLAUDE_FILE_PATH` or `$CLAUDE_COMMAND` from environment, perform the check, output warning or exit 1 to block.

Key behaviors:
- `large-file-warning.sh`: `wc -l` on `$CLAUDE_FILE_PATH`, warn (don't block) if >500 lines
- `missing-test-companion.sh`: Given new file path, check if corresponding test file exists. Map `src/foo.py` → `tests/test_foo.py`, `app/services/bar.py` → `tests/test_bar.py`. Warn (don't block) if missing.
- `dangerous-git-ops.sh`: Parse `$CLAUDE_COMMAND`, block if contains `push --force`, `push -f`, `reset --hard`, `checkout .`, `checkout -- .`. Exit 1.
- `uncommitted-work-guard.sh`: Run `git status --porcelain`. If non-empty and command is `git checkout <branch>`, warn.
- `build-before-commit.sh`: Detect project lint command (ruff/eslint/flake8 from pyproject.toml or package.json). Run it. If exit code non-zero, block commit.
- `todo-cleanup.sh`: Run `git diff HEAD~1 --diff-filter=ACM -U0` and grep for `TODO|FIXME|HACK`. Output list if found.
- `session-context-loader.sh`: Upgrade existing `scripts/hooks/session-start-context.sh` — add handoff.md detection, make project-agnostic (use `$CLAUDE_PROJECT_DIR` instead of hardcoded path).
- `pre-compaction-backup.sh`: Upgrade existing `scripts/hooks/pre-compaction-save.sh` — make project-agnostic.
- `worktree-cleanup.sh`: List worktrees via `git worktree list`, remove any with `[prunable]` status.

**Step 3: Make all scripts executable**

```bash
chmod +x hooks/tier1/*.sh
```

**Step 4: Test each script manually**

Run each script in a test project to verify it produces correct output and exits with the right code.

**Step 5: Commit**

```bash
git add hooks/tier1/
git commit -m "feat: add tier 1 universal hook scripts"
```

---

### Task 3: Write Tier 2 hook scripts

**Files:**
- Create: `hooks/tier2/lint-on-save-python.sh`
- Create: `hooks/tier2/lint-on-save-js.sh`
- Create: `hooks/tier2/test-on-save-python.sh`
- Create: `hooks/tier2/test-on-save-js.sh`
- Create: `hooks/tier2/migration-sequence-check.sh`
- Create: `hooks/tier2/type-check-on-save.sh`
- Create: `hooks/tier2/docker-rebuild-reminder.sh`

**Step 1: Write each script**

Key behaviors:
- `lint-on-save-python.sh`: Detect linter (ruff preferred, fallback flake8). Run `ruff check --fix $CLAUDE_FILE_PATH` or `flake8 $CLAUDE_FILE_PATH`. Output results, don't block.
- `lint-on-save-js.sh`: Run `npx eslint --fix $CLAUDE_FILE_PATH`. Output results, don't block.
- `test-on-save-python.sh`: Map source file to test: `basename "$CLAUDE_FILE_PATH" .py` → `pytest tests/ -k "$testname" --tb=short -q`. Output last 5 lines.
- `test-on-save-js.sh`: Map source file to test: `npx jest --findRelatedTests $CLAUDE_FILE_PATH --no-coverage`. Output summary.
- `migration-sequence-check.sh`: Run `alembic heads` and verify only one head. If multiple, warn about branched migrations.
- `type-check-on-save.sh`: Run `npx tsc --noEmit --pretty`. Output errors, don't block.
- `docker-rebuild-reminder.sh`: Echo reminder. No check needed.

**Step 2: Make executable and test**

```bash
chmod +x hooks/tier2/*.sh
```

**Step 3: Commit**

```bash
git add hooks/tier2/
git commit -m "feat: add tier 2 stack-specific hook scripts"
```

---

### Task 4: Update install.sh to install hooks

**Files:**
- Modify: `install.sh`

**Step 1: Add hooks installation section**

After the existing scripts installation, add a new section that:
1. Copies `hooks/` directory to `$CLAUDE_DIR/hooks/claude-flow/`
2. Makes all scripts executable
3. Copies `hook-registry.json` alongside

**Step 2: Add hook generator function**

Add a `--generate-hooks` flag that:
1. Reads `hook-registry.json`
2. Detects stack tags in the current project (reuse Phase 0.5 detection logic from `references/hook-templates.md`)
3. Generates a `hooks.json` with all tier 1 hooks + matching tier 2 hooks
4. Outputs the generated hooks list

This is optional (not run by default install) — invoked separately per project.

**Step 3: Test the install**

```bash
./install.sh
```

Verify hooks directory is installed correctly.

**Step 4: Commit**

```bash
git add install.sh
git commit -m "feat: install hook scripts and add --generate-hooks flag"
```

---

### Task 5: Update hook-templates.md reference

**Files:**
- Modify: `skills/code-creation-workflow/references/hook-templates.md`

**Step 1: Update to reference hook-registry.json**

Phase 0.5 currently has inline hook templates. Update the reference to point at the hook-registry.json as the source of truth, and document that Phase 0.5 now reads the registry instead of hardcoding templates.

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/references/hook-templates.md
git commit -m "refactor: hook-templates now references hook-registry.json"
```

---

## Component 2: New Skills

### Task 6: Create session-handoff skill

**Files:**
- Create: `skills/session-handoff/SKILL.md`

**Step 1: Write the skill**

```markdown
---
name: session-handoff
description: Export current session state for seamless resume in next session. Use at end of sessions, before closing, or when context gets heavy. Writes handoff.md with phase, modified files, blockers, and next steps.
user-invocable: true
---

# Session Handoff

Write a lightweight "where I left off" summary to `$PROJECT/.claude/handoff.md`.

## When to invoke

- End of session (Stop hook triggers automatically)
- Before closing when mid-feature
- User says "save state", "hand off", "I'll continue later"

## What to capture

1. **Current position** — Which phase/step of code-creation-workflow (if active), or general task description
2. **Files modified** — List with one-line summary of each change (from `git diff --name-only` + `git diff --stat`)
3. **Open questions** — Anything unresolved from Phase 3 clarification or discovered during implementation
4. **Blockers** — Failing tests, missing dependencies, API issues
5. **Next 3 steps** — From the plan (if one exists) or inferred from context

## Output format

Write to `$PROJECT/.claude/handoff.md`:

    # Session Handoff
    **Date:** YYYY-MM-DD HH:MM
    **Branch:** feature/xyz
    **Phase:** 5 (Implementation), Step 7 of 12

    ## Modified files
    - `app/services/billing.py` — Added invoice generation service
    - `tests/test_billing.py` — Tests for invoice generation

    ## Open questions
    - None / list any

    ## Blockers
    - None / list any

    ## Next steps
    1. Implement webhook handler for payment confirmation
    2. Write tests for webhook validation
    3. Add error handling for failed payments

## Resume behavior

The `session-context-loader` hook (tier 1) detects handoff.md on next SessionStart and outputs:
"Resuming from [phase/step] on branch [name] — [N] files modified, [N] blockers."
```

**Step 2: Commit**

```bash
git add skills/session-handoff/
git commit -m "feat: add session-handoff skill for cross-session continuity"
```

---

### Task 7: Create smart-exploration skill

**Files:**
- Create: `skills/smart-exploration/SKILL.md`
- Create: `skills/smart-exploration/prompt-library.md`

**Step 1: Write the SKILL.md**

Skill that Phase 2 consults before dispatching explorer subagents. Classifies the task into a category and returns tuned exploration prompts.

Task categories: `endpoint`, `ui`, `data`, `integration`, `refactor`, `bugfix`, `config`

**Step 2: Write prompt-library.md**

Reference file with 2-3 explorer prompts per category. Each prompt is a complete subagent dispatch instruction with thinking budget keyword.

Example for `endpoint`:
```
think harder about... Trace the route → service → model chain for the nearest similar endpoint to [FEATURE]. Find:
1. How the route is registered and what middleware it passes through
2. The service method signature and error handling pattern
3. The model/query pattern used for data access
4. How the response is serialized
5. What tests exist for this endpoint

Return: key files (with line ranges), patterns to follow, and constraints discovered.
```

**Step 3: Commit**

```bash
git add skills/smart-exploration/
git commit -m "feat: add smart-exploration skill with task-typed prompt library"
```

---

### Task 8: Create hook-doctor skill

**Files:**
- Create: `skills/hook-doctor/SKILL.md`

**Step 1: Write the skill**

Diagnostic skill that:
1. Reads hooks from `~/.claude/settings.json` (global) and `$PROJECT/.claude/hooks.json` (project)
2. For each hook script: check exists, is executable, dry-run with mock env vars
3. Reports status per hook: ✅ working, ⚠️ warning, ❌ broken
4. Suggests fixes for broken hooks

Output is a table of all hooks with status.

**Step 2: Commit**

```bash
git add skills/hook-doctor/
git commit -m "feat: add hook-doctor diagnostic skill"
```

---

### Task 9: Create memory-injection skill

**Files:**
- Create: `skills/memory-injection/SKILL.md`

**Step 1: Write the skill**

This is largely a formalization of the existing `references/memory-injection.md` into a standalone skill that the workflow orchestrator explicitly invokes. The skill:
1. Reads MEMORY.md from project root or `.claude/memory/`
2. Accepts a list of file paths that will be touched (from Phase 2 results)
3. Matches against the domain → gotcha mapping
4. Returns a formatted `PROJECT GOTCHAS` block for injection into subagent prompts
5. Graceful no-op if MEMORY.md doesn't exist

**Step 2: Update code-creation-workflow SKILL.md**

Add explicit invocation of `/memory-injection` in Phase 2 (after exploration returns) and Phase 4/5/6 (before each subagent dispatch batch). Reference the skill by name rather than inlining the logic.

**Step 3: Commit**

```bash
git add skills/memory-injection/ skills/code-creation-workflow/SKILL.md
git commit -m "feat: add memory-injection skill, wire into workflow phases"
```

---

## Component 3: MCP Server

### Task 10: Scaffold FastMCP server

**Files:**
- Create: `mcp/claude-flow-server/server.py`
- Create: `mcp/claude-flow-server/requirements.txt`
- Create: `mcp/claude-flow-server/README.md`

**Step 1: Create directory**

```bash
mkdir -p mcp/claude-flow-server
```

**Step 2: Write requirements.txt**

```
fastmcp>=0.1.0
```

**Step 3: Write server.py scaffold**

FastMCP server with resource and tool registrations. Start with the basic structure:

```python
#!/usr/bin/env python3
"""Claude Flow MCP Server — workflow state and memory access."""

import json
import os
from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP("claude-flow")


def find_project_dir() -> Path | None:
    """Find the project directory from CLAUDE_PROJECT_DIR env or cwd."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if project_dir:
        return Path(project_dir)
    cwd = Path.cwd()
    # Walk up to find .git
    for parent in [cwd, *cwd.parents]:
        if (parent / ".git").exists():
            return parent
    return None


# Resources and tools registered below
```

**Step 4: Commit scaffold**

```bash
git add mcp/claude-flow-server/
git commit -m "feat: scaffold FastMCP server for claude-flow"
```

---

### Task 11: Implement MCP resources

**Files:**
- Modify: `mcp/claude-flow-server/server.py`

**Step 1: Implement handoff resource**

```python
@mcp.resource("claude-flow://handoff")
def get_handoff() -> str:
    """Current session handoff state."""
    project = find_project_dir()
    if not project:
        return "No project directory found."
    handoff = project / ".claude" / "handoff.md"
    if handoff.exists():
        return handoff.read_text()
    return "No handoff file found. Start a session and use /session-handoff."
```

**Step 2: Implement plan status resource**

Read the most recent plan file from `docs/plans/` and return it with any TodoWrite state if available.

**Step 3: Implement memory index resource**

Read MEMORY.md from project `.claude/memory/` or project root.

**Step 4: Implement hook health resource**

Read hook-registry.json, check each script exists and is executable. Return status table.

**Step 5: Implement session history resource**

Read last 5 handoff files (if timestamped) or git log of handoff.md changes.

**Step 6: Commit**

```bash
git add mcp/claude-flow-server/server.py
git commit -m "feat: implement MCP resources (handoff, plan, memory, hooks, sessions)"
```

---

### Task 12: Implement MCP tools

**Files:**
- Modify: `mcp/claude-flow-server/server.py`

**Step 1: Implement get_workflow_state tool**

Combines handoff + plan + TodoWrite state into a single workflow status response.

**Step 2: Implement search_memory tool**

Keyword search across all `.md` files in the project memory directory.

**Step 3: Implement run_hook_doctor tool**

Programmatic version of the hook-doctor skill. Checks all hooks, returns health report JSON.

**Step 4: Implement get_exploration_prompts tool**

Reads the smart-exploration prompt library and returns prompts for a given task type.

**Step 5: Commit**

```bash
git add mcp/claude-flow-server/server.py
git commit -m "feat: implement MCP tools (workflow state, memory search, hook doctor, exploration)"
```

---

### Task 13: Update install.sh for MCP server

**Files:**
- Modify: `install.sh`

**Step 1: Add MCP installation section**

Copy `mcp/claude-flow-server/` to `~/.claude/mcp/claude-flow/`. Install Python dependencies.

**Step 2: Register in settings.json**

Add guidance (or script) to register the MCP server in `~/.claude/settings.json`:
```json
{
  "claude-flow": {
    "command": "python3",
    "args": ["~/.claude/mcp/claude-flow/server.py"]
  }
}
```

Don't auto-modify settings.json — output the config block for the user to add.

**Step 3: Commit**

```bash
git add install.sh
git commit -m "feat: install MCP server and output registration config"
```

---

### Task 14: Test MCP server end-to-end

**Step 1: Start the server locally**

```bash
cd mcp/claude-flow-server
pip install -r requirements.txt
python server.py
```

**Step 2: Verify resources return data**

Test each resource against a real project directory with handoff.md, plans, and MEMORY.md.

**Step 3: Verify tools work**

Test `search_memory`, `get_workflow_state`, `run_hook_doctor`, `get_exploration_prompts`.

**Step 4: Fix any issues found**

**Step 5: Commit any fixes**

```bash
git add mcp/claude-flow-server/
git commit -m "fix: MCP server corrections from end-to-end testing"
```

---

## Component 4: Agent SDK PR Reviewer

### Task 15: Scaffold Agent SDK TypeScript project

**Files:**
- Create: `agent-sdk/pr-reviewer/package.json`
- Create: `agent-sdk/pr-reviewer/tsconfig.json`
- Create: `agent-sdk/pr-reviewer/src/index.ts`
- Create: `agent-sdk/pr-reviewer/src/reviewers.ts`
- Create: `agent-sdk/pr-reviewer/src/triage.ts`
- Create: `agent-sdk/pr-reviewer/src/github.ts`

**Step 1: Create directory**

```bash
mkdir -p agent-sdk/pr-reviewer/src
```

**Step 2: Write package.json**

```json
{
  "name": "claude-flow-pr-reviewer",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js",
    "review": "node dist/index.js"
  },
  "dependencies": {
    "@anthropic-ai/sdk": "^0.39.0",
    "claude-agent-sdk": "^0.1.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0",
    "@types/node": "^22.0.0"
  }
}
```

**Step 3: Write tsconfig.json**

Standard Node.js TypeScript config targeting ES2022, module NodeNext, outDir dist.

**Step 4: Write src/index.ts scaffold**

Entrypoint that:
1. Reads PR number from CLI args or `GITHUB_PR_NUMBER` env
2. Fetches PR diff via `gh pr diff`
3. Calls review pipeline
4. Posts results via github.ts

**Step 5: Commit scaffold**

```bash
git add agent-sdk/pr-reviewer/
git commit -m "feat: scaffold Agent SDK PR reviewer project"
```

---

### Task 16: Implement review agent prompts

**Files:**
- Modify: `agent-sdk/pr-reviewer/src/reviewers.ts`

**Step 1: Port Phase 6 review prompts from SKILL.md**

Extract the reviewer prompts from the code-creation-workflow SKILL.md and convert them to TypeScript template functions. Each function takes a diff string and returns a complete prompt.

Reviewers to implement:
1. `codeReviewPrompt(diff)` — bugs, logic errors, race conditions
2. `silentFailurePrompt(diff)` — swallowed errors, empty catches, hidden failures
3. `securityReviewPrompt(diff)` — auth, injection, data exposure
4. `migrationReviewPrompt(diff)` — Alembic safety (conditional)
5. `asyncReviewPrompt(diff)` — async anti-patterns (conditional)
6. `apiDocReviewPrompt(diff)` — route documentation (conditional)

All prompts include the overshoot technique: "find at least 30 issues."

**Step 2: Add conditional reviewer selection**

Function `selectReviewers(diff)` that inspects file extensions in the diff and returns the list of applicable reviewer functions.

**Step 3: Commit**

```bash
git add agent-sdk/pr-reviewer/src/reviewers.ts
git commit -m "feat: implement review prompts with overshoot technique"
```

---

### Task 17: Implement triage and deduplication

**Files:**
- Modify: `agent-sdk/pr-reviewer/src/triage.ts`

**Step 1: Define severity levels**

```typescript
type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'NITPICK';
```

**Step 2: Implement finding parser**

Parse reviewer output into structured findings: file, line, severity, description, suggestion.

**Step 3: Implement deduplication**

Multiple reviewers may flag the same issue. Deduplicate by file+line proximity (within 3 lines) and similar description (simple string similarity).

**Step 4: Implement severity aggregation**

Group findings by severity for PR comment formatting.

**Step 5: Commit**

```bash
git add agent-sdk/pr-reviewer/src/triage.ts
git commit -m "feat: implement finding triage and deduplication"
```

---

### Task 18: Implement GitHub PR comment posting

**Files:**
- Modify: `agent-sdk/pr-reviewer/src/github.ts`

**Step 1: Implement PR comment formatter**

Format triaged findings into a PR review comment:
- CRITICAL/HIGH at top (request changes)
- MEDIUM as inline comments
- LOW/NITPICK in a collapsed `<details>` block
- Header with reviewer count, finding count, and triage summary

**Step 2: Implement posting via gh CLI**

Use `gh pr review` and `gh pr comment` to post findings. Requires `GITHUB_TOKEN`.

**Step 3: Implement small-PR shortcut**

If diff is <50 lines, use a single combined reviewer instead of the full pipeline. Saves cost.

**Step 4: Commit**

```bash
git add agent-sdk/pr-reviewer/src/github.ts
git commit -m "feat: implement GitHub PR comment posting with severity formatting"
```

---

### Task 19: Wire up the full pipeline in index.ts

**Files:**
- Modify: `agent-sdk/pr-reviewer/src/index.ts`

**Step 1: Implement main function**

1. Parse args (PR number, optional flags: `--dry-run`, `--max-agents`, `--skip-tiers`)
2. Fetch diff via `gh pr diff $PR_NUMBER`
3. Select applicable reviewers via `selectReviewers(diff)`
4. Dispatch each reviewer sequentially via Agent SDK
5. Collect all findings
6. Triage and deduplicate
7. Post to PR (or print in dry-run mode)

**Step 2: Add cost guard**

If reviewer count exceeds `--max-agents` (default 6), truncate to core reviewers only (code + silent failure + security).

**Step 3: Test with `--dry-run` against a real PR**

```bash
cd agent-sdk/pr-reviewer
npm install && npm run build
node dist/index.js --dry-run --pr 1
```

**Step 4: Commit**

```bash
git add agent-sdk/pr-reviewer/src/index.ts
git commit -m "feat: wire up full PR review pipeline with cost guard"
```

---

### Task 20: Create GitHub Actions workflow

**Files:**
- Create: `.github/workflows/claude-flow-review.yml`

**Step 1: Write the workflow**

```yaml
name: Claude Flow PR Review

on:
  pull_request:
    types: [opened, synchronize]

permissions:
  pull-requests: write
  contents: read

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '22'
      - name: Install and build
        working-directory: agent-sdk/pr-reviewer
        run: npm ci && npm run build
      - name: Run PR review
        working-directory: agent-sdk/pr-reviewer
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_PR_NUMBER: ${{ github.event.pull_request.number }}
        run: node dist/index.js
```

**Step 2: Commit**

```bash
git add .github/workflows/claude-flow-review.yml
git commit -m "feat: add GitHub Actions workflow for automated PR review"
```

---

## Component 5: Final Integration

### Task 21: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Add sections for new components**

Document the hook system, new skills, MCP server, and PR reviewer. Include configuration instructions and examples.

**Step 2: Commit**

```bash
git add README.md
git commit -m "docs: update README with hook system, MCP server, and PR reviewer"
```

---

### Task 22: End-to-end integration test

**Step 1: Run full install**

```bash
./install.sh
```

**Step 2: Verify hooks are installed**

Check `~/.claude/hooks/claude-flow/` has all tier 1 and tier 2 scripts.

**Step 3: Verify skills load**

In Claude Code, check that `/session-handoff`, `/smart-exploration`, `/hook-doctor`, `/memory-injection` are discoverable.

**Step 4: Verify MCP server starts**

```bash
python3 ~/.claude/mcp/claude-flow/server.py
```

**Step 5: Verify PR reviewer builds**

```bash
cd agent-sdk/pr-reviewer && npm run build
```

**Step 6: Fix any issues**

**Step 7: Final commit**

```bash
git commit -m "fix: integration test corrections"
```

---

## Task Summary

| # | Component | Task | Est. |
|---|-----------|------|------|
| 1 | Hooks | Create hook-registry.json | 5 min |
| 2 | Hooks | Write tier 1 scripts (10) | 30 min |
| 3 | Hooks | Write tier 2 scripts (7) | 20 min |
| 4 | Hooks | Update install.sh for hooks | 10 min |
| 5 | Hooks | Update hook-templates.md reference | 5 min |
| 6 | Skills | session-handoff skill | 10 min |
| 7 | Skills | smart-exploration skill + prompt library | 15 min |
| 8 | Skills | hook-doctor skill | 10 min |
| 9 | Skills | memory-injection skill + workflow wiring | 15 min |
| 10 | MCP | Scaffold FastMCP server | 10 min |
| 11 | MCP | Implement resources (5) | 20 min |
| 12 | MCP | Implement tools (4) | 15 min |
| 13 | MCP | Update install.sh for MCP | 5 min |
| 14 | MCP | End-to-end MCP test | 10 min |
| 15 | SDK | Scaffold TypeScript project | 10 min |
| 16 | SDK | Review prompts + conditional selection | 15 min |
| 17 | SDK | Triage + deduplication | 15 min |
| 18 | SDK | GitHub PR comment posting | 10 min |
| 19 | SDK | Wire full pipeline | 15 min |
| 20 | SDK | GitHub Actions workflow | 5 min |
| 21 | Integration | Update README | 10 min |
| 22 | Integration | End-to-end integration test | 15 min |
