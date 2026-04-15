---
name: claude-flow
description: Use when creating new features, implementing complex changes, or executing implementation plans. Agentic workflow with fast, clone, lite, explore, and full paths. Executor/Advisor strategy — Sonnet executes, Opus advises at key decision points.
user-invocable: true
---

# Code Creation Workflow

Agentic multi-phase workflow for building features. **Executor/Advisor strategy:** Sonnet executor runs the main loop (exploring, drafting, implementing). Opus advisor fires on-demand at 3-5 decision points. Project-agnostic — works for any codebase or greenfield project.

**Announce:** "Running claude-flow — loading context, exploring codebase, then building with you."

---

## Model Assignments

| Role | Model | When |
|------|-------|------|
| **Executor** | **sonnet** | Every turn — exploration, drafting, implementation, all file I/O |
| **Advisor (tiered)** | **sonnet** Phase 2, **opus** Phase 4 | Sonnet for gap-finding, Opus for architecture + plan critique |
| **Lightweight reviewer** | **haiku** | Phase 6 — single batched dispatch (types, API docs, invariants, defensive) |
| **Specialist reviewers** | **sonnet** | Phase 6 — safety (combined), test coverage |

---

## How to Use This Workflow

1. **This file** (router) is always resident (~2.5K tokens)
2. **Load `contracts/*.schema.md`** at start — always resident (~800 tokens total)
3. **On entering each phase:** load `phases/phase-N-*.md` via Read tool
4. **On completing each phase:** the phase file can be dropped — the populated contract (`$exploration`, `$requirements`, `$plan`, `$diff`) carries forward at 1/10th the size
5. **Reference files** in `references/` are lazy-loaded only when a phase needs them
6. **Architecture diagrams** in `diagrams/*.mmd` are lazy-loaded — read when reasoning about path selection (`triage-paths.mmd`), token budget behavior (`phase-lifecycle.mmd`), or contract data flow (`contract-flow.mmd`). Not resident.

---

## Flags

Optional flags modify specific phases without changing the path decision.

**Two flag scopes:**
- **Path-scoped** flags pick the whole workflow path — e.g. `--fast`, `--lite`, `--clone`, `--explore`, `--full`. These interact with Phase 1 triage (see Path Decision below) and typically skip later phases entirely.
- **Phase-scoped** flags modify one phase's behavior without changing the path — e.g. `--visual` / `--no-visual` below. Path selection is unaffected; only the named phase runs differently. New phase-scoped flags should name the phase in the `Phase` column of this table so the scope stays obvious.

| Flag | Phase | Effect |
|------|-------|--------|
| `--visual` | Phase 4 | Force the Visual Checkpoint step (Step 6): generate `.excalidraw` mockups under `docs/design/<feature>/mockups/`, pause for user edits, fold drift back into `$plan`. Auto-enabled when `$plan` touches frontend files or the task mentions "UI mockup" / "wireframe" / "visual review". |
| `--no-visual` | Phase 4 | Skip the Visual Checkpoint step even when auto-enable signals fire. The always-emit `architecture.excalidraw` (one-way) still runs. |

---

## Path Decision (Phase 1 Core Logic)

```
BUG? (error report, regression, stack trace, "fix this bug")
  → Invoke /bug-fix skill — EXIT workflow

SMALL? (single file, no schema, no new endpoints)
  → FAST PATH: make change → test → commit → EXIT

HAS PLAN/PRP? (existing plan file or PRP document)
  → PLAN PATH: read plan → skip to Phase 5

NEAR-IDENTICAL FEATURE? (2-3 grep/glob checks)
  → CLONE PATH: clone + adapt → Phase 6 review

1-2 FILES? (no new endpoints, no schema, no new models)
  → LITE PATH: Phases 2-6 with inline architecture

EXPLORATORY? ("try this", "spike", "prototype", "proof of concept")
  → EXPLORE PATH: sandbox (60/100 bar, no TDD, no Phase 6)
    Graduate → full workflow from Phase 4
    Archive → /session-handoff --abandon

ELSE → FULL WORKFLOW (all phases)
```

Load `phases/phase-1-discovery.md` for full path criteria and artifact requirements table.

---

## Phase Transition Map

| From → To | Condition |
|-----------|-----------|
| phase-0 → phase-0.5 | No hooks.json exists |
| phase-0 → phase-1 | hooks.json exists |
| phase-0.5 → phase-1 | Always |
| phase-1 → EXIT | Fast path |
| phase-1 → phase-2 | Full or lite path |
| phase-1 → phase-5 | Clone or plan path |
| phase-2 → phase-3 | Always |
| phase-3 → phase-4 | Always |
| phase-4 (includes plan stress-test) → phase-4d | Full path only |
| phase-4 (includes plan stress-test) → phase-5 | Lite path |
| phase-4d → phase-5 | Always |
| phase-5 → phase-5 | Retry: tests/lint failed, iteration < 3 |
| phase-5 → phase-6 | Tests + lint pass |
| phase-6 → phase-5 | High/critical findings, iteration < 2 |
| phase-6 → COMPLETE | No high/critical findings |

**Iteration limits:** Phase 5: max 3 (then surface to user). Phase 6: max 2 (then ship with known issues). All others: forward only.

---

## Phase Output Contracts

| Contract | Schema File | Produced By | Consumed By |
|----------|-------------|-------------|-------------|
| `$exploration` | `contracts/exploration.schema.md` | Phase 2 | Phases 3, 4, advisors |
| `$requirements` | `contracts/requirements.schema.md` | Phase 3 | Phases 4, 4c, 5, 6 |
| `$plan` | `contracts/plan.schema.md` | Phase 4b | Phases 4c, 4d, 5, 6 |
| `$diff` | `contracts/diff.schema.md` | Phase 5 | Phase 6 |

Contracts are the interface between phases. When dispatching subagents, pass the named contract — not raw conversation. See each schema file for field definitions and notes.

**Never pass to subagents:** advisor transcripts, rejected architecture details, Phase 0 skill loading decisions, raw clarification Q&A (pass `$requirements` instead).

**Authoring-time verification:** Phase 3 audits self-answerable questions; Phase 5 injects deterministic lookups (alembic, routes, columns, CSS, React) and runs a visual-drift gate. Optional deps graceful-skip — never block the workflow. See concept: `knowledge/concepts/authoring-time-verification.md`.

---

## Quick Reference

| Phase | Name | Model | Key Pattern | Gate |
|-------|------|-------|-------------|------|
| 0 | Context | executor | Trigger matrix → load relevant skills only | None |
| 1 | Discovery | executor | 7-path triage (bug/fast/clone/plan/lite/explore/full) | Auto |
| 2 | Exploration | executor + **sonnet advisor** | Executor explores → advisor reviews gaps + scores quality gate | Advisor confirms |
| 3 | Requirements | executor | Ambiguities + $requirements (quality gate skipped if Phase 2 passed) | User approves |
| 4 | Architecture + Plan | executor + **opus advisor** | 2 options → advisor critiques → plan → advisor stress-tests | User approves plan |
| 5 | Implementation | executor (+ advisor optional) | TDD per step, defensive patterns, parallel dispatch | Tests + lint pass |
| 5.5 | Reflection | executor | RARV self-check before expensive reviews | Auto |
| 6 | Quality + Finish | sonnet/haiku | Cascading 5-tier review → verify → commit → retrospective | Verification |

---

## Error Recovery

| Situation | Action |
|-----------|--------|
| Exploration misses key area | Re-explore; call advisor again with new findings |
| Advisor identifies critical gap | Investigate the gap before proceeding |
| Architecture options both rejected | Ask user for different constraints, executor re-drafts |
| Tests fail during implementation | Fix immediately, don't proceed to next step |
| Reviewer finds critical issue | Fix → re-run that specific reviewer → max 3x → escalate |
| User wants to stop | Stop. Summarize state (phase, done, remaining). |
| Wrong architecture chosen | Revert to plan, re-architect with new constraints |

---

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Skipping Phase 0 context loading | Always load project context first |
| Exploring without checking prior knowledge | Step 0: check MEMORY.md, PRPs, Serena before exploring |
| Skipping Phase 4c plan verification | Plans reference Phase 2 findings — codebase can drift |
| Jumping to fixes without evidence | Use `/investigator` for complex TDD failures |
| Calling advisor every turn | 2-4 calls per workflow, not every step |
| Using Opus for Phase 2 exploration review | Sonnet handles gap-finding; Opus reserved for Phase 4 |
| Running all Phase 6 tiers when Tier 1 is clean | Early exit: if CodeRabbit finds no HIGH+ issues, skip Tiers 2-4 |
| Dispatching 4 separate haiku reviewers | Batch into single `lightweight-reviewer` with combined checklist |
| Initializing state machine for fast/lite paths | Skip — single-session linear flows don't need cross-session resume |
| Re-running Phase 3 quality gate when Phase 2 scored it | Carry scores forward — skip redundant re-check |
| Coding before clarification | Phase 3 is a hard gate |
| Single architecture proposal | Always present 2 options |
| Passing full conversation to subagents | Use named contracts ($plan, $requirements, etc.) |
| Using full workflow for 1-2 file changes | Use Lite path |
| Writing tests after code | TDD — test first |
| Guessing external API patterns | Hard gate: `/fetch-api-docs` before any API code |
| Not tagging workflow failures | Apply taxonomy tags (see `references/failure-taxonomy.md`) |
| Letting context grow unbounded | Tool-result clearing at ~50K, compaction at ~80% |
| Running 10-step plans without context breaks | Fresh context for subagents at 5+ steps |
| Running silent-failure-hunter and security-reviewer separately | Use merged `safety-reviewer` (Tier 2) — they're consolidated |
