# Plugin Conversion + Next-Step Hints Design

**Date:** 2026-04-11
**Status:** Approved

## Problem

claude-flow is installed via `install.sh` which copies files to `~/.claude/`. This works but:
1. Not discoverable via Claude Code's plugin system
2. Standalone skills end abruptly without guiding users to logical next steps

## Changes

### 1. Add `.claude-plugin/plugin.json`

Create a plugin manifest so Claude Code can install claude-flow natively from its git repo. Skills in `skills/` are auto-discovered by the plugin loader.

```json
{
  "name": "claude-flow",
  "description": "Multi-agent code creation workflow — 6-phase pipeline with parallel subagents for exploration, architecture, implementation, and review",
  "category": "development",
  "author": { "name": "Summer Rae" },
  "source": { "source": "url", "url": "https://github.com/summerela/claude-flow.git" },
  "homepage": "https://github.com/summerela/claude-flow"
}
```

### 2. Update install.sh messaging

Demote to "advanced setup" for hooks, MCP server, and memory bootstrapping. Skills are auto-loaded by the plugin system.

### 3. Add `## Next Steps` to 6 standalone skills

| Skill | Hints |
|-------|-------|
| hook-doctor | → `install.sh --generate-hooks`, → `/lint-memory` |
| investigator | → `/bug-fix`, → `/code-creation-workflow` |
| lint-memory | → fix stale entries, → `/session-learnings` |
| prompt-optimization | → `/code-creation-workflow` for data, → check variants |
| session-handoff | → resume with handoff.md, → `--abandon` for dead ends |
| production-readiness-check | → fix critical findings, → `/ship` |

## Ruled Out

- **marketplace.json**: Not needed for git-based installation
- **Multi-plugin split**: Fragments integrated pipeline
- **Central workflow-map file**: Indirection harder to maintain than inline hints
