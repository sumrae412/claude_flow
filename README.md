# Claude Flow — Code Creation Workflow

Standalone, self-contained agentic workflow for building features with Claude Code. Uses parallel subagents for exploration, competing architecture proposals, TDD implementation, and multi-tier quality review.

## Why use this instead of vanilla Claude Code?

Claude Code's default mode is a single-pass loop: read a few files, form a mental model, write code, commit. This workflow replaces that with a structured multi-agent pipeline. Exploration dispatches 2-3 parallel subagents (Opus) to map codebase patterns and architecture before the main session touches code, then the main session reads the top 5-10 source files itself so it has firsthand knowledge of the code, not just agent summaries. A bundled repo outline script extracts function and class signatures without their bodies, so Claude sees the full codebase structure without burning context tokens on implementation details. A hard gate forces all ambiguities (edge cases, error handling, scope boundaries) to be resolved with you before architecture begins, so Claude doesn't build the wrong thing based on assumptions. Two competing architect agents (simplicity vs. separation) produce proposals you choose between rather than getting a single take-it-or-leave-it design. Implementation enforces strict TDD ordering (test-first per plan step) with defensive skill injection: guard clauses, no-silent-swallow rules, and state management loaded automatically based on whether the step touches UI or backend. Before shipping, a 4-tier parallel review runs 5+ agents (code review, silent failure hunting, security, test coverage analysis) plus conditional specialists (migration, async, API audit) that fire only when relevant file types appear in the diff. This catches entire categories of bugs that vanilla Claude misses: swallowed exceptions, missing error states, auth gaps, untested edge cases, and type mismatches. Hook scripts handle context persistence: pre-compaction transcript backup, post-commit memory updates, and session-start context reloading so the next session doesn't start from scratch.

## Install

```bash
git clone https://github.com/sumrae412/claude_flow.git
cd claude_flow
./install.sh
```

This copies all skills to `~/.claude/skills/` and scripts to `~/.claude/scripts/`.

## What's included

### Core workflow

**code-creation-workflow** — The main orchestrator. 6 phases:

| Phase | What happens |
|-------|-------------|
| 0 Context | Load project identity, classify task, load relevant skills |
| 0.5 Hooks | Auto-detect stack, generate Claude Code hooks (one-time) |
| 1 Discovery | Triage: fast-path, plan-path, or full workflow |
| 2 Exploration | 2-3 parallel code-explorer subagents map the codebase |
| 3 Clarification | Resolve all ambiguities before architecture (hard gate) |
| 4 Architecture | 2 parallel architect proposals, user picks |
| 5 Implementation | TDD per step, parallel dispatch for independent work |
| 6 Quality | 4-tier parallel review, static analysis, verification |

### Bundled skills (13 total)

**Enforcement:**
- `coding-best-practices` — Python, JS, API, testing, performance standards
- `defensive-ui-flows` — Guard clauses, state flags, overlay feedback for UI
- `defensive-backend-flows` — Error handling, data migrations, service-layer patterns

**Workflow:**
- `writing-plans` — Structured implementation plans
- `executing-plans` — Plan execution with review checkpoints
- `test-driven-development` — TDD discipline with anti-patterns reference
- `subagent-driven-development` — Parallel agent dispatch for independent tasks
- `verification-before-completion` — Pre-commit verification gate

**Utilities:**
- `fetch-api-docs` — Fetch API docs before coding against external services
- `finishing-a-development-branch` — Branch completion (merge/PR/cleanup)
- `session-learnings` — Capture discoveries after committing work
- `shipping-workflow` — End-to-end shipping pipeline (commit, PR, review, merge)

### Scripts

- `generate_repo_outline.py` — Extract function/class signatures without bodies (token-efficient codebase context)
- `plancraft_review.py` — Multi-model AI plan review (DeepSeek + Codex)
- `hooks/session-start-context.sh` — Load context + skill suggestions on session start
- `hooks/pre-compaction-save.sh` — Save transcript before context compaction
- `hooks/post-commit-memory-update.sh` — Update memory files after commits

## Usage

After installing, invoke in Claude Code:

```
/code-creation-workflow
```

Or describe what you want to build — the workflow triggers automatically for complex features.

## Updating

Pull the latest and re-run the installer:

```bash
cd claude_flow
git pull
./install.sh
```

## Uninstall

Remove the installed skills:

```bash
# Remove all bundled skills
for skill in code-creation-workflow coding-best-practices defensive-ui-flows \
  defensive-backend-flows fetch-api-docs finishing-a-development-branch \
  session-learnings shipping-workflow writing-plans executing-plans \
  test-driven-development subagent-driven-development verification-before-completion; do
  rm -rf ~/.claude/skills/$skill
done

# Remove scripts
rm -f ~/.claude/scripts/generate_repo_outline.py
rm -f ~/.claude/scripts/plancraft_review.py
rm -f ~/.claude/scripts/hooks/session-start-context.sh
rm -f ~/.claude/scripts/hooks/pre-compaction-save.sh
rm -f ~/.claude/scripts/hooks/post-commit-memory-update.sh
```

## License

MIT
