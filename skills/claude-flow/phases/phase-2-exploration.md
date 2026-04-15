# Phase 2: Exploration (Executor + Advisor)

<!-- Loaded: after Phase 1 (full/lite path) | Dropped: after transition to Phase 3 -->
<!-- Output: $exploration contract -->

The **executor (Sonnet)** explores the codebase directly — reading files, tracing patterns, mapping architecture. No parallel explorer subagents. The executor builds firsthand context that persists naturally through Phases 3-5, eliminating any context hydration gate.

**Greenfield projects:** If there is no existing codebase, skip Phase 2 exploration entirely — go straight to Phase 3 clarification and then Phase 4 architecture. There are no files to explore or patterns to discover.

---

## Research Team Branch (Full/Complex Path Only)

When the task path is `full` or `complex` (set in Phase 1 Discovery):

1. **Run Step 0** (Prior Knowledge Check) — still runs; prior knowledge reduces redundant research
2. **Invoke `/research` skill** with the task description as the research question (plus any prior knowledge found in Step 0)
3. The research skill runs its full pipeline (classify → Wave 1 → gap detection → Wave 2 → synthesize)
4. **Receive the research brief** — this replaces the exploration output from Steps 1-2
5. **Skip to Step 3** (Advisor Checkpoint) — the Opus advisor reviews the research brief instead of raw exploration findings
6. The research brief's confidence scores are included in the `$exploration` variable

When the task path is `lite` or `fast`, the single-executor exploration (Steps 0-2 below) runs unchanged.

> **Why branch here:** Research adds depth, breadth, and quality verification — but costs 3-6 agent round-trips. Lite/fast tasks don't need this overhead. The branch respects the existing path classification without replacing what works for simpler tasks.

### Wave 1 dispatch shape: task-typed vs. N-per-entity

The `/research` skill defaults to **task-typed** Wave 1 — 2-4 researchers covering different dimensions (backend, frontend, prior art, external API). When the research question is "compare these N alternatives" rather than "explore this feature area," switch to **N-per-entity fan-out**: dispatch one researcher per candidate library/approach, each running the same evaluation checklist. See `n_per_entity_fanout.md` (memory) for the full decision matrix. Triggers for the entity-typed shape:
- Question explicitly compares ≥4 named alternatives ("OAuth providers: Auth0 vs Clerk vs Supabase Auth vs WorkOS")
- $requirements lists multiple candidate technologies and asks for a recommendation
- Prior exploration produced ≥4 viable approaches and the architect needs each evaluated independently

---

## Step 0: Prior Knowledge Check (Token Saver)

Before exploring from scratch, check what's already known about this feature area. Prior sessions may have already mapped the relevant architecture, patterns, and integration points.

```
1. MEMORY CHECK
   → Read MEMORY.md index for relevant entries
   → If any match the feature area, read the memory files
   → Extract: key files, patterns, conventions, gotchas

2. PRP CHECK
   → Glob for plans/PRP-*.md files related to this feature
   → If a PRP exists, it contains curated codebase intelligence
     from a prior session's exploration (key files, patterns,
     integration points, constraints)
   → A PRP can replace most of Step 2 exploration

3. SERENA MEMORY CHECK (if Serena is active)
   → read_memory for the feature area
   → Prior sessions may have persisted symbol mappings,
     architectural notes, or decision rationale

4. SESSION-LEARNINGS CHECK
   → Grep MEMORY.md for learnings from prior work in
     the same feature area
   → Prior corrections, validated patterns, and gotchas
     are more valuable than fresh exploration

5. WORKFLOW TRACE CHECK
   → Grep MEMORY.md for workflow failure tags from prior runs
     on similar feature types
   → If prior runs flagged `exploration-gap` for this area,
     allocate extra exploration passes
   → If prior runs flagged `review-escape`, add the escaped
     pattern to the Phase 6 review prompt
   → Prior workflow failures are the eval signal — use them
     to calibrate this run's effort allocation
```

**Outcome:**
- **Rich prior knowledge exists** → Skip or reduce Step 2 exploration. Go straight to Step 3 advisor checkpoint with prior findings, asking "Is this still accurate? What's changed?"
- **Partial prior knowledge** → Focus Step 2 exploration on gaps only. Don't re-explore what's already known.
- **No prior knowledge** → Proceed to Step 1 normally.

**Why this matters:** Re-exploring a codebase you've already mapped burns tokens for zero new information. A 30-second memory check can save 5-10 minutes of redundant file reads. Over multiple sessions on the same project, the savings compound — each session builds on prior knowledge instead of starting cold.

---

## Step 1: Compressed Codebase Context (Token Saver)

Generate token-efficient codebase maps before deep exploration:

```bash
# Signatures only — function/class headers without bodies
python scripts/generate_repo_outline.py app/services/ --max-depth 2

# Full compressed context — entire codebase packed into minimal tokens
repomix --compress --output .repomix-output.txt
```

For small/familiar codebases, `generate_repo_outline.py` alone is sufficient. For large or unfamiliar codebases, always run both.

---

## Step 2: Executor Explores Directly

The executor (main session, Sonnet) explores the codebase in 3 focused passes:

```
Pass 1: SIMILAR FEATURES
  → Trace how analogous features are implemented
  → Read 3-5 files showing the established pattern
  → Note: data flow, naming conventions, error handling

Pass 2: FEATURE AREA ARCHITECTURE
  → Map the layers this feature will touch
  → Read key files at each layer (route → service → model)
  → Note: integration points, shared utilities, constraints

Pass 3: TEST + UI PATTERNS (if relevant)
  → Read existing test files for the area
  → Read UI templates/components if UI work is involved
  → Note: test setup patterns, fixture usage, rendering conventions
```

**Minimum output:** 8-15 key files read firsthand, patterns documented, concerns identified.

**Serena integration:** Use `find_symbol` / `find_referencing_symbols` instead of grep chains. Use `write_memory` to persist discoveries for cross-session continuity.

---

## Step 3: Advisor Checkpoint — Exploration Review

### Advisor: Exploration Review

Dispatch **Sonnet** (`model: "sonnet"`, `subagent_type: "general-purpose"`) with:
- Input: populated `$exploration` contract (key_files, patterns, integration_points, concerns)
- Question: "What's missing from this exploration before I move to requirements? Also score these 4 quality axes as pass/fail: (1) Objective Clarity — deliverable stateable as one-sentence outcome? (2) Service Scope — affected files/modules identifiable? (3) Testability — all behaviors expressible as WHEN/THEN? (4) Completeness — all edge cases from exploration have resolutions?"
- If research brief was produced: include full brief with confidence scores instead of raw exploration
- Act on response: explore identified gaps. If all 4 quality axes pass, carry scores forward to Phase 3 (skip quality gate re-check). If any fail, Phase 3 will re-score after ambiguity resolution.

**Why Sonnet, not Opus:** Exploration review is gap-finding and checklist scoring — broad pattern matching, not deep trade-off analysis. Opus is reserved for Phase 4 architecture critique and plan stress-test where it earns its cost.

---

## Phase 2 Step Labels

| Step | Label (standard path) | Label (research team path) |
|------|----------------------|---------------------------|
| 1 | Prior knowledge check | Prior knowledge check |
| 2 | Compressed codebase context | Task classification |
| 3 | Executor explores directly | Wave 1 dispatch |
| 4 | Advisor checkpoint | Gap detection |
| 5 | — | Wave 2 dispatch (if needed) |
| 6 | — | Synthesis |
| 7 | — | Advisor checkpoint |

When the research team is active, update `agents_spawned`, `agents_completed`, and `agents_failed` in the workflow state as researchers are dispatched and return. The existing state schema supports this — no schema changes needed.

---

## State Transition

Write `artifacts.exploration_summary` with `key_files` / `patterns` / `integration_points` / `gaps`, then transition to Phase 3.

**Output:** Populate `$exploration` contract (see `contracts/exploration.schema.md`). This artifact persists after this phase file is unloaded.
