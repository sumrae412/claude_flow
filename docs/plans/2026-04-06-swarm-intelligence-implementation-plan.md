# Swarm Intelligence Workflow Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add layered emergence (swarm intelligence) to code-creation-workflow with tiered complexity, Bayesian agent registry, inter-agent communication, and persistent telemetry.

**Architecture:** Extend SKILL.md + references/ with tiered protocols. Add Python registry module. Modify smart-exploration for registry integration.

**Design doc:** `docs/plans/2026-04-06-swarm-intelligence-workflow-design.md` — source of truth for all schemas, protocols, and decisions. Reference it; don't re-specify.

---

## Dependency Graph

```
Task 1: Registry module (Python + tests)         ← foundation, no deps
Task 2: Reference files (all protocols in 2 files) ← no deps
Task 3: SKILL.md rewrite (all phases)             ← depends on 1, 2
Task 4: Smart-exploration registry integration     ← depends on 1
Task 5: Supporting files + validation              ← depends on 3, 4
```

Parallelizable: Tasks 1 + 2 (independent). Then 3 + 4 (independent). Then 5.

---

## Task 1: Registry Module

**Files:**
- Create: `~/.claude/skills/code-creation-workflow/scripts/registry.py`
- Create: `~/.claude/skills/code-creation-workflow/scripts/test_registry.py`

TDD. The registry module provides all operations the SKILL.md protocols reference: Bayesian updates, effectiveness scoring, prior blending, fingerprint similarity, event compaction, decay, dispatch decisions.

**Step 1: Write tests for core functions**

Test these functions (see design doc Section 6 for exact behavior):
- `bayesian_update(prior, success)` — alpha/beta increment
- `compute_effectiveness(prior)` — alpha / (alpha + beta)
- `blend_priors(project_agent, global_agent)` — 0.7/0.3 below 5 dispatches, pure project at 15+
- `fingerprint_similarity(a, b)` — Jaccard on flattened tags including boolean fields
- `apply_decay(agent, factor)` — multiply with floor at 1.0
- `dispatch_decision(effectiveness, confidence)` — threshold logic: >0.3 dispatch, <0.1+high confidence skip, 0.1-0.3+high confidence reduced budget

Test the `Registry` class:
- `init()` creates global + project registry files from schema
- `record_event()` appends to JSONL
- `compact()` applies events to registry, truncates event file, creates entries for unknown agents
- `get_effectiveness(agent)` blends project + global priors

**Step 2: Run tests, verify fail**

Run: `cd ~/.claude/skills/code-creation-workflow/scripts && python -m pytest test_registry.py -v`

**Step 3: Implement registry.py to pass all tests**

Schema definitions live in the design doc. The module imports nothing beyond stdlib (json, os, pathlib, datetime). Keep it under 200 lines.

**Step 4: Run tests, verify pass**

**Step 5: Commit**

```bash
git commit -m "feat(swarm): registry module with Bayesian updates and event compaction"
```

---

## Task 2: Reference Files

**Files:**
- Create: `~/.claude/skills/code-creation-workflow/references/swarm-schemas.md`
- Create: `~/.claude/skills/code-creation-workflow/references/swarm-protocols.md`

Two files, not seven. Schemas in one, protocols in the other.

**Step 1: Write swarm-schemas.md**

All JSON schemas from design doc Section 6 in one file:
- Global registry, project overlay, exploration log, missed-context log
- Scratchpad, build-state, review-findings (ephemeral)
- Registry events (JSONL format + event type table)
- Complexity calibration history entry
- Gitignore guidance (which files committed vs ignored)
- Schema versioning protocol

This is the single source of truth for data shapes. SKILL.md and registry.py both reference this file instead of re-specifying schemas.

**Step 2: Write swarm-protocols.md**

All operational protocols consolidated into sections:

```markdown
# Swarm Protocols

## 1. Complexity Classifier
  Static scoring (4 axes table), degradation probe, registry feedback, user override.
  (From design Section 1)

## 2. Exploration Scratchpad
  Staggered dispatch, write/read protocol, prompt templates for Explorer B/C, lifecycle.
  (From design Section 2 complex tier)

## 3. Adversarial Architecture
  Gap detection scan, gap-fill dispatch, critic rebuttal prompts, synthesis judge prompt.
  (From design Section 3 complex tier)

## 4. Build-State
  Per-step write protocol, failed-approach propagation, parallel merge, full context chain.
  (From design Section 4 complex tier)

## 5. Agent Signals
  Four signal types + schemas, orchestrator processing, deviation detection, collaborative rescue.
  (From design Section 4)

## 6. Staged Review
  Wave 1/2/3 protocol, meta-reviewer tasks, cross-reference prompt templates.
  (From design Section 5 complex tier)

## 7. Missed-Context Audit
  When to run, audit steps, miss types, sources to check, severity, feedback paths.
  (From design Section 2/3/4/5 — consolidated)

## 8. Periodic Review
  Trigger conditions, 5 analysis dimensions, output→action mapping, retention policy.
  (From design Section 6)
```

Each section is concise operational instructions (not re-explanation of design rationale). Reference the design doc for "why." These protocols say "how."

**Step 3: Commit**

```bash
git commit -m "feat(swarm): add schema and protocol reference files"
```

---

## Task 3: SKILL.md Rewrite

**Files:**
- Modify: `~/.claude/skills/code-creation-workflow/SKILL.md`

One pass through the file, updating all phases. Do not re-read between edits.

**Step 1: Add tier concept to the top of the file**

After the Model Strategy table, add a "Swarm Tiers" section explaining the moderate/complex distinction and referencing `swarm-protocols.md#1-complexity-classifier`.

**Step 2: Update Phase 1 — add complexity classification**

After the existing fast-path decision tree, add the classifier step. Reference `swarm-protocols.md#1-complexity-classifier`. The tier result propagates to all subsequent phases.

**Step 3: Update Phase 2 — tiered exploration**

Replace "Launch Explorers" with two subsections (moderate / complex).

Moderate: registry-informed variant selection (query `registry.py`, rank by findings-used rate, dispatch top 2).

Complex: staggered dispatch with scratchpad. Reference `swarm-protocols.md#2-exploration-scratchpad`. Add missed-context audit call after each explorer. Reference `swarm-protocols.md#7-missed-context-audit`.

Context hydration section: unchanged, but add persistence step (write exploration-log).

**Step 4: Update Phase 4 — tiered architecture**

Moderate: all architects receive scratchpad + gap chain. Registry-weighted synthesis.

Complex: add gap detection + Round 2 critics + Round 3 synthesis judge. Reference `swarm-protocols.md#3-adversarial-architecture`.

Add feedback loop: gap detections → exploration log as misses.

**Step 5: Update Phase 5 — tiered implementation**

Moderate: registry-informed thinking budgets. Registry-informed specialist dispatch.

Complex: build-state protocol. Reference `swarm-protocols.md#4-build-state`. Agent signals. Reference `swarm-protocols.md#5-agent-signals`. Architecture deviation detection. Collaborative rescue. Failed-approach propagation.

Update retry loop: add registry check before diagnosis, rescue path, build-state in diagnosis context.

Update parallel dispatch: add build-state snapshot + conflict detection.

**Step 6: Update Phase 6 — tiered review**

Moderate: registry-selective dispatch (HIGH/MODERATE/LOW/UNKNOWN).

Complex: wave protocol with staged findings + meta-reviewer. Reference `swarm-protocols.md#6-staged-review`.

Both: missed-context audit for reviewers. Review → exploration feedback.

**Step 7: Update Quick Reference tables**

- "All Phases" table: add tier column
- "Agents Used" table: add meta-reviewer, gap-fill explorer, rescue agents
- "Error Recovery" table at bottom or in reference: add swarm-specific rows

**Step 8: Add registry event recording throughout**

Scan all dispatch points. Each must include: "Record `dispatched` event to registry." Each finding/outcome must include the corresponding event type. This is a cross-cutting concern — add it to every dispatch instruction, not as a separate section.

**Step 9: Commit**

```bash
git commit -m "feat(swarm): add tiered swarm protocols to all phases"
```

---

## Task 4: Smart-Exploration Registry Integration

**Files:**
- Modify: `~/.claude/skills/smart-exploration/SKILL.md`
- Modify: `~/.claude/skills/smart-exploration/prompt-library.md`

**Step 1: Add registry lookup to SKILL.md**

After "How Phase 2 Uses This Skill," add a section: when registry exists, rank prompt variants by effectiveness before selecting. Fall back to default if no data.

**Step 2: Add variant IDs to prompt-library.md**

Tag each explorer prompt with a `variant_id` (e.g., `endpoint:route-chain`). This is how the registry tracks per-variant effectiveness. One-line addition per prompt.

**Step 3: Commit**

```bash
git commit -m "feat(swarm): integrate registry into smart-exploration"
```

---

## Task 5: Supporting Files + Validation

**Files:**
- Modify: `~/.claude/skills/code-creation-workflow/references/error-recovery.md`
- Modify: `~/.claude/skills/code-creation-workflow/references/common-mistakes.md`
- Modify: `~/.claude/skills/code-creation-workflow/references/red-flags.md`

**Step 1: Add swarm entries to all three files**

error-recovery.md — add rows for: scratchpad failures, gap-fill returns nothing, no registry data, build-state conflicts, meta-reviewer systemic patterns, rescue failures, tier mismatch mid-session, available_in_prompt misses. (8 rows)

common-mistakes.md — add rows for: dispatching Explorer B before A writes scratchpad, skipping gap detection, not recording registry events, ignoring agent signals, running full swarm on moderate tasks, skipping missed-context audit. (6 rows)

red-flags.md — add rows for: "Registry doesn't have enough data," "Scratchpad is overkill," "I'll merge findings manually." (3 rows)

**Step 2: Structural validation**

Verify all cross-references in SKILL.md resolve to existing files:

```bash
grep -oP 'references/[a-z-]+\.md' ~/.claude/skills/code-creation-workflow/SKILL.md | sort -u | while read f; do
  test -f ~/.claude/skills/code-creation-workflow/$f && echo "OK: $f" || echo "MISSING: $f"
done
```

Verify registry.py tests pass:

```bash
cd ~/.claude/skills/code-creation-workflow/scripts && python -m pytest test_registry.py -v
```

**Step 3: Commit**

```bash
git commit -m "feat(swarm): update supporting files and validate integration"
```
