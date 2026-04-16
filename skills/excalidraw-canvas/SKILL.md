---
name: excalidraw-canvas
description: Use when user wants visual UI mockups or architecture diagrams with round-trip editing. Generates .excalidraw files Claude can write and the user can edit in VS Code or excalidraw.com. Invoked standalone via /excalidraw-canvas or by claude-flow Phase 4 when --visual flag is set.
user-invocable: true
---

# Excalidraw Canvas

Generate editable `.excalidraw` files for UI mockups and architecture diagrams. Uses a compact JSON subset the executor can write reliably; the user edits in VS Code (Excalidraw extension) or at excalidraw.com. Round-trip mode re-reads user edits and detects drift against the plan.

**Announce:** "Generating excalidraw canvas — will print the open command so you can edit."

---

## When to Load

- **Standalone:** user runs `/excalidraw-canvas` (explicit request to draft or open a mockup).
- **Phase 4 integration:** claude-flow's Phase 4 loads this skill when either (a) `--visual` flag present, (b) task description contains UI signals ("mockup", "visual review", "screen"), or (c) the `$plan` contains a `diagrams` section (one-way architecture case).
- **File-pattern signals for UI work:** `*.tsx`, `*.jsx`, `*.html`, `*.css`, `app/templates/*`, `components/**` — these are the cases Phase 4 most often pairs with this skill.

Not every UI task needs mockups. Skip for bug fixes, copy changes, or single-component tweaks where text description is already precise.

---

## Two Modes

| Mode | File location | Round-trip? | Phase owner |
|------|---------------|-------------|-------------|
| **Architecture diagram (one-way)** | `docs/design/<feature>/architecture.excalidraw` | No — user views only | Phase 4 architect |
| **UI mockup (round-trip, state matrix)** | `docs/design/<feature>/mockups/<screen>__<state>.excalidraw` + `mockup-manifest.json` | Yes — user edits, Phase 4 re-reads, Phase 5 consumes | Phase 4 → user → Phase 5 |

`<feature>` is a kebab-case slug of the feature name (e.g. `settings-page`). Architecture diagram = one file total. UI mockups = one file per (screen, state) tuple (state matrix) plus one `mockup-manifest.json` per feature.

**State matrix required for UI mockups.** Each screen enumerates the UI states that apply (default, loading, error, empty, success). Required-state sets per screen type live in `skills/claude-flow/contracts/mockup-manifest.schema.md`. Happy-path-only mockups ship bugs that `visual-verify` cannot catch.

**Refactor-path extract.** For UI-refactor tasks (`$requirements.task_type == "refactor"` with an existing `target_url`), mockups seed from the live page via `skills/claude-flow/scripts/extract_mockup.py` rather than a blank canvas. See Refactor Path below.

---

## Workflow

1. **Generate.** Read `references/mockup-prompts.md` and `references/excalidraw-schema.md`. Produce one `.excalidraw` file per screen (mockup mode) or one total (architecture mode). Write with the Write tool.
2. **Validate.** Confirm the file parses as JSON and every element has a unique `id` and a `type` in the supported subset before printing the open command. If invalid, regenerate — do not show the user a broken file.
3. **Print open command.** Emit the exact line `scripts/open_excalidraw.sh <file>` (one line per file when multiple). Do not auto-open — the script handles editor detection and fallback to excalidraw.com.
4. **If round-trip:** pause with the message *"Edit in VS Code (Excalidraw extension) or excalidraw.com. Reply 'continue' when done."* Wait for the user; do not loop or poll.
5. **Re-read on resume.** Load the edited file. Use `references/mockup-prompts.md` (drift-detection prompt) to compare generated vs edited. If drift is material, emit a `$plan` delta inline — the Phase 4 architect owns reconciling it before handing off.
6. **Phase 5 handoff.** The mockup path is referenced in `$plan` task descriptions, not embedded in a contract schema. Phase 5 implementers read the file alongside `$plan` as context.

---

## Refactor Path (Extract Before Iterate)

For UI-refactor tasks — where production already renders a version of the screen — seeding Phase 4 from a blank canvas wastes the existing layout as information.

**Trigger:** `$requirements.task_type == "refactor"` AND `$requirements.target_url` is set (e.g. `http://localhost:3000/settings`). Greenfield UI work stays on the blank-canvas path.

**Workflow:**

1. Phase 4 runs `skills/claude-flow/scripts/extract_mockup.py --url <target_url> --output docs/design/<feature>/mockups/<screen>__default.excalidraw` as the *default*-state seed.
2. The executor reviews the extracted skeleton. If extraction is skipped (Playwright missing, URL unreachable) or visibly lossy (empty output, broken DOM tree), fall back to the blank-canvas path and note the fallback.
3. The executor then generates the other state mockups (`loading`, `error`, `empty`, `success`) by *modifying copies* of the extracted default, not from scratch. This preserves the existing layout anchors.
4. User edits as usual. `visual-verify` then has a real before/after comparison.

**Failure modes are enumerated in the table below** — extraction is a lossy spike, not a pixel-perfect copier.

---

## Lazy-Loaded References

| Reference | Load when |
|-----------|-----------|
| `references/excalidraw-schema.md` | Writing any `.excalidraw` JSON — defines the supported element subset, envelope, and validation checklist |
| `references/mockup-prompts.md` | Generating initial mockups from `$plan` + `$requirements`, detecting drift after user edits, or emitting `$plan` deltas when drift is material |
| `../claude-flow/contracts/mockup-manifest.schema.md` | Emitting `mockup-manifest.json` after state-matrix mockups — defines required-state sets per screen type |

Read these files only when the step requires them; drop after use.

---

## Boundaries

This skill does **not**:

- Render or rasterize `.excalidraw` files. Rendering happens in the user's editor (VS Code extension or excalidraw.com).
- Export PNG/SVG. If the user wants an image asset, point them at the editor's export menu.
- Auto-open files. The opener is `scripts/open_excalidraw.sh` — this skill prints the command, the executor or user runs it. This preserves the terminal/editor boundary and matches the `script_for_mechanical_checks` MEMORY pattern.
- Introduce a new contract schema. `.excalidraw` files are referenced by path inside `$plan`; no `$mockups` contract. Adding one would couple Phase 4 and Phase 5 without carrying information that the path reference doesn't already carry.
- Replace Phase 4's architect. The architect still owns `$plan`; this skill produces visual artifacts consumed alongside it.

---

## Failure Modes

| Situation | Handling |
|-----------|----------|
| Generated JSON fails to parse | Regenerate from `references/excalidraw-schema.md`; do not show the user a broken file |
| User didn't edit (round-trip) | Proceed with the generated version; no drift delta needed |
| User edited heavily (many shapes moved/added/removed) | Run drift prompt; if material drift, emit `$plan` delta for architect review before Phase 5 |
| `scripts/open_excalidraw.sh` missing or not executable | Fall back to printing the file path and `https://excalidraw.com/` instructions; do not block |
| User is working backend-only and this skill was loaded by mistake | Exit early with no files written — no harm done |
| `extract_mockup.py` emits skip envelope (Playwright missing, URL unreachable) | Fall back to blank-canvas mockup path; note the fallback in Phase 4 output so the user knows the extract didn't run |
| `extract_mockup.py` produces visibly lossy output (missing large regions, broken DOM tree flattened to a few rectangles) | Keep the extracted file as a rough anchor but instruct executor to augment heavily from `$plan` + `$requirements`; do not treat extract as ground truth |
| State mockup missing for a screen type that requires it per schema | Executor generates the missing state before emitting manifest; do not ship a partial manifest — `visual-verify` will fail on incomplete coverage |
| Manifest references a `.excalidraw` path that doesn't exist | Treat as a generator bug; regenerate the missing state or remove the manifest entry. Never ship a manifest that points to a nonexistent file |
