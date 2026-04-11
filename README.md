# Claude Flow — Code Creation Workflow

Standalone, self-contained agentic workflow for building features with Claude Code. Uses parallel subagents for exploration, competing architecture proposals, TDD implementation, and multi-tier quality review.

## Why use this instead of vanilla Claude Code?

Claude Code's default mode is a single-pass loop: read a few files, form a mental model, write code, commit. This workflow replaces that with a structured multi-agent pipeline:

- **Deep exploration before coding.** 2-3 parallel subagents (Opus) map codebase patterns and architecture before the main session touches code. The main session then reads the top 5-10 source files itself so it has firsthand knowledge of the code, not just agent summaries.
- **Token-efficient context.** A bundled repo outline script extracts function and class signatures without their bodies, so Claude sees the full codebase structure without burning context tokens on implementation details.
- **Hard-gated clarification.** All ambiguities (edge cases, error handling, scope boundaries) must be resolved with you before architecture begins, so Claude doesn't build the wrong thing based on assumptions.
- **Competing architectures.** Two architect agents (simplicity vs. separation) produce proposals you choose between rather than getting a single take-it-or-leave-it design.
- **Strict TDD with defensive patterns.** Test-first per plan step, with guard clauses, no-silent-swallow rules, and state management injected automatically based on whether the step touches UI or backend.
- **4-tier parallel review.** 5+ agents (code review, silent failure hunting, security, test coverage analysis) plus conditional specialists (migration, async, API audit) that fire only when relevant file types appear in the diff. This catches entire categories of bugs vanilla Claude misses: swallowed exceptions, missing error states, auth gaps, untested edge cases, and type mismatches.
- **Context persistence across sessions.** Hook scripts handle pre-compaction transcript backup, post-commit memory updates, and session-start context reloading so the next session doesn't start from scratch. Related memories are compiled into consolidated concept articles for efficient retrieval.

## How it works

```mermaid
flowchart LR
    A([User Request]):::start --> B[Context\nLoading]:::phase0
    B --> C{Small\nchange?}:::decision
    C -->|No| E[Explore\n2-3 parallel agents]:::opus
    E --> F[Clarify\nhard gate]:::gate
    F --> G[Architecture\n2 competing proposals]:::opus
    G --> H[Implement\nTDD per step]:::sonnet
    H --> I[Review\n4-tier parallel]:::sonnet
    I --> J([Ship]):::ship
    C -->|Yes| D[Fast Path\nchange + test + commit]:::fast
    D --> J

    classDef start fill:#1a1a2e,stroke:#16213e,color:#e94560,stroke-width:2px
    classDef phase0 fill:#0f3460,stroke:#16213e,color:#e8e8e8
    classDef decision fill:#533483,stroke:#16213e,color:#e8e8e8
    classDef opus fill:#e94560,stroke:#16213e,color:#fff
    classDef gate fill:#f5a623,stroke:#16213e,color:#1a1a2e,stroke-width:2px
    classDef sonnet fill:#0f3460,stroke:#e94560,color:#e8e8e8,stroke-width:2px
    classDef fast fill:#2d4059,stroke:#16213e,color:#e8e8e8
    classDef ship fill:#1a1a2e,stroke:#e94560,color:#e94560,stroke-width:2px
```

## Install

```bash
git clone https://github.com/sumrae412/claude_flow.git
cd claude_flow
./install.sh
```

This copies all skills to `~/.claude/skills/` and scripts to `~/.claude/scripts/`, and installs the 10 universal Tier 1 hooks.

To also generate stack-specific Tier 2 hooks (lint, test, migration check, type-check) based on your project's detected stack:

```bash
./install.sh --generate-hooks
```

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

### Bundled skills (19 total)

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
- `session-learnings` — Capture discoveries after committing work, compile related memories into consolidated concept articles
- `shipping-workflow` — End-to-end shipping pipeline (commit, PR, review, merge)
- `session-handoff` — Export full session state for pickup in a new context window
- `smart-exploration` — Task-typed exploration prompts for Phase 2 (feature/bug/refactor variants)
- `hook-doctor` — Diagnose hook health: missing files, bad exit codes, env issues
- `memory-injection` — Inject project gotchas and compiled knowledge articles into subagent system prompts
- `lint-memory` — 4 health checks for memory files: broken links, orphans, stale entries, contradictions
- `prompt-optimization` — A/B test and promote subagent prompts across explorers, architects, and reviewers

### Self-debugging agents

Autonomous failure detection, diagnosis, and retry for Phases 5-6. When a test, lint check, or review fix fails:

1. The retry loop classifies the error against the **failure catalog** (`memory/failure-catalog.md`)
2. Known patterns are fixed automatically using documented strategies
3. Novel failures dispatch a **diagnosis subagent** that identifies root cause and proposes a fix
4. New patterns are validated via multi-model review (DeepSeek + Codex) before being added to the catalog
5. The catalog is pushed to GitHub so all users benefit from accumulated patterns
6. All events are logged to `memory/failure-events.jsonl` for trend analysis

Fully autonomous — user only sees failures that survive 3 retry attempts.

### Prompt optimization

Closed-loop A/B testing for subagent prompts. The system measures whether the prompts dispatched to subagents actually produce good results, then promotes winners and generates challengers for losers.

**Three agent types tracked:**

| Agent Type | Phase | What's Measured | Score |
|-----------|-------|----------------|-------|
| Explorer | 2 | Were discovered files actually used in implementation? | F1(precision, recall) * (1 - retry_rate) |
| Architect | 4 | Was this proposal chosen? Did it converge quickly? Few review issues? | Weighted: selection + quality + convergence |
| Reviewer | 6 | Were reported issues real and worth fixing? | true_positive_rate * signal_to_noise |

**How it works:**

1. Before dispatching subagents, `prompt-tracker.py select` picks a variant via epsilon-greedy (80% exploit best, 20% explore)
2. After the phase completes, outcomes are recorded to per-type JSONL event files
3. After 10+ sessions per variant, the system compares scores and promotes winners (gap > 0.05)
4. Losing variants get rewritten by an LLM to address their specific blind spots (requires user approval)

**Manual review:** Run `/prompt-optimization` to see current variant performance across all agent types.

**MCP tool:** `get_prompt_performance` returns JSON performance data, filterable by agent type and category.

### Hook system

Three-tier hook architecture for automated enforcement and context management:

| Tier | Count | Description |
|------|-------|-------------|
| 1 — Universal | 10 | Always-on: secret detection, git safety, session lifecycle, pre-compaction backup, post-commit memory update |
| 2 — Stack-specific | 7 | Auto-detected by `install.sh`: lint, test, migration check, type-check (fires only when relevant files change) |
| 3 — Project-specific | — | User-configured per repo, not bundled |

**Generate hooks for your stack:**
```bash
./install.sh --generate-hooks
```

This detects your stack (Node, Python, Rails, etc.) and writes the relevant Tier 2 hooks into `.claude/hooks/`.

**Diagnose hook issues:**
```
/hook-doctor
```

Checks for missing hook files, bad exit codes, unset env vars, and permission errors, and prints a fix for each.

### MCP server

A Model Context Protocol server that exposes workflow state to external tools and IDE integrations.

| Type | Name | Description |
|------|------|-------------|
| Resource | `workflow://state` | Current phase, active agents, last checkpoint |
| Resource | `workflow://memory` | Project memory files (identity, gotchas, decisions) |
| Resource | `workflow://hooks` | Hook registry and last-run status |
| Resource | `workflow://outline` | Latest repo outline (signatures without bodies) |
| Resource | `workflow://session` | Active session context and loaded skills |
| Tool | `query_state` | Query workflow state with a natural-language filter |
| Tool | `search_memory` | Full-text search across all memory files |
| Tool | `check_hook_health` | Run hook-doctor diagnostics and return results |
| Tool | `inject_context` | Push a context block into the next subagent prompt |

**Register in `~/.claude/settings.json`:**
```json
{
  "mcpServers": {
    "claude-flow": {
      "command": "node",
      "args": ["~/.claude/scripts/mcp-server/index.js"]
    }
  }
}
```

### Automated PR review

An Agent SDK app (`scripts/pr-review-agent/`) that runs the Phase 6 quality review headlessly against any PR diff — no interactive Claude session required.

**What it reviews:**
- Tier 1 checks always run: silent failure hunting, security audit, test coverage analysis
- Tier 2 checks fire conditionally: migration safety (if `*.sql` in diff), async patterns (if `async/await` count is high), API contract audit (if route files changed)

**GitHub Actions integration:**

Add to `.github/workflows/pr-review.yml` — the action posts review comments directly on the PR.

```yaml
- uses: sumrae412/claude-flow-pr-review@v1
  with:
    anthropic_api_key: ${{ secrets.ANTHROPIC_API_KEY }}
```

**Cost controls:** PRs under 200 lines skip the full agent pool and use a single-pass review. The agent cap defaults to 5 and is configurable via `MAX_REVIEW_AGENTS`.

### Scripts

**Analysis:**
- `generate_repo_outline.py` — Extract function/class signatures without bodies (token-efficient codebase context)
- `plancraft_review.py` — Multi-model AI plan review (DeepSeek + Codex)
- `prompt-tracker.py` — Prompt variant selection, outcome recording, and performance reporting

**Universal hooks (Tier 1 — always installed):**
- `hooks/session-start-context.sh` — Load context + skill suggestions on session start
- `hooks/pre-compaction-save.sh` — Save transcript before context compaction
- `hooks/post-commit-memory-update.sh` — Update memory files after commits
- `hooks/secret-detection.sh` — Block commits containing secrets or credentials
- `hooks/git-safety.sh` — Prevent force-pushes to main and other destructive ops

**Stack-specific hooks (Tier 2 — generated by `install.sh --generate-hooks`):**
- `hooks/stack/lint.sh` — Run linter on changed files before commit
- `hooks/stack/test.sh` — Run affected tests before commit
- `hooks/stack/migration-check.sh` — Validate migration files when schema changes
- `hooks/stack/type-check.sh` — Run type checker when type files change

**Self-debugging:**
- `scripts/emit-failure-event.sh` — Append structured events to the failure event log
- `hooks/tier1/failure-catalog-push.sh` — Auto-commit and push failure catalog updates to GitHub

**MCP server:**
- `mcp-server/index.js` — MCP server entrypoint (5 resources, 4 tools)

**PR review agent:**
- `pr-review-agent/index.js` — Headless Phase 6 review via Agent SDK

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
  test-driven-development subagent-driven-development verification-before-completion \
  lint-memory; do
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
