# CLAUDE.md — claude_flow

## Project Identity

**claude-flow** is the platform layer for Claude Code — a repository of skills, hooks, an MCP server, and an Agent SDK app that extend Claude Code's native capabilities for development workflows.

It is NOT a standalone LLM framework (like LangChain/CrewAI). It runs INSIDE Claude Code, using its native primitives: Agent tool, skills, hooks, slash commands. Don't propose wrapping it in an external orchestrator.

**Exception — free external libraries are allowed when they clearly fit.** If a specific capability is handled materially better by an existing open-source library (e.g. scipy for statistical tests, Phoenix for eval tracing, RAGAS for pre-built eval metrics) AND the library is free — no paid SaaS, no lock-in — prefer it over a hand-rolled native implementation. The rule above targets *wrapping claude_flow in an orchestrator*, not using peer libraries for specific capabilities. Paid observability platforms (LangSmith, Braintrust, etc.) and frameworks whose main value is orchestration (LangGraph, CrewAI) remain out.

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
- `nvidia` — free-tier hosted models at `integrate.api.nvidia.com/v1` (OpenAI-compatible). Requires `NVIDIA_API_KEY` + either `NVIDIA_MODEL` (single-model mode) or `NVIDIA_MODEL_POOL` (comma-separated list, ensemble fan-out mode). No prompt caching. Optional: `NVIDIA_BASE_URL`, `NVIDIA_MAX_TOKENS`, `NVIDIA_TIMEOUT_MS` (client-side undici headers timeout, default 900000), `NVIDIA_PER_CALL_TIMEOUT_MS` (ensemble per-model abort ceiling, default 240000), `NVIDIA_ENSEMBLE_GRACE_MS` (after first ensemble success, grace window for stragglers before aborting remaining calls, default 30000).

Cross-cutting optional env vars:
- `PR_REVIEWER_FALLBACK_PROVIDER=anthropic` — wraps primary in `FallbackModelClient`; on primary throw, retries transparently via fallback. Pair with `NVIDIA_MODEL_POOL` as "free-first, paid safety net." Known compromise: fallback inherits primary's `preferSoftPrompts`, so Anthropic-as-fallback gets the soft prompt variant rather than the aggressive overshoot one. Acceptable for resilience; use single-provider mode when prompt-variant fidelity matters.
- `DEDUP_SIMILARITY_THRESHOLD` — Dice coefficient threshold for semantic dedup in `triage.ts` (default 0.25). Raise to ~0.4 if over-merging distinct concerns; lower to ~0.15 if paraphrases slip through. Don't go below 0.1.
- `PR_REVIEWER_REVALIDATE=1` — opt-in second-pass FP filter (`src/revalidate.ts`). After dedup, asks the model to re-read each finding against the diff and emit `TRUE_POSITIVE` / `FALSE_POSITIVE` / `UNCERTAIN`; drops false positives, keeps the rest. Inspired by [vercel-labs/deepsec](https://github.com/vercel-labs/deepsec)'s `revalidate` stage (they report ~50% FP-rate reduction on whole-repo scans). Costs **4.6–9.9× the review's input tokens** on the current structure (the diff is re-sent uncached per finding; the cached system prompt is below the 1024-token floor so caching no-ops) — NOT "double." Don't default on. **Verified 2026-05-29** ([`docs/decisions/2026-05-29-revalidate-verdict.md`](docs/decisions/2026-05-29-revalidate-verdict.md), A/B over 5 PRs on Sonnet): drop accuracy was 13/13 correct (killed a false CRITICAL + 4 false HIGH security findings on noisy code; zero real bugs dropped). FP-cut earns its cost on **large / noisy / high-recall** runs but is thin (0–2 low-severity drops) on **small diffs at the worst cost ratio** — keep OFF for small diffs. Caching the diff (≥1024-token `cache_control` block shared across the N calls) would drop cost toward ~1× and is the prerequisite for ever defaulting it on.
- `PR_REVIEWER_MAX_REVALIDATE` — Rule-6 budget cap on the revalidation pass (default 30, `0` disables). Findings are sorted by severity and only the top-N are revalidated; the cheap-to-lose tail is kept (never dropped) and surfaced as `unverified` in the PR comment's partial-coverage banner. Bounds the 4.6–9.9× cost blast radius (see above) when a high-recall ensemble produces a long findings list — verified engaging on the 47- and 67-finding PRs in the A/B (17 / 37 findings left `unverified`).

**Partial-coverage surfacing (Rule 7 + Rule 12).** `runReview` returns `degraded[]` (reviewer or `reviewer@model` labels that errored/timed out), `skipped[]` (reviewers dropped by the `--max-agents` cap), and `plannedReviewerCount` alongside the actual `reviewerCount`. A failed reviewer no longer returns a silent `[]` that lets the comment over-claim "N reviewers" — it lands in `degraded`, and the PR comment renders an honest "N of M reviewers" + a `⚠️ Partial coverage` banner. Ensemble runs (`NVIDIA_MODEL_POOL`) now return per-model `segments[]` so each model's findings are parsed under a `reviewer@model` label; that label flows into `deduplicateFindings`' `mergedFrom`, so cross-model consensus survives the join instead of every finding reading as the same reviewer. Protected invariants live in `src/coverage.test.ts`.

NVIDIA gotchas (last verified 2026-05-20 against PR #60, 203-line diff; original entry 2026-04-24 against PR #45):
- **Aggressive overshoot framing is filtered.** "I'm positive there are at least 30 issues — find them all" either silently TCP-closes or hangs past the 5-min gateway timeout. Each overshoot reviewer (`code`, `silentFailure`, `security`) now carries a `systemSoft` variant in `reviewers.ts`; `ModelClient.preferSoftPrompts=true` makes `pickSystem()` swap it in. Confirmed A/B: aggressive → 504 at 5:02; soft → 200 in 9.9s end-to-end.
- **Model IDs are versioned and drift fast — don't guess, don't trust stale notes.** `deepseek-ai/deepseek-v3` / `moonshotai/kimi-k2` return 404. **As of 2026-05-20:** `moonshotai/kimi-k2-instruct-0905` is GONE (April's verified ID); replaced by `moonshotai/kimi-k2.6`. `deepseek-ai/deepseek-v3.2` is GONE; replaced by `deepseek-ai/deepseek-v4-flash` / `deepseek-v4-pro`. Confirmed working today: `moonshotai/kimi-k2.6` (kimi-k2-instruct-0905 successor — A/B'd on PR #60, 31.4s, 23 findings, free). Other current options seen in `/v1/models`: `meta/llama-3.3-70b-instruct`, `meta/llama-4-maverick-17b-128e-instruct`, `nvidia/llama-3.3-nemotron-super-49b-v1.5`. Reasoning models (e.g. `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`) return output in a `reasoning` field the parser doesn't read — skip unless wiring that up. **Always `curl /v1/models` before relying on a specific ID; the drift window is ~4 weeks.**
- **Extended headersTimeout.** Node's built-in fetch defaults to 300s headersTimeout (undici); `NvidiaModelClient` uses `undici.Agent` with 900s so a slow-but-eventually-successful call doesn't fail client-side before NVIDIA's own 5-min edge timeout decides.
- **Ensemble fan-out (`NVIDIA_MODEL_POOL`).** With a comma-separated pool, each `createReview` dispatches to every model in parallel with a `AbortSignal.timeout()` per model (default 240s — below NVIDIA's 5-min edge). Partial success is tolerated; `triage.ts` dedupes overlap. A/B on PR #45 (2026-04-24): single Kimi → 3 findings in 6.5s; Kimi+MiniMax+DeepSeek pool → 8 findings in 4:00 (MiniMax timed out, other two merged). Recall roughly 2-3× at the cost of wall time bounded by the slowest surviving model. Calibration differs across models (DeepSeek is more aggressive about CRITICAL than Kimi) — treat ensemble output as "candidate findings for review," not ground truth.

When adding providers, extend `src/model-client.ts` (ModelClient interface + factory) — do NOT inline SDK calls in `index.ts`. CI (`.github/workflows/claude-flow-review.yml`) is pinned to Anthropic; non-Anthropic providers are local/opt-in until validated.

## Pipeline Discipline Rules

These rules apply to Phase 0–6 work and to authoring claude_flow components (skills, hooks, agent-sdk). Bias: caution over speed on non-trivial work. Each rule maps to a documented recurring failure mode.

### Rule 4 — Goal-driven execution: define success, loop until verified
Every plan (`writing-plans`) and every Phase 5 implementation must state explicit, machine-checkable success criteria before work begins. Iterate against the criteria; don't follow steps blindly. Vague acceptance ("the feature works") fails this rule — name the command, expected output, or artifact that proves success.

### Rule 5 — Use the model only for judgment calls
LLM calls in this repo are for: review judgments, finding-severity reasoning, plan critique, code generation. Do NOT route through LLMs: deduplication (use Dice/Jaccard in `triage.ts`), file-path resolution, severity-bucket sorting, "did task X complete" (parse the artifact). `pr-reviewer/triage.ts` is the reference example — extend the deterministic surface rather than adding model calls for transforms code can answer. Cost, latency, and variance all benefit.

### Rule 6 — Token budgets are not advisory
Each phase and each agent dispatch carries a budget (see `token-economy` skill). If a phase approaches its budget, summarize and checkpoint — do not silently overrun. Surface the breach as an explicit field in phase output. The free-tier NVIDIA pool exists in part to make budgets enforceable on the review pipeline; treat budget breaches the same way as test failures.

### Rule 7 — Surface conflicts, don't average them
When two reviewers/models disagree on the same finding (severity, classification, fix recommendation), `triage.ts` must surface both with attribution and pick one with stated reason — never silently merge to median. Calibration differs across models (documented: DeepSeek is more aggressive about CRITICAL than Kimi). Averaging hides the signal that disagreement provides. Same rule for conflicting patterns in code: pick the more recent / more tested one, explain why, flag the other for cleanup.

### Rule 10 — Checkpoint after every significant step
Phase boundaries already checkpoint. For long Phase 5 runs (>30 min or >5 file edits), insert intra-phase checkpoints: what's done, what's verified, what's left. Required after every shadow-path verification (`git rev-parse --show-toplevel`) and before every push. If you lose track of state, stop and restate before continuing.

### Rule 12 — Fail loud
"Phase complete" is wrong if any sub-step was skipped, timed out, or degraded. Every phase must emit `skipped: [...]`, `degraded: [...]`, and `unverified: [...]` fields explicitly — empty arrays are fine, missing fields are not. Specific surfaces this rule covers:
- Ensemble partial-success (NVIDIA pool with timeouts) → list which models failed, don't claim full coverage
- `cache_control` writes under 1024 tokens → surface as `cache_skipped`, don't claim caching is on
- Revalidate pass dropping findings → list dropped findings with reason
- `[X]` audit downgrades (PR #67) → emit `[~]` with reason, not silent removal
- Test suites with skipped cases → never report "tests pass" without surfacing skip count

### Rule 13 — Three-Layer Termination Check (lint → tests/startup → user flow)
Phase 5 "complete" requires passing all three layers IN ORDER. Do not proceed to layer 2 while layer 1 fails; do not declare success on layer 2 without exercising layer 3 for surfaces a user would touch. Extends Rule 12 with an ordering contract — the existing "fail loud" rule covered the WHAT (surface every gap) but not the WHEN (don't run integration tests on code that won't compile). Pattern sourced from walkinglabs/learn-harness-engineering lecture 09. Specific surfaces:
- Pre-commit / typecheck / format errors → block before any test run is reported
- Unit + integration test failures → block before any "ship it" / runtime claim
- User-facing flow (dev server start, endpoint response, UI render) → required before "feature works" is claimed
- For PR reviewer: the three layers map to `tsc --noEmit` → `npm test` → `node dist/index.js --dry-run <PR>`

### Process Patterns — observed in 2026-05 triage

- **Session scoping: prefer weeks-of-work tasks over granular Phase 5 batches** when work has a natural through-line. Simon Last's lesson (2026-05-23): long-running implementer sessions (days to weeks, compacting many times) accumulate convention memory that short-lived per-feature sessions lose. Validate against claude-flow Phase 3 (requirements) sizing — if a feature splits into 5+ thin sub-features that share state and conventions, default to one larger session with intra-session checkpoints (Rule 10) rather than a sub-feature relay. The relay overhead (handoff cost + re-loading context) is often higher than the per-session compaction tax.
- **Side-quest workflow during PR review** — AI review (especially multi-model ensemble) routinely surfaces pre-existing bugs unrelated to the PR's stated scope. Default disposition: file each as a `mcp__ccd_session__spawn_task` chip rather than expanding the current PR. The current PR's review comment should note "N side-quests filed" so the user can decide which to spin off. Pattern sourced from Nolan Lawson's "Using AI to write better code more slowly" (2026-05-25).

## Multi-Clone Gotcha

The "two-clones" gotcha is not unique to this repo. Any project cloned more than once on the same filesystem can trigger it. Confirmed instances:

- **claude_flow:** canonical `/Users/summerrae/claude_code/claude_flow/` vs shadow `/Users/summerrae/claude_flow/`
- **courierflow:** canonical `/Users/summerrae/courierflow/` plus `/Users/summerrae/courierflow/.claude/worktrees/*/` — a 2026-04-20 parallel-agent PR (#443) shipped byte-identical `docs/routines/*.md` files from a shadow clone BEFORE the author's commit could land.

Always run `git rev-parse --show-toplevel` on the first turn. If cwd is a shadow path, switch to canonical before writing. A shadow clone can appear populated in one turn and nearly empty the next. When your local commit can't cherry-pick onto `origin/main` cleanly — suspect parallel-agent pickup, verify with `git diff origin/main HEAD -- <paths>`, and if empty your work is already upstream. See MEMORY `two_clones_same_repo`, `shadow_path_drift_within_session`, `two_clones_gotcha_generalized`, `git_cherry_pick_empty_signal`, and `reset_hard_after_upstream_verification`.

## Known Gotchas

- **Anthropic `cache_control` silently no-ops below 1024 tokens:** Sonnet/Opus prompt-cache writes require ≥1024 cached tokens (2048 for Haiku). Under that, `usage.cache_creation_input_tokens=0` + `cache_read_input_tokens=0`, no error raised. Verify live (not via unit tests) before claiming prompt caching works. Tool-use schemas (advisor-tool beta) may additionally break prefix reuse — assert `cache_read > 0` across consecutive calls, not just on the first. See `docs/decisions/2026-04-24-advisor-tool-verdict.md`.
- **Verify LLM pricing before every cost eval:** Anthropic/OpenAI/Google rates can move 50%+ between plan authoring and execution (Opus 4.7 dropped 66% in ~6 weeks, Apr 2026). Triangulate against the provider's pricing page + a second surface (docs or console), stamp `# verified YYYY-MM-DD` in `scripts/pricing.py`, and re-run the check when resuming a paused eval plan.
- **Keyword-substring rubrics are structurally broken for signal-to-noise:** Discriminator keywords like "however", "but", "trade-off" appear in nearly every non-trivial answer — rubrics that check for their *presence* score ~1.0 across all arms and hide real differences. Use LLM-as-judge for nuanced quality dimensions; reserve keyword checks for hard-required literals (specific API names, required section headings).
- **Plan-step kill criteria actually save money:** The Step 6 re-pilot gate in `docs/archive/plans/2026-04-24-advisor-ab-eval-tuning.md` caught a 66% price shift that invalidated the 20-trial premise at $0.76 spend vs $12-25 budgeted. When a plan has a measurable premise (cost, quality, latency), codify a mid-plan gate that re-verifies the premise before the expensive step.
- **Decision-evidence artifacts (`results_*.json`) may be gitignored:** `evals/*/results_*.json` is gitignored, but pilot results that justify a decision doc need to be committed. Use `git add -f <file>` and reference the blob from the decision markdown. Consider narrowing the ignore pattern (e.g. only ignore `results_*_local.json`) if this recurs.
- **CodeRabbit treats `git mv` renames as new authorship:** Docs-only PRs that rename N files + edit a few will produce ~N findings on the renamed files (style nits, "missing context" on content CR can't see was just relocated). Filter by inspecting `git log --follow --diff-filter=R` on the flagged paths — if the file is a pure rename or rename+trivial edit, the finding is almost always noise. Hit on PR #58: 21 of 22 findings were on archived files. Corollary to the existing authored-vs-upstream filter in `~/.claude/CLAUDE.md` Plugin Cache section.
- **Date-stamped model-ID entries decay in ~4 weeks; track removals explicitly.** When CLAUDE.md or a plan names a specific verified model ID, add a "GONE since [date]:" subline listing IDs that have disappeared, rather than silently replacing them. The April-2026 NVIDIA gotcha named `moonshotai/kimi-k2-instruct-0905` as "confirmed working"; a May-2026 `/v1/models` query showed it had been removed and replaced by `kimi-k2.6`. Without an explicit GONE list, downstream readers will keep referencing the dead ID. Re-verify model-ID entries on every multi-provider plan; the drift window is short enough that any plan citing a specific ID more than ~4 weeks old should re-`curl /v1/models` before relying on it.
- **Stale `session-learnings/<date>-*` branches collide with canonicalized SKILL.md files.** If a learnings branch sat unmerged while main absorbed canonical versions of the same skills (a different PR shipped `<skill>/SKILL.md` in between), the rebase produces add/add conflicts on `<skill>/SKILL.md`. When the branch's diff for that file is `+N / -0` (pure addition of a draft that's been superseded), resolve with `git checkout --theirs <path>` — but ONLY after spot-checking branch-unique content via `git show <branch>:<path> | diff - <path>` to confirm no original content is lost. UU conflicts (both sides edited the same line range) still need hand-merge. Hit on claude-skills PR #104 (2026-05-27): 3 of 4 SKILL.md conflicts were superseded-drafts resolved with `--theirs`; 1 was a real edit overlap that needed hand-merge to preserve a new "Common mistakes" row alongside a new "Notes" section.
- **Workflow-tool primitives can't back the pr-reviewer headless app.** The Claude Code Workflow tool's `agent()`/`parallel()`/`pipeline()` run only inside a Claude Code session; `agent-sdk/pr-reviewer/` runs as `node dist/index.js` in CI, so it adopts workflow-style semantics (`degraded[]`/`skipped[]` status, per-model `segments[]` provenance join, `PR_REVIEWER_MAX_REVALIDATE` budget cap — see [PR #66](https://github.com/sumrae412/claude_flow/pull/66)) WITHOUT the Workflow tool. Don't re-propose "port pr-reviewer to a Workflow script." See agent-vault `agent/claude-code-workflow-tool.md`.

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

## External SDD Framework Coverage

claude-flow Phase 0–6 covers ~90% of github/spec-kit's spec-driven-development surface (constitution → specify → plan → tasks → implement). The two genuine gaps were closed in claude-skills PR #67 (squash-merged 2026-05-01, commit `bfad6d2`):

- **Phantom-completion audit** — `executing-plans/SKILL.md` Step 4.5 + `claude-flow/phases/phase-5-implementation.md` HARD GATE before Phase 5.5. Re-parses `[X]` tasks against on-disk artifacts; downgrades hollow checkmarks to `[~]` and surfaces them.
- **Spec-references-as-context gate** — required `## References` section in `writing-plans` plan header; `smart-exploration` and `executing-plans` Step 1a treat the section as a whitelist for prior-art context. Surfaces `REFERENCES_GAP` / `REFERENCES_MISSING` instead of silently expanding context.

Before pulling more from spec-kit (or any SDD framework), invoke `/useful-for` against claude-flow first — most surface area is already covered.

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

- `docs/archive/plans/2026-04-05-platform-layer-design.md` — Platform layer design (approved, archived 2026-05-17 after shipping)
- `docs/archive/plans/2026-04-05-platform-layer-implementation.md` — 22-task implementation plan (executed, archived 2026-05-17)
- `docs/plans/INDEX.md` — Index of active plans + archived plans (90-day deletion window)
- `README.md` — User-facing installation and usage guide
- `skills/code-creation-workflow/references/` — Memory injection, hook templates, skill triggers, error recovery
