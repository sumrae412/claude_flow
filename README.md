# Claude Flow — Code Creation Workflow

Standalone, self-contained agentic workflow for building features with Claude Code. Uses parallel subagents for exploration, competing architecture proposals, TDD implementation, and multi-tier quality review.

## Why use this instead of vanilla Claude Code?

Claude Code out of the box is powerful, but it wings it. It reads some files, makes a plan in its head, and starts coding. That works for small tasks. For anything complex, you hit the same failure modes over and over:

**Claude skips understanding before building.** Without structured exploration, Claude reads 2-3 files and starts writing code based on assumptions. This workflow launches 2-3 parallel explorer agents that map the actual codebase — patterns, data flow, architecture layers — before a single line is written. The main session then reads the key files firsthand (context hydration) so it has real knowledge, not summaries.

**There's no checkpoint before ambiguity bites you.** Vanilla Claude will happily build the wrong thing because it never stopped to ask about edge cases, error handling, or scope boundaries. Phase 3 is a hard gate — all ambiguities get surfaced and resolved with you before architecture work begins.

**You get one architecture, take it or leave it.** This workflow runs two competing architect agents in parallel — one optimizing for simplicity, one for clean separation. You see both proposals with trade-offs and pick the best fit (or combine them). Vanilla Claude gives you whatever it thought of first.

**Tests come after the code (or not at all).** Claude tends to write implementation first, then bolt on tests as an afterthought. This workflow enforces TDD — test first, implement to make it pass, verify green — for every step in the plan.

**Review is an afterthought.** Vanilla Claude commits and calls it done. This workflow runs a 4-tier parallel review: two code reviewers (bugs + conventions), a silent failure hunter (swallowed errors, empty catches), a security reviewer, and a test coverage analyzer — all before you ship. Conditional specialists (migration reviewer, async reviewer, API auditor) fire when relevant code is detected.

**No defensive patterns by default.** Claude doesn't think about guard clauses, loading/error/success states, silent error swallowing, or input validation unless you remind it every time. This workflow loads defensive skills automatically — UI flows get guard clauses and state management, backend code gets error handling discipline and no-silent-swallow rules.

**Context evaporates between sessions.** Hook scripts preserve context across compaction events and session boundaries. Post-commit memory updates capture what was learned. Session-start hooks reload relevant context automatically. Vanilla Claude starts fresh every time.

In short: this workflow adds structure where Claude Code is weakest — exploration before coding, clarification before building, competing designs before committing to one, tests before implementation, and review before shipping. The result is code that works on the first PR, not the third.

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
