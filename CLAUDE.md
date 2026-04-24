# CLAUDE.md — claude_flow

## Project Identity

**claude-flow** is the platform layer for Claude Code — a repository of skills, hooks, an MCP server, and an Agent SDK app that extend Claude Code's native capabilities for development workflows.

It is NOT a standalone LLM framework (like LangChain/CrewAI). It runs INSIDE Claude Code, using its native primitives: Agent tool, skills, hooks, slash commands. Don't propose wrapping it in an external orchestrator.

## Repository Structure

```
claude_flow/
├── hooks/
│   ├── hook-registry.json       # Source of truth for all hook definitions
│   ├── tier1/                   # Universal hooks (install on every project)
│   └── tier2/                   # Stack-specific hooks (install when tags match)
├── mcp/
│   └── claude-flow-server/      # FastMCP server (Python, file-based, no daemon)
│       ├── server.py            # 5 resources + 4 tools
│       └── requirements.txt
├── agent-sdk/
│   └── pr-reviewer/             # TypeScript Agent SDK app for headless PR review
│       ├── src/
│       │   ├── index.ts         # Pipeline entrypoint
│       │   ├── reviewers.ts     # 6 review prompts with overshoot technique
│       │   ├── triage.ts        # Dedup + severity classification
│       │   └── github.ts        # PR comment posting
│       ├── package.json
│       └── tsconfig.json
├── .github/workflows/
│   └── claude-flow-review.yml   # Triggers PR reviewer on pull_request
├── skills/                      # NOTE: skills live in claude-skills repo now (symlink)
├── install.sh                   # Installs skills, hooks, MCP server; --generate-hooks flag
└── docs/plans/                  # Design and implementation plans
```

**Skills note:** The `skills/` directory here is historical. Canonical skills live at `/Users/summerrae/claude_code/claude-skills/` and are symlinked into `~/.claude/skills/`. Edits to skills happen there, not here.

## Key Policies

### Hook registry is single source of truth
`hooks/hook-registry.json` defines all hooks. Never hardcode hooks in `settings.json` or `hooks.json` directly — generate them via `./install.sh --generate-hooks`, which detects stack tags and selects matching tier 1 + tier 2 entries.

### install.sh does NOT auto-modify settings.json
`--generate-hooks` outputs the JSON block for the user to paste into `settings.json`. This is intentional — preserves user control over global config. Don't "fix" this to auto-write.

### Memory injection is a cross-cutting policy
`memory-injection` skill must be invoked before dispatching any subagent that touches project code. This is wired into:
- `claude-flow` Phases 2, 4, 5, 6
- `subagent-driven-development` (pre-first-dispatch)
- `executing-plans` (pre-first-dispatch)

Adding a new skill that dispatches subagents? It MUST call memory-injection first. Bypassing this breaks the cross-session gotcha safety net.

### MCP server is file-based
No database, no daemon. Reads `.claude/handoff.md`, `docs/plans/`, MEMORY.md, `hooks.json` directly. Safe to point any MCP client at it. Exposes `claude-flow://handoff`, `claude-flow://plan`, `claude-flow://memory`, `claude-flow://hooks`, `claude-flow://sessions`.

### Overshoot technique exemptions
"Find at least 30 issues" framing applies to OPEN-ENDED bug hunters (code reviewer, silent failure, security). It does NOT apply to deterministic/structured-checklist reviewers — those have fixed scope and overshoot prompts actively degrade them. See MEMORY `overshoot_prompt_scope`.

### PR reviewer is provider-pluggable
`agent-sdk/pr-reviewer/` selects a model provider via `PR_REVIEWER_PROVIDER`:
- `anthropic` (default) — Claude Sonnet with ephemeral prompt caching (~90% input discount within the 5-min TTL). Uses `ANTHROPIC_API_KEY`; optional `ANTHROPIC_MODEL`, `ANTHROPIC_MAX_TOKENS`.
- `nvidia` — free-tier hosted models at `integrate.api.nvidia.com/v1` (OpenAI-compatible). Requires `NVIDIA_API_KEY` + `NVIDIA_MODEL`. No prompt caching. Optional `NVIDIA_BASE_URL`, `NVIDIA_MAX_TOKENS`, `NVIDIA_TIMEOUT_MS` (default 900000).

NVIDIA gotchas (verified 2026-04-24 against PR #45, 44-line diff):
- **Aggressive overshoot framing is filtered.** "I'm positive there are at least 30 issues — find them all" either silently TCP-closes or hangs past the 5-min gateway timeout. Each overshoot reviewer (`code`, `silentFailure`, `security`) now carries a `systemSoft` variant in `reviewers.ts`; `ModelClient.preferSoftPrompts=true` makes `pickSystem()` swap it in. Confirmed A/B: aggressive → 504 at 5:02; soft → 200 in 9.9s end-to-end.
- **Model IDs are versioned — don't guess.** `deepseek-ai/deepseek-v3` / `moonshotai/kimi-k2` return 404. Query `GET /v1/models` for the real list. Confirmed working: `moonshotai/kimi-k2-instruct-0905`. Confirmed overloaded/timing-out (may recover): `minimaxai/minimax-m2.7`, `deepseek-ai/deepseek-v3.2`, `moonshotai/kimi-k2.5`. Reasoning models (e.g. `nvidia/nemotron-3-nano-30b-a3b`) return output in a `reasoning` field the parser doesn't read — skip unless wiring that up.
- **Extended headersTimeout.** Node's built-in fetch defaults to 300s headersTimeout (undici); `NvidiaModelClient` uses `undici.Agent` with 900s so a slow-but-eventually-successful call doesn't fail client-side before NVIDIA's own 5-min edge timeout decides.

When adding providers, extend `src/model-client.ts` (ModelClient interface + factory) — do NOT inline SDK calls in `index.ts`. CI (`.github/workflows/claude-flow-review.yml`) is pinned to Anthropic; non-Anthropic providers are local/opt-in until validated.

## Multi-Clone Gotcha

The "two-clones" gotcha is not unique to this repo. Any project cloned more than once on the same filesystem can trigger it. Confirmed instances:

- **claude_flow:** canonical `/Users/summerrae/claude_code/claude_flow/` vs shadow `/Users/summerrae/claude_flow/`
- **courierflow:** canonical `/Users/summerrae/courierflow/` plus `/Users/summerrae/courierflow/.claude/worktrees/*/` — a 2026-04-20 parallel-agent PR (#443) shipped byte-identical `docs/routines/*.md` files from a shadow clone BEFORE the author's commit could land.

Always run `git rev-parse --show-toplevel` on the first turn. If cwd is a shadow path, switch to canonical before writing. A shadow clone can appear populated in one turn and nearly empty the next. When your local commit can't cherry-pick onto `origin/main` cleanly — suspect parallel-agent pickup, verify with `git diff origin/main HEAD -- <paths>`, and if empty your work is already upstream. See MEMORY `two_clones_same_repo`, `shadow_path_drift_within_session`, `two_clones_gotcha_generalized`, `git_cherry_pick_empty_signal`, and `reset_hard_after_upstream_verification`.

## Bundled Skills (relevant to claude-flow authorship)

| Skill | Purpose |
|-------|---------|
| `claude-flow` | The main orchestrator workflow skill (Phase 0-6 pipeline) |
| `session-handoff` | Cross-session state export to `.claude/handoff.md` |
| `session-learnings` | Post-commit reflection, auto-commits to MEMORY.md |
| `smart-exploration` | Task-typed Phase 2 exploration prompts |
| `hook-doctor` | Diagnose broken/misconfigured hooks |
| `memory-injection` | Inject MEMORY.md gotchas into subagent prompts |
| `writing-plans` / `subagent-driven-development` / `executing-plans` | Plan authoring and execution |
| `debate-team` | Multi-model review (absorbs plancraft) |
| `cleanup` | Branch cleanup, worktree teardown, post-merge housekeeping |

## Commands

```bash
./install.sh                      # Install skills, hooks, MCP server
./install.sh --generate-hooks     # Generate project-specific hooks (in project cwd)
python3 mcp/claude-flow-server/server.py   # Start MCP server manually

cd agent-sdk/pr-reviewer
npm install && npm run build      # Build PR reviewer
node dist/index.js --dry-run --pr 1   # Dry-run against a PR

cd /Users/summerrae/claude_code/claude-skills  # Edit canonical skills
```

## Documentation

- `docs/plans/2026-04-05-platform-layer-design.md` — Platform layer design (approved)
- `docs/plans/2026-04-05-platform-layer-implementation.md` — 22-task implementation plan (executed)
- `README.md` — User-facing installation and usage guide
- `skills/code-creation-workflow/references/` — Memory injection, hook templates, skill triggers, error recovery
