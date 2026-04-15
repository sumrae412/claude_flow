# Design: Excalidraw Canvas + Curmudgeon Reviewer for claude-flow

**Created:** 2026-04-15 | **Status:** approved

## Problem

Two gaps in claude-flow v3, both highlighted by CJ Hess's [How I AI episode](https://www.chatprd.ai/how-i-ai/cj-hess-tenex-custom-dev-tools-and-model-vs-model-code-reviews):

1. **No visual feedback loop for UI work.** Phase 4 architecture output is text-only. When a feature touches `*.tsx`, `*.html`, `*.css`, etc., the user has no way to draw/edit a mockup and have Claude consume the result. The article's `flowy` tool solves this with a JSON-backed visual canvas; the user wants the same pattern but using Excalidraw, weighted toward UI iteration.
2. **No non-Anthropic reviewer.** Phase 6's cascade is all-Anthropic. MEMORY flags this as `multi_model_deferred` — `debate-team` exists but requires API keys the user hasn't set. The article's "curmudgeonly staff engineer" pattern (GPT-5.2 Codex as a second opinion) catches code smells and wrong abstractions that a same-family reviewer misses.

## Approach

Two additive features, no rewrites. Both match existing claude-flow patterns (opt-in flags, declarative registry, progressive disclosure, early-exit respect).

### A. Excalidraw Canvas — Hybrid Round-Trip

**Activation (opt-in):**
- `/claude-flow --visual` flag, OR task description contains "UI mockup" / "visual review"
- Independent: Phase 4 always emits `architecture.excalidraw` when the plan has a diagrams section (one-way, no round-trip)

**Files (git-tracked, in the host project's repo):**
- `docs/design/<feature>/architecture.excalidraw` — one-way, Phase 4 architect → user viewing only
- `docs/design/<feature>/mockups/<screen>.excalidraw` — round-trip, Phase 4 → user edit → Phase 5 input

**Round-trip flow (UI mockups, opt-in only):**
1. Phase 4 architect drafts `$plan` as today
2. [new] `excalidraw-canvas` skill generates initial `.excalidraw` mockups per screen/component from `$plan` + `$requirements`
3. [new] Workflow prints the open command + pauses: *"Edit in VS Code (Excalidraw extension) or excalidraw.com. Reply 'continue' when done."*
4. [new] Architect re-reads the edited files, emits `$plan` delta if UI drifted
5. Phase 5 UI-task implementers read `.excalidraw` alongside `$plan` as extra context

**Editor (no new infrastructure):**
- **Primary:** VS Code Excalidraw extension (zero round-trip overhead — save triggers re-read)
- **Fallback:** `scripts/open_excalidraw.sh` detects missing extension and opens excalidraw.com with file loaded

**Why Phase 4 only (not Phase 3):**
Requirements are text-first (EARS acceptance criteria, user stories). Visual mockups tied to a firm `$plan` produce useful drift detection; mockups tied to vague requirements produce rework. Can revisit adding Phase 3 later if demand appears.

**Why hybrid (one-way architecture, round-trip UI):**
Architecture diagrams rarely need user editing — they reflect decisions already made. UI mockups benefit from the user pushing pixels around faster than text can describe them. Scoping round-trip to UI keeps complexity proportional to payoff.

### B. Curmudgeon Reviewer — Non-Anthropic Tier 2

**New entry in `reviewer-registry.json`:**

```json
{
  "id": "curmudgeon-review",
  "tier": "always",
  "cascade_tier": 2,
  "runner": "codex-cli",
  "model": "gpt-5-codex",
  "description": "Non-Anthropic second opinion — code smells, wrong abstractions, lazy tests"
}
```

**Runner:** `scripts/curmudgeon_review.sh <diff-path>` shells out to the local `codex` CLI. No API key in repo; uses existing ChatGPT auth. Outputs structured findings parseable by the existing Phase 6 orchestrator (same format other reviewers produce: severity / file / line / rationale).

**Persona prompt:**

> You are a curmudgeonly staff engineer reviewing a PR. You've seen every antipattern and you're tired. Focus on: code smells, inconsistencies with existing patterns, places where the diff works but is the wrong abstraction, tests that prove nothing, and suspicious silent failure modes. Be specific; cite `file:line`. Do not praise. Do not repeat what CodeRabbit said.

**Placement rationale:**
- **Tier 2, not Tier 1** — respects the early-exit optimization. Clean diffs (no Tier 1 HIGH+ findings) don't pay for curmudgeon. Matches MEMORY `early_exit_cascades` and `tier_placement_preserves_early_exit`.
- **Always-tier, not opt-in** — unlike the excalidraw canvas, curmudgeon has zero UX friction when the CLI is installed. Opt-in makes sense for workflow pauses; not for parallel reviewers.
- **Not batched** with lightweight Sonnet reviewers — this is an opinionated single-model review, per MEMORY `batch_similar_agents` (only batch reviewers sharing input + output format).

**Graceful degradation:**
- If `codex` CLI not installed → script exits 0 with warning; Phase 6 continues without the reviewer. Addresses MEMORY `bootstrap_before_reference` (check presence before call).

## Data Flow

```
Phase 4 (--visual or UI-mockup keyword)
  ├── architect drafts $plan (as today)
  ├── [new] excalidraw-canvas generates .excalidraw mockups from $plan + $requirements
  ├── [new] pause: user edits in VS Code / excalidraw.com
  └── [new] architect re-reads edited mockups, updates $plan if drift

Phase 5
  └── UI-task implementers read .excalidraw alongside $plan (path reference, no contract change)

Phase 6
  ├── Tier 1: CodeRabbit (unchanged) → early-exit check (unchanged)
  ├── Tier 2: silent-failure + security + test-coverage + prod-readiness + [NEW] curmudgeon (parallel)
  └── Tier 3+: lightweight-reviewer batch (unchanged)
```

## Files Touched

**New:**
- `skills/excalidraw-canvas/SKILL.md` — thin router (invocable standalone via `/excalidraw-canvas` and loaded by Phase 4 when `--visual`)
- `skills/excalidraw-canvas/references/excalidraw-schema.md` — compact JSON schema subset (rect, text, arrow, group, color)
- `skills/excalidraw-canvas/references/mockup-prompts.md` — generation prompts + drift-detection prompts
- `scripts/curmudgeon_review.sh` — Codex CLI wrapper with persona system prompt
- `scripts/open_excalidraw.sh` — detect VS Code extension → fallback to excalidraw.com URL
- `tests/fixtures/excalidraw/*.excalidraw` + shell tests for both scripts

**Edited:**
- `reviewer-registry.json` — add curmudgeon entry (single line addition)
- `skills/claude-flow/phases/phase-4-architecture.md` — add `--visual` guarded mockup step + re-read step
- `skills/claude-flow/phases/phase-5-implementation.md` — "read mockup files as context" instruction for UI tasks
- `skills/claude-flow/phases/phase-6-quality.md` — reference curmudgeon in reviewer dispatch prose
- `skills/claude-flow/SKILL.md` — document `--visual` flag in flag reference
- `CLAUDE.md` — mention `/excalidraw-canvas` in the Domain Skills table

**NOT touched (scope lock):**
- `contracts/*.schema.md` — `.excalidraw` files referenced by path, no new contract needed
- `skills/claude-flow/diagrams/*.mmd` — workflow reference diagrams stay as Mermaid
- Existing reviewer entries in `reviewer-registry.json`
- `debate-team` skill — separate multi-model path, untouched

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| User doesn't have VS Code Excalidraw extension | `open_excalidraw.sh` detects and falls back to excalidraw.com URL |
| User doesn't have Codex CLI | Graceful skip with log warning; Phase 6 continues |
| `.excalidraw` JSON too complex to regenerate reliably | Use compact schema subset (rect/text/arrow/group/color) in `references/excalidraw-schema.md`; reject elements outside subset |
| User forgets to resume after editing | Optional `--auto-resume-after Nm` flag; default is block-until-continue |
| Phase drift when user edits mockup after architect finished | Architect re-reads post-edit and emits `$plan` delta inline (explicit step in Phase 4) |
| Curmudgeon duplicates CodeRabbit findings | Persona prompt explicitly instructs "don't repeat CodeRabbit findings"; existing Phase 6 orchestrator does a dedup pass |
| Codex output drifts from expected format | Script enforces JSON schema on output; malformed → skip with warning (not failure) |
| `.excalidraw` file bloat in repo | Only commit if user elects to; mockups go under `docs/design/<feature>/` (easy to `.gitignore` if needed) |

## Ruled Out

- **Local dev server / file watcher** — Flowy-style custom rendering. Abandoned: VS Code extension already provides the round-trip; duplicating that is maintenance debt for marginal gain.
- **Phase 3 mockups** — Visual mockups tied to firm `$plan` (Phase 4) beat mockups tied to unstable requirements.
- **Replacing CodeRabbit Tier 1 with curmudgeon** — CodeRabbit is dialed in; swap risks regression. Curmudgeon complements, doesn't replace.
- **OpenAI API billing path** — Codex CLI uses existing ChatGPT auth; avoids opening a new billing surface.
- **Rewriting `reviewer-registry.json`** — One-line addition only; existing entries unchanged.
- **New `$mockups` contract schema** — Path reference is sufficient; adding a contract introduces coupling without carrying new information.
- **Always-on visual checkpoint (non-opt-in)** — Breaks autonomous path for backend-only features; wrong default for an autonomous workflow.

## Known-Gotcha Memory Hits

This design is informed by these MEMORY entries:

- `multi_model_deferred` — **unblocked** by Codex CLI approach (no API key required in repo)
- `bootstrap_before_reference` — curmudgeon + excalidraw scripts both presence-check tools before invoking
- `overshoot_prompt_scope` — curmudgeon is structured-checklist, NOT overshoot-wired
- `early_exit_cascades` — curmudgeon at Tier 2 respects CodeRabbit early-exit
- `tier_placement_preserves_early_exit` — new always-tier entry goes to Tier 2, not Tier 1
- `batch_similar_agents` — curmudgeon is opinionated single-model, NOT batched with Sonnet reviewers
- `declarative_config_pattern` — curmudgeon added via `reviewer-registry.json`, not hardcoded in a phase file
- `compose_dont_replace` — excalidraw composes with existing Phase 4, doesn't reimplement architect
- `progressive_disclosure` — `excalidraw-canvas` skill is router + lazy-loaded references, not monolithic
- `script_for_mechanical_checks` — `open_excalidraw.sh` detection is a script, not an LLM step
- `grep_callers_before_commit` — initial commit wires scripts to callers (phase files + reviewer registry) so they're not orphaned

## Testing

- **Unit:** Shell tests for `curmudgeon_review.sh` (mock diff → parseable output) and `open_excalidraw.sh` (extension detection logic)
- **Integration:** Phase 4 dry-run with `--visual` emits `.excalidraw` files to expected paths
- **Integration:** Phase 6 dispatch test confirms curmudgeon entry is picked up by the reviewer-registry parser
- **Fixtures:** Known-good `.excalidraw` files in `tests/fixtures/excalidraw/` covering: simple rect+text, flowchart with arrows, multi-screen UI mockup

## Success Criteria

- Running `/claude-flow --visual "add settings page"` on a UI feature produces editable `.excalidraw` files in `docs/design/settings-page/mockups/`, pauses for user edits, and Phase 5 implementers receive the edited version as context.
- A Phase 6 run on a dirty diff (CodeRabbit HIGH+ present) dispatches curmudgeon in parallel with existing Tier 2 reviewers; its findings appear in the consolidated review output with citations.
- A Phase 6 run on a clean diff (CodeRabbit early-exits) does NOT invoke curmudgeon (preserves early-exit).
- Missing Codex CLI or VS Code Excalidraw extension produces warnings, not failures.

## Next Steps

Hand off to `writing-plans` skill to produce the implementation plan (tasks, dependencies, TDD cycles). Separate plan file: `docs/plans/2026-04-15-excalidraw-canvas-curmudgeon-plan.md`.
