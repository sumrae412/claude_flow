---
name: hook-doctor
description: Diagnose hook health — find broken, missing, or misconfigured hooks. Checks both global (~/.claude/settings.json) and project (.claude/hooks.json) hooks. Use when hooks seem to not be firing or after modifying hook configuration.
user-invocable: true
---

# Hook Doctor

## When to Invoke

- Hooks are not firing as expected
- After modifying hook configuration
- User says "check hooks", "debug hooks", "hook doctor", or "why isn't my hook running"
- After installing or updating hooks

## The Process

### Step 1: Discover All Configured Hooks

Run these commands to collect hook configuration:

```bash
# Global hooks
cat ~/.claude/settings.json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d.get('hooks', {}), indent=2))" 2>/dev/null || echo "(no global hooks)"

# Project hooks
cat "$PROJECT/.claude/hooks.json" 2>/dev/null || echo "(no project hooks.json)"

# Installed hook registry
cat ~/.claude/hooks/claude-flow/hook-registry.json 2>/dev/null || echo "(no hook registry)"
```

List all hooks found, noting their source: **global** (`~/.claude/settings.json`), **project** (`.claude/hooks.json`), or **registry** (`~/.claude/hooks/claude-flow/hook-registry.json`).

### Step 2: Check Each Hook Script

For each hook that references a command or script path, run:

```bash
# Check file exists
SCRIPT_PATH="/path/to/hook.sh"
[ -f "$SCRIPT_PATH" ] && echo "EXISTS" || echo "MISSING"

# Check executable permission
[ -x "$SCRIPT_PATH" ] && echo "EXECUTABLE" || echo "NOT EXECUTABLE"

# Check shebang line
head -1 "$SCRIPT_PATH" 2>/dev/null

# Dry-run with mock env vars (timeout 5 seconds)
timeout 5 env \
  CLAUDE_FILE_PATH=/tmp/test.py \
  CLAUDE_PROJECT_DIR=$(pwd) \
  CLAUDE_COMMAND="echo test" \
  "$SCRIPT_PATH" </dev/null
echo "Exit code: $?"
```

Classify each hook as:
- **working** — file exists, is executable, has valid shebang, exits 0
- **broken** — file missing, not executable, or invalid shebang
- **warning** — runs but exits non-zero

### Step 3: Report

Output a table in this format:

```
Hook Health Report
==================

Global hooks (~/.claude/settings.json):
  ✅ PostToolUse:Bash — post-commit-learnings.sh (working)

Project hooks (.claude/hooks.json):
  ✅ PreToolUse:Edit — external API detection (working)
  ✅ PreToolUse:Edit(.env*) — .env blocker (working)
  ❌ PreToolUse:Edit(*lock.json) — lock file blocker (script not found: /path/to/missing.sh)
  ⚠️ PostToolUse:Edit(*.js) — ESLint auto-fix (runs but exits non-zero — eslint may not be installed)

Registry hooks (installed but not configured):
  ℹ️ secret-detection — not in any hooks.json (run install.sh --generate-hooks)
  ℹ️ large-file-warning — not in any hooks.json

Summary: 3 working, 1 broken, 1 warning, 2 not configured
```

Use ✅ working, ❌ broken, ⚠️ warning, ℹ️ not configured.

### Step 4: Suggest Fixes

For each broken or warning hook, provide a specific fix:

| Condition | Suggestion |
|-----------|-----------|
| Script not found | "Script not found at [path]. Check the path or reinstall with `./install.sh`" |
| Not executable | "Run: `chmod +x [path]`" |
| Exits non-zero | "Script exits with error. Run manually to debug: `[command]`" |
| Not configured | "Run `./install.sh --generate-hooks` to generate project hooks" |
| No shebang | "Add a shebang line to [path], e.g. `#!/bin/bash`" |

If all hooks are healthy, confirm: "All configured hooks are working correctly."

---

## Next Steps

- **Regenerate hooks for this project?** Run `./install.sh --generate-hooks` to re-detect your stack and rebuild hook config.
- **Stale hook paths?** Run `/lint-memory` to check if memory files reference hooks that have moved or been renamed.
- **Need new hooks?** Add entries to `hooks/hook-registry.json` (tier 1 = always-on, tier 2 = stack-conditional), then re-run `--generate-hooks`.
