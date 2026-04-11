# Review Standards — Claude Flow

Project-specific review rules. Any reviewer (human, AI agent, hook, or CI tool) should check against these.

## Must Check

- Skills are self-contained: no imports from other skills, no assumptions about calling context. Exception: integration-layer skills (e.g., `fetch-api-docs`) may depend on external CLIs — document the dependency in the skill frontmatter
- Hook scripts exit with correct codes (0 = pass, 1 = block) and never silently succeed on error
- Scripts have `set -e` at minimum (bash) or equivalent error handling (Python)
- No hardcoded paths — use `$HOME/.claude/` or relative paths from script location
- Subagent prompts include explicit scope boundaries (what to check, what to skip, when to stop)
- Review agents never auto-fix; they report findings for human/caller decision
- Shell scripts are executable (`chmod +x`) and have correct shebangs

## Skip

- Generated repo outlines (output of `generate_repo_outline.py`)
- Test fixture files and snapshot data
- Third-party vendored scripts

## Project Patterns

- **Tier 1 hooks** are universal safety nets (secrets, large files, dangerous git ops). They must be fast (<2s) and never block on network calls.
- **Tier 2 hooks** are project-specific quality gates (lint, typecheck, test-on-save). They can be slower but should target only changed files.
- **Skills** follow the SKILL.md frontmatter format with `name`, `description`, and trigger conditions. The skill body is the prompt itself.
- **Scripts** are standalone utilities. They must work when called from any directory and handle missing dependencies gracefully (check for tools before using them).
- **Subagent prompts** should specify model tier (`sonnet` for execution, `opus` for judgment/review) and include a token budget or scope limit.
- Workflow phases are sequential with hard gates — never skip clarification, never start implementation before architecture approval.

## Common AI Mistakes to Watch For

- Adding wrapper abstractions around shell commands that a direct `#!/bin/bash` script handles fine
- Silently swallowing hook exit codes (catching errors and returning 0 instead of propagating failure)
- Making hook scripts chatty — hooks should only output on failure, not on success
- Over-engineering skill prompts with conditional logic that belongs in the calling code, not the prompt text
- Adding Python dependencies to scripts that should be zero-dependency bash
- Creating "utility" modules that only one script uses
- Changing skill trigger conditions without updating the corresponding CLAUDE.md entry
- Writing review prompts that say "check everything" instead of scoping to specific concern categories
- Duplicating logic between tier 1 and tier 2 hooks (e.g., secret detection in both tiers)
- Adding backwards-compatibility shims for hook formats that no longer exist
