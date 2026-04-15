# Plan: Mockup State Matrix + Refactor-Path Extract

**Branch:** `feat/workflow-improvements-from-pattern-mining`
**Date:** 2026-04-15
**Source:** User + Opus conversation re: Figma MCP workflow article

## Summary

Two related improvements to `excalidraw-canvas` + `visual-verify`:

1. **State matrix** — Phase 4 UI mockups must enumerate all UI states (default, loading, error, empty, success). Phase 5 `visual-verify` iterates screenshots over each state. Closes the happy-path-only gap.
2. **Refactor-path extract (spike)** — For UI-REFACTOR tasks, seed Phase 4 mockups from existing production state via Playwright DOM extraction, not a blank canvas.

## Ruled Out

- **Workflow #3 `/ship` automation** — already exists as `shipping-workflow` skill. No duplicate.
- **New `$mockups` top-level contract absorbing architecture diagrams** — existing `excalidraw-canvas/SKILL.md` boundary explicitly rejects this coupling. Keep states as a per-UI-screen attribute referenced from `$plan`, not a new contract.
- **Multi-viewport state matrix (mobile/tablet/desktop × states)** — scope creep. States only for now; viewport axis is a future extension.

## Steps

### Feature 1: State Matrix (lands first)

#### Step 1 — Extend mockup-prompts.md with state matrix convention
- type: `shared_prerequisite`
- files: `skills/excalidraw-canvas/references/mockup-prompts.md`
- depends_on: none
- test_requirements: none (docs change)
- Update the "Generate Initial Mockup" prompt to require one `.excalidraw` file per (screen, state) tuple, using path convention `docs/design/<feature>/mockups/<screen-slug>__<state>.excalidraw`. Default state set: `default`, `loading`, `error`, `empty`. Add per-state scripting hints (state-trigger scripts).

#### Step 2 — Add mockup-manifest.schema.md contract
- type: `shared_prerequisite`
- files: `skills/claude-flow/contracts/mockup-manifest.schema.md` (new)
- depends_on: 1 (knowledge)
- test_requirements: example manifest parses as valid JSON
- Defines a per-feature `mockup-manifest.json` enumerating screens × states with URLs and trigger scripts. Consumed by `visual_verify.py` iteration mode and referenced from `$plan`.

#### Step 3 — Extend visual_verify.py with manifest iteration mode (TDD)
- type: `value_unit`
- files: `skills/claude-flow/scripts/visual_verify.py`, `tests/skills/claude-flow/test_visual_verify.py`, `tests/fixtures/visual_verify/manifest_*.json` (new)
- depends_on: 2 (knowledge)
- test_requirements:
  - `test_manifest_mode_iterates_all_states` — manifest with 3 states triggers 3 render calls (Playwright forced-unavailable to stub)
  - `test_manifest_mode_any_state_mismatch_blocks_gate` — if state N fails, overall exit = 1
  - `test_manifest_missing_file_skips_gracefully` — non-existent manifest → skip envelope, exit 0
  - `test_manifest_malformed_json_skips_gracefully` — parse error → skip envelope
  - `test_single_mockup_mode_still_works` — backward-compat regression guard
  - `test_manifest_per_state_url_and_trigger_used` — URL suffixes and trigger scripts passed to render_and_extract
- Add `--manifest <path>` arg. When present, iterate every `screens[].states[]` entry: render at `base_url + url_suffix`, run trigger script if any, compare against that entry's `mockup_file`. Findings accumulate across all states. Preserve existing `--mockup` single-file mode.

#### Step 4 — Thread manifest through Phase 4 + Phase 5 docs
- type: `value_unit`
- files: `skills/claude-flow/phases/phase-4-architecture.md`, `skills/claude-flow/phases/phase-5-implementation.md`, `skills/excalidraw-canvas/SKILL.md`
- depends_on: 3 (build)
- test_requirements: none (docs change — verified by Phase 6 grep-for-reference-consistency)
- Phase 4: after mockup generation, emit `docs/design/<feature>/mockup-manifest.json`. Phase 5 Step 3d: prefer `--manifest` over `--mockup` if manifest exists. Update `excalidraw-canvas/SKILL.md` Two Modes table to note state matrix.

### Feature 2: Refactor-Path Extract (spike)

#### Step 5 — Build extract_mockup.py (TDD)
- type: `value_unit`
- files: `skills/claude-flow/scripts/extract_mockup.py` (new), `tests/skills/claude-flow/test_extract_mockup.py` (new)
- depends_on: 3 (knowledge — reuses Playwright rendering pattern)
- test_requirements:
  - `test_skip_when_playwright_unavailable` — graceful skip envelope, exit 0
  - `test_skip_when_url_unreachable` — network failure → skip
  - `test_dom_to_excalidraw_shapes_produces_valid_json` — accepts stub DOM boxes, emits valid Excalidraw JSON (unique ids, supported types, parses)
  - `test_output_has_no_more_than_N_elements` — cap at 80 elements (Claude-writable scale)
  - `test_broken_extraction_emits_skip_not_empty_file` — if 0 DOM elements extracted, skip rather than write empty Excalidraw
- Renders URL via Playwright, extracts DOM element list (tag, bbox, computed color/fontSize), maps each to an Excalidraw rectangle or text element. Writes `.excalidraw` skeleton. Documents in docstring: known lossy aspects (no gradients, no images beyond placeholder boxes, no transforms, flattened z-index).

#### Step 6 — Wire extract into Phase 4 for REFACTOR task type
- type: `value_unit`
- files: `skills/claude-flow/phases/phase-4-architecture.md`, `skills/excalidraw-canvas/SKILL.md`
- depends_on: 5 (build), 4 (build — resolves edit conflicts on Phase 4 doc)
- test_requirements: none (docs change)
- Add task-type detection: if `$requirements.task_type == "refactor"` AND `$requirements.target_url` is set, Phase 4 runs extract first, then iterates on that skeleton. Document failure modes in `excalidraw-canvas/SKILL.md` Failure Modes table: lossy extraction, missing elements, user falls back to fresh mockup.

## Acceptance

**Feature 1:**
- Running `visual_verify.py --manifest <manifest>` iterates every state and exits 1 if any state fails.
- Running `visual_verify.py --mockup <file>` (existing shape) still works unchanged.
- Phase 4 docs instruct executor to emit manifest + per-state `.excalidraw` files for UI tasks.
- All existing tests green; new tests green.

**Feature 2:**
- `extract_mockup.py --url <u> --output <f>` writes a valid `.excalidraw` when Playwright + URL are available.
- All failure modes emit skip envelope; never writes corrupted output.
- Phase 4 docs gate extract on `task_type == "refactor"` so greenfield mockups stay unchanged.
- Failure modes explicitly enumerated in `excalidraw-canvas/SKILL.md`.

## Files Affected

| # | Path | Action |
|---|------|--------|
| 1 | `skills/excalidraw-canvas/references/mockup-prompts.md` | modify |
| 2 | `skills/claude-flow/contracts/mockup-manifest.schema.md` | new |
| 3 | `skills/claude-flow/scripts/visual_verify.py` | modify |
| 3 | `tests/skills/claude-flow/test_visual_verify.py` | extend |
| 3 | `tests/fixtures/visual_verify/manifest_*.json` | new |
| 4 | `skills/claude-flow/phases/phase-4-architecture.md` | modify |
| 4 | `skills/claude-flow/phases/phase-5-implementation.md` | modify |
| 4 | `skills/excalidraw-canvas/SKILL.md` | modify |
| 5 | `skills/claude-flow/scripts/extract_mockup.py` | new |
| 5 | `tests/skills/claude-flow/test_extract_mockup.py` | new |
| 6 | `skills/claude-flow/phases/phase-4-architecture.md` | modify (additional) |
| 6 | `skills/excalidraw-canvas/SKILL.md` | modify (additional) |
