# Phase 4: Architecture (Executor Drafts + Advisor Critiques)

<!-- Loaded: after Phase 3 | Dropped: after user approves plan -->
<!-- Output: $plan contract -->
<!-- Step numbers are cross-referenced from other skills (search "Phase 4 Step N"
     across skills/, references/, docs/ before renumbering). Add new steps at
     the END or as `Step X.5` to preserve existing cross-refs.
     See memory/phase_step_renumbering.md. -->

The **executor (Sonnet)** drafts two competing architecture options. It has full context from Phase 2 exploration — it read the files firsthand, knows the patterns, understands the integration points. No architect subagents needed.

---

## Step 0: Cross-Document Consistency Check

Before drafting architectures, check if existing plans or PRPs contain decisions that constrain this feature:

```
1. Glob for existing docs:
   plans/PRP-*.md
   docs/plans/*.md

2. For each doc found:
   - Scan for file paths, service names, or models that overlap
     with the current feature's scope (from $exploration)
   - Extract: API contracts, architectural decisions, constraints

3. If overlapping docs exist:
   - Note constraints the new architecture must respect
   - Flag contradictions to surface during user presentation
     ("PRP-X specifies Y for this service — confirm precedence")
   - If no contradictions: proceed with constraints noted

4. If no existing docs: skip — proceed to Step 1
```

**Why this matters:** Without this check, the executor might draft an architecture that contradicts a decision from a prior session's PRP. The user then approves the plan, implementation proceeds, and the contradiction surfaces as a bug in Phase 6 (or worse, in production). A 30-second glob-and-scan prevents this.

### Extended Thinking for Phase 4 Advisors

Both advisor checkpoints in this phase (Architecture Critique + Plan Stress-Test) include "Think step by step" — these are the highest-stakes decisions in the workflow. A missed blind spot here propagates through all of implementation. Phase 2 (gap-finding) and Phase 5 (focused decisions) do NOT need extended thinking — speed matters more there.

---

## Step 1: Executor Drafts Two Options

The executor writes two architecture proposals with different optimization targets:

```
Option A: SIMPLICITY
  → Reuse existing patterns, minimal new files
  → Least moving parts, smallest diff
  → Trade-off: may sacrifice extensibility

Option B: CLEAN SEPARATION
  → Clear boundaries between concerns
  → Extensible, independently testable
  → Trade-off: more files, more indirection
```

**Each option includes:**
- Files to create/modify (with line counts)
- Component designs and responsibilities
- Data flow (how data moves through the system)
- What this approach sacrifices

---

## Step 2: Advisor — Architecture Critique

### Advisor: Architecture Critique

Dispatch Opus (`model: "opus"`, `subagent_type: "general-purpose"`) with:
- Input: `$exploration` + both option summaries (files, trade-offs)
- Question: "Blind spots? Which trade-offs am I underweighting? Hybrid approach?"
- Add: "Think step by step before responding."
- Act on response: revise options, note advisor's recommendation

**N-per-entity escalation:** If Step 1 produced **3 or more** architectural options (instead of the default 2), use N-per-entity fan-out for the critique — dispatch one Opus challenger per option, each focused on stress-testing one option independently. Synthesis collates challenger findings before user presentation. See `n_per_entity_fanout.md` (memory) for the trigger criteria and cost model. With 2 options the single-advisor critique is fine; the fan-out only pays off when each option warrants its own deep critique.

---

## Step 2.5: Offer Visual Mockup (UI Features)

If the feature includes a visual/UI component, ask the user before proceeding:

> "Would you like to see a mockup or diagram before I start building?"

If yes: create a standalone HTML mockup (write to `/tmp/`) showing the proposed UI layout, interactions, and visual design. Use the project's design system colors and patterns. Present for feedback before moving to Step 3.

If no: proceed directly to Step 3.

**Why this matters:** Validating visual design before writing code prevents wasted effort when the UX direction is wrong. A 10-minute mockup can save hours of rework.

---

## Step 3: Present to User

Present both options (post-advisor-refinement) to the user with the advisor's analysis included:
- The two options with trade-offs
- Advisor's critique and any identified risks
- Advisor's recommendation (if any)

```
◆ USER CHOOSES architecture (A, B, or hybrid) ◆
```

**State transition:** Write `artifacts.architecture_doc` with approach/files_to_create/files_to_modify/trade_offs, then proceed to Step 4 (plan writing).

---

## Step 4: Write Implementation Plan

After user chooses, write a structured plan using the `writing-plans` skill:
- Numbered steps with specific files and changes
- Test requirements per step
- Dependencies between steps marked clearly

---

## Step 5: Advisor — Plan Stress-Test

### Advisor: Plan Stress-Test

Dispatch Opus (`model: "opus"`, `subagent_type: "general-purpose"`) with:
- Input: `$plan` + `$requirements`
- Question: "Logic errors, missing edges, integration risks, scope creep, reordering needed?"
- Add: "Think step by step before responding."
- Triage: CRITICAL (must fix) / HIGH (should fix) / MEDIUM (note) / LOW (informational)
- Revise plan for HIGH+ findings. Present to user.

### Step 5b: Conditional Re-Grade (only if iter-1 revision was substantive)

**Gate:** skip this step unless Step 5 surfaced ≥1 CRITICAL or ≥2 HIGH findings AND the plan was materially rewritten (not just annotated).

When the gate fires, dispatch one more Opus pass on the revised plan:
- Input: revised `$plan` (post-Step-5 edits)
- Question: "Did the revisions introduce new risks, or leave the original HIGH/CRITICAL issues unresolved? One-pass verdict: PASS / REVISE-AGAIN / ABANDON."
- No new triage categories — the output is one of three verdicts.

If `PASS` → proceed to user approval. If `REVISE-AGAIN` → one more edit pass, then proceed regardless (don't loop). If `ABANDON` → surface to user; the plan may need requirements rework.

**Why gated:** Phase 4 already has two advisor calls (Step 2 + Step 5). An unconditional third pass duplicates work and violates `advisor_prompt_compression` (one-line question, contract reference only). The gate ensures the third pass only fires when substantive rewrites risk introducing *new* problems — which is exactly when a fresh read adds signal.

**Why rejected:** The 8-question rubric import from vercel-labs/open-agents (see `memory/abandoned_phase4_advisor_rubric.md`). This design is the lightweight alternative — single one-line question, hard gate, no rubric.

---

## Step 6: Visual Checkpoint (guarded)

Optional UI-mockup loop that runs after `$plan` is finalized and before the user approval gate. Lets the user edit a concrete drawing rather than a prose description — drift between the edited mockup and `$plan` is then folded back into the plan.

**Guard — run this step only if ALL apply:**
- One of the following signals is present:
  - `--visual` flag on the workflow invocation
  - Task description contains "UI mockup", "visual review", "wireframe", or "mockup"
  - `$plan` touches frontend files (`*.html`, `*.jsx`, `*.tsx`, `*.vue`, `*.svelte`, template dirs, or CSS files)
- `$plan` has user-facing UI surface area (new screens, modified layouts, new components)

**Skip branch — exit this step immediately if:**
- Backend-only feature (no frontend files in `$plan`'s files_to_create / files_to_modify)
- Task is a refactor, migration, or infra change with no visible UI delta
- User explicitly set `--no-visual`

### Substeps (when guard passes)

1. **Load skill.** Read `skills/excalidraw-canvas/SKILL.md` — it routes to `references/excalidraw-schema.md` (JSON subset), `references/mockup-prompts.md` (generation + drift-detection prompts), and `skills/claude-flow/contracts/mockup-manifest.schema.md` (state-matrix manifest).

2. **Refactor-path extract (conditional).** If `$requirements.task_type == "refactor"` AND `$requirements.target_url` is set, seed the `default` state from the live page before generating other states:
   ```
   python skills/claude-flow/scripts/extract_mockup.py \
       --url <target_url> \
       --output docs/design/<feature>/mockups/<screen>__default.excalidraw
   ```
   If the script returns a skip envelope (Playwright missing, URL unreachable) or writes a visibly lossy output (empty, single-box flattening), discard the extract and fall back to blank-canvas generation — note the fallback in the Phase 4 output. Greenfield (non-refactor) tasks skip this substep.

3. **Generate state-matrix mockups.** Using the generation prompt from `skills/excalidraw-canvas/references/mockup-prompts.md`, synthesize one `.excalidraw` file per (screen, state) tuple. Required-state sets per screen type are listed in `skills/claude-flow/contracts/mockup-manifest.schema.md`. Paths follow `docs/design/<feature>/mockups/<screen-slug>__<state>.excalidraw`. Feature slug comes from the branch name or `$requirements.feature_slug`.

4. **Emit manifest.** After all state mockups for the feature are written, emit `docs/design/<feature>/mockup-manifest.json` per the schema in `skills/claude-flow/contracts/mockup-manifest.schema.md`. Every state entry must point to an existing `.excalidraw` file — a manifest that references a missing file is a HIGH-severity finding at the Phase 5 visual-verify gate.

5. **Print open commands.** For each generated file, print:
   ```
   scripts/open_excalidraw.sh docs/design/<feature>/mockups/<screen-slug>__<state>.excalidraw
   ```
   Show the user the list of files written and remind them VS Code opens in an Excalidraw tab if the extension is installed; otherwise the script falls back to excalidraw.com.

6. **Pause for user edits.** Prompt: "Edit the mockup(s) directly, then reply `continue` when done — or `skip` to proceed without re-reading." Do not touch the files during the pause.

7. **Drift detection.** On `continue`, re-read each edited `.excalidraw` and diff against the generator's original output. Use the drift-detection prompt from `skills/excalidraw-canvas/references/mockup-prompts.md` to convert visual deltas into `$plan` deltas (new components, renamed fields, removed screens, etc.). Apply deltas inline to `$plan` and note them in a "Visual-driven plan changes" callout for the user approval gate. If no drift, note "Mockup approved as-is" and continue. If states were added or removed during editing, update `mockup-manifest.json` to match.

### Always-emit architecture diagram (runs regardless of guard)

Independent of `--visual` and independent of the guard above: if `$plan` has a `diagrams` or `component_map` section, emit a one-way (no re-read) `docs/design/<feature>/architecture.excalidraw` summarizing modules, data flow, and dependencies. This runs even for backend-only features so the plan has a visual record; it does NOT pause for user edits. Skip only if `$plan` has no diagrams/component_map content to represent.

**Output:** Updated `$plan` (if drift detected), plus `.excalidraw` files under `docs/design/<feature>/`. Do not block the User Approval Gate on mockup perfection — the user sees the revised `$plan` at the next gate and can still reject.

---

## User Approval Gate

```
◆ USER APPROVES final plan (post-advisor-review) before implementation ◆
```

**State transition:** Write `artifacts.implementation_plan` with steps array, then transition to phase-4d (full path) or phase-5 (lite path).

---

**Output:** Populate `$plan` contract (see `contracts/plan.schema.md`). User must approve before implementation.
