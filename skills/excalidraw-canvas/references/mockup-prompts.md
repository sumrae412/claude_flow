# Mockup Prompts

Three prompts the `excalidraw-canvas` executor runs, in order: (1) generate initial mockups from the plan, (2) detect drift after user edits, (3) produce a `$plan` delta when drift is material. Each section below tells the executor what to do — treat these as instructions, not literal prompt strings to paste verbatim.

All `.excalidraw` output must follow `references/excalidraw-schema.md` (supported elements, envelope, validation checklist).

---

## 1. Generate Initial Mockup

**When to run:** Phase 4 architect has a complete `$plan` and `$requirements`. The feature touches UI (`*.tsx`, `*.jsx`, `*.html`, `*.css`, `app/templates/*`, or the plan contains a `screens` / `components` section).

**Inputs:**
- `<feature name>` — kebab-case slug used for the output directory (`docs/design/<feature>/`).
- `<screen/component list>` — pulled from `$plan`. One `.excalidraw` file per screen or top-level component.
- `<acceptance criteria>` — pulled from `$requirements`. Drives which UI affordances need to exist (a criterion like "user sees validation errors inline" implies a visible error region on the form).

**Instructions to the executor:**

For each screen/component, produce one `.excalidraw` file **per UI state**. State matrix is required — happy-path-only mockups ship bugs in error and loading states that `visual-verify` cannot catch.

**Default state set (generate all that apply to the screen):**

- `default` — normal populated view. Always required.
- `loading` — spinner, skeleton rows, or disabled submit. Required for any screen with async data.
- `error` — validation messages, API error, or recovery prompt. Required for any screen with a form, a network call, or acceptance criteria mentioning failure modes.
- `empty` — "no data yet" state. Required for any screen listing user-generated content.
- `success` — post-action confirmation. Required if an acceptance criterion names a success outcome distinct from `default`.

If a state doesn't apply (e.g., a static marketing page has no `loading`), omit it and note the omission in the Phase 4 output so the manifest is consistent.

**Per (screen, state):**

1. Name the output file `docs/design/<feature>/mockups/<screen-slug>__<state>.excalidraw` (double underscore between slug and state). Create the directory if it doesn't exist.
2. Enumerate the concrete UI elements the plan + acceptance criteria demand for *this state*. An error state shows an error message region; a loading state shows a spinner or skeleton; an empty state shows the empty-state CTA. Don't duplicate the `default` state's contents verbatim — each state mockup should differ in the elements the state itself introduces or removes.
3. Lay out elements top-to-bottom, left-aligned, inside a roughly 800×600 canvas. Use the grouping pattern from `references/excalidraw-schema.md`.
4. For each element, pick the closest shape from the supported subset (rectangle, ellipse, text, arrow, line). Button = filled rectangle + text. Input = outlined rectangle + placeholder text. Section header = text. Error banner = outlined rectangle + red-tinted text. Spinner = ellipse with a text label like "loading…".
5. Write the file using the Write tool. Validate against the checklist in `references/excalidraw-schema.md`.

**After all state mockups for every screen in the feature are written:**

6. Emit `docs/design/<feature>/mockup-manifest.json` — a single manifest per feature covering every screen × state combination. Follow the schema in `skills/claude-flow/contracts/mockup-manifest.schema.md`. Emit this once, after the final screen's last state is written — not after each screen. This is the artifact Phase 5 `visual-verify` iterates over.

7. If the plan has a `diagrams` section (architecture one-way case), produce one `docs/design/<feature>/architecture.excalidraw` using rectangle/ellipse nodes and arrows, no mockup group conventions. Architecture diagrams are single-state — no matrix needed.

**Output:** one `.excalidraw` file per (screen, state), one `mockup-manifest.json`, and optionally one `architecture.excalidraw`. Pass the list of mockup paths to the open-command printer.

---

## 2. Detect Drift (Post-Edit)

**When to run:** The user has indicated they're done editing (replied "continue" after the skill's pause). Only mockup-mode files — architecture diagrams are one-way, no drift check.

**Inputs:**
- `<generated-path>` — the file the skill originally produced. Check git history if the on-disk version has been overwritten (`git show HEAD:<path>` from the commit that added it).
- `<edited-path>` — the current on-disk version.

**Instructions to the executor:**

1. Parse both files as JSON. If either fails to parse, abort with a message: the user may have corrupted the file; ask them to re-open it in the editor.
2. Build a structured diff between the two `elements` arrays, keyed by `id`. Classify each change as one of:
   - **moved** — same `id`, `x` or `y` changed by > 20px.
   - **resized** — same `id`, `width` or `height` changed by > 20px.
   - **relabeled** — `text`-type element with same `id`, different `text` string.
   - **added** — `id` present only in edited.
   - **removed** — `id` present only in generated.
3. Emit a JSON summary (for internal use — do not show the raw blob to the user):

   ```json
   {
     "moved":     [{"id": "...", "from": [x, y], "to": [x, y]}],
     "resized":   [{"id": "...", "from": [w, h], "to": [w, h]}],
     "relabeled": [{"id": "...", "from": "old", "to": "new"}],
     "added":     [{"id": "...", "type": "rectangle", "hint": "..."}],
     "removed":   [{"id": "...", "type": "text", "hint": "..."}]
   }
   ```

   For `added` and `removed`, include a short `hint` describing the element (text content if it's a text element, nearby labels for shapes).
4. Decide whether the drift is **cosmetic** or **material**:
   - Cosmetic: only `moved` or `resized` entries, no `added`/`removed`/`relabeled`. User nudged the layout but didn't change the component set.
   - Material: any `added`, `removed`, or `relabeled` entry — the user's edit changed what the screen includes, not just how it's arranged.
5. If cosmetic: report the drift summary to the user in prose ("you moved the submit button down and widened the username field — no plan changes needed") and continue to Phase 5 with the edited file as-is.
6. If material: proceed to prompt 3.

---

## 3. Generate $plan Delta

**When to run:** Prompt 2 classified the drift as material.

**Inputs:**
- The drift JSON from prompt 2.
- The original `$plan` (the full populated contract, not a summary).

**Instructions to the executor:**

1. For each `added` / `removed` / `relabeled` entry, reason about what the user's edit implies at the plan level. Examples:
   - Added a "Sign in with Google" button → new OAuth flow → plan needs a task for OAuth integration, probably a new dependency and backend endpoint.
   - Removed the "Forgot password?" link → feature descope → plan's password-reset task is no longer in scope for this iteration.
   - Relabeled "Submit" to "Create account" → semantic shift from sign-in to sign-up → the feature's purpose may have changed; confirm with the user before treating as a real delta.
2. Emit a brief Markdown delta with exactly these three sections. Keep it under ~200 words total — the architect reconciles, not the canvas skill:

   ```markdown
   ## Plan Delta (excalidraw drift)

   ### Implies added to plan
   - <bullet per implied new task or requirement>

   ### Implies removed from plan
   - <bullet per implied descope>

   ### Needs architect confirmation
   - <bullet per edit whose intent is ambiguous>
   ```

3. Do not edit `$plan` directly. Emit the delta as output; the Phase 4 architect owns reconciling it into the contract before handing off to Phase 5.
4. If every material drift entry lands under "Needs architect confirmation" (i.e. the executor can't confidently infer intent), say so plainly. Better to surface ambiguity than invent architecture.

---

## Notes on Style

- Keep prompts 1-3 executor-facing. The user never sees the raw JSON drift blob; they see the prose summary in prompt 2 step 5 and the Markdown delta in prompt 3 step 2.
- Do not overshoot. These prompts are structured-checklist (per `overshoot_prompt_scope` in MEMORY) — do not append "find at least N issues" or similar. The executor produces exactly the changes the inputs imply.
- When in doubt between emitting a delta and asking the user, ask. Round-trip editing is a conversation, not a classifier.
