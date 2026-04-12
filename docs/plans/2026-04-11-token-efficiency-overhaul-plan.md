# Token Efficiency Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Split the 24K-token code-creation-workflow SKILL.md monolith into a thin router + per-phase files + structured contracts, with compressed advisor prompts and reviewer consolidation.

**Architecture:** Progressive disclosure — SKILL.md becomes a ~2.5K router that loads phase files on demand. Structured YAML-schema contracts replace prose handoffs between phases. Advisor templates compressed to contract references + 1-line questions.

**Tech Stack:** Markdown skill files, YAML schemas in markdown fences

---

### Task 1: Create Contract Schema Files (shared_prerequisite)

These are consumed by every phase file downstream, so they must exist first.

**Files:**
- Create: `skills/code-creation-workflow/contracts/exploration.schema.md`
- Create: `skills/code-creation-workflow/contracts/requirements.schema.md`
- Create: `skills/code-creation-workflow/contracts/plan.schema.md`
- Create: `skills/code-creation-workflow/contracts/diff.schema.md`

**Step 1: Create exploration.schema.md**

```markdown
# $exploration
<!-- Produced by: Phase 2 | Consumed by: Phases 3, 4, advisor prompts -->

## Schema

key_files:
  - path: string        # file path
    role: string        # 1-line role (e.g., "tenant CRUD service")

patterns:               # 3-5 discovered conventions
  - name: string
    example_file: string

integration_points:     # systems this feature touches
  - system: string
    interface: string   # function/endpoint name

concerns: string[]      # open questions for Phase 3

confidence: verified | inferred | assumed   # from research team if used

## Notes

- Populated by executor at end of Phase 2
- For full/complex path with research team: confidence scores come from synthesis
- Persists after phase-2-exploration.md is unloaded — this is the surviving artifact
- Target size: 100-200 tokens when populated
```

**Step 2: Create requirements.schema.md**

```markdown
# $requirements
<!-- Produced by: Phase 3 | Consumed by: Phases 4, 4c, 5, 6 reviewers -->

## Schema

stories:
  - role: string
    want: string
    benefit: string

acceptance_criteria:    # EARS format — these become the Phase 4c coverage checklist
  - id: AC-N
    when: string
    if: string          # optional condition
    then: string

scope:
  in: string[]          # explicitly included
  out: string[]         # explicitly excluded — enforced as scope-creep detection

edge_cases:
  - case: string
    resolution: string

nonfunctional:          # optional
  - type: string        # performance | backward_compat | security
    constraint: string

## Notes

- Populated after user approves requirements in Phase 3
- acceptance_criteria is the primary input for Phase 4c coverage mapping
- scope.out items are enforced in Phase 4c as scope-creep detection
- Phase 6 reviewers receive only acceptance_criteria (not full contract) for payload slimming
```

**Step 3: Create plan.schema.md**

```markdown
# $plan
<!-- Produced by: Phase 4b | Consumed by: Phases 4c, 4d, 5, 6 reviewers -->

## Schema

steps:
  - id: N
    description: string
    files: string[]       # exact paths to create/modify
    type: value_unit | shared_prerequisite | adr
    depends_on:
      - step: N
        type: data | build | knowledge
    test_requirements: string
    status: pending | complete

## Notes

- Populated after user approves plan in Phase 4b (post-advisor stress-test)
- Phase 4c verifies file paths and function references against codebase
- Phase 5 dispatches based on dependency types: data/build = sequential, knowledge = parallelizable
- Phase 6 reviewers receive only step id + files list (not full descriptions) for payload slimming
- status updated during Phase 5 as steps complete
```

**Step 4: Create diff.schema.md**

```markdown
# $diff
<!-- Produced by: Phase 5 | Consumed by: Phase 6 reviewers -->

## Schema

files_changed: string[]
insertions: number
deletions: number
git_diff: string          # full diff (unavoidable — reviewers need real content)

## Notes

- Generated at end of Phase 5 via `git diff main --stat` + `git diff main`
- git_diff is the primary reviewer input — cannot be compressed
- files_changed used for conditional reviewer triggers (Tier 3 file_patterns matching)
- insertions + deletions used for code-simplifier skip condition (<100 lines = skip)
```

**Step 5: Verify all 4 files exist**

Run: `ls skills/code-creation-workflow/contracts/`
Expected: `diff.schema.md  exploration.schema.md  plan.schema.md  requirements.schema.md`

**Step 6: Commit**

```bash
git add skills/code-creation-workflow/contracts/
git commit -m "feat(workflow): add structured phase contract schemas

Four YAML-schema contracts ($exploration, $requirements, $plan, $diff)
that define the interface between phases. Replaces prose handoff
descriptions with compact, typed schemas."
```

---

### Task 2: Extract Failure Taxonomy + Agent Registry to References (shared_prerequisite)

Move content OUT of the monolith into lazy-loaded reference files before the split.

**Files:**
- Create: `skills/code-creation-workflow/references/failure-taxonomy.md`
- Create: `skills/code-creation-workflow/references/agent-registry.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 1792-1845 (failure taxonomy + common mistakes source)
- Read: `skills/code-creation-workflow/SKILL.md` lines 1707-1778 (agents/skills/tools/eliminated tables)

**Step 1: Create failure-taxonomy.md**

Extract the Workflow Failure Taxonomy table (SKILL.md lines 1792-1810) into `references/failure-taxonomy.md`. Include the tag table verbatim — these tags are referenced by Phase 6 retrospective.

**Step 2: Create agent-registry.md**

Extract these sections from SKILL.md into `references/agent-registry.md`:
- "Agents Used Within This Workflow" (lines 1707-1738) — advisor + review agent tables
- "Skills Invoked Within This Workflow" (lines 1740-1756)
- "Static Analysis & Context Tools" (lines 1758-1766)
- "Skills Eliminated (Absorbed)" (lines 1768-1778)

These are reference documentation, not runtime instructions. They don't need to be loaded into every session.

**Step 3: Verify files exist**

Run: `ls skills/code-creation-workflow/references/failure-taxonomy.md skills/code-creation-workflow/references/agent-registry.md`

**Step 4: Commit**

```bash
git add skills/code-creation-workflow/references/failure-taxonomy.md skills/code-creation-workflow/references/agent-registry.md
git commit -m "refactor(workflow): extract failure taxonomy and agent registry to references

Moves ~1.8K tokens of reference tables out of the monolith into
lazy-loaded files. Failure taxonomy loaded by Phase 6 only; agent
registry is documentation, not runtime."
```

---

### Task 3: Create Phase 0 + Phase 0.5 File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-0-context.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 102-386 (workflow state machine + Phase 0 + Phase 0.5)

**Step 1: Create phases/ directory**

Run: `mkdir -p skills/code-creation-workflow/phases`

**Step 2: Write phase-0-context.md**

Extract and compress these sections from SKILL.md into `phases/phase-0-context.md`:
- Workflow State Machine (lines 106-238): Keep the JSON schema, jq templates, transition map, and cross-session resume logic
- Phase 0 steps (lines 241-335): Steps 0-7 (check existing state, load identity, load core skill, classify task, load enforcement, conditional tools, git check, bootstrap MEMORY.md)
- Phase 0.5 (lines 338-386): Bootstrap project hooks

**Compression targets:**
- Remove the ASCII-art box diagram for state machine (the JSON schema is sufficient)
- Compress the jq examples — keep one transition template, not separate ones for update/complete
- The step descriptions can stay as-is — they're already fairly compact

**Target size:** ~2K tokens

**Step 3: Verify**

Run: `wc -c skills/code-creation-workflow/phases/phase-0-context.md`
Expected: Under 8000 bytes (~2K tokens)

**Step 4: Commit**

```bash
git add skills/code-creation-workflow/phases/
git commit -m "refactor(workflow): extract Phase 0 + 0.5 to phase file

Moves context loading, workflow state machine, hooks bootstrap
into phases/phase-0-context.md (~2K tokens). Loaded on entry,
dropped after transition to Phase 1."
```

---

### Task 4: Create Phase 1 Discovery File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-1-discovery.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 389-490

**Step 1: Write phase-1-discovery.md**

Extract Phase 1 content. Keep:
- The full path decision flowchart (this is the core routing logic)
- Path criteria definitions (bug/fast/clone/explore/lite/full)
- Artifact Requirements by Scale table

**Compression targets:**
- The flowchart ASCII art is essential — keep it
- Path criteria can be slightly compressed (remove redundant explanations)

**Target size:** ~1.5K tokens

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-1-discovery.md
git commit -m "refactor(workflow): extract Phase 1 discovery to phase file"
```

---

### Task 5: Create Phase 2 Exploration File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-2-exploration.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 492-657

**Step 1: Write phase-2-exploration.md**

Extract Phase 2. Keep:
- Research Team Branch routing (full/complex vs lite/fast)
- Step 0: Prior knowledge check (token saver)
- Step 1: Compressed codebase context
- Step 2: Executor explores (3 passes)
- Step 3: Advisor checkpoint — but compress the advisor template

**Advisor compression:** Replace the verbose ~350-token template with:
```
### Advisor: Exploration Review
Dispatch Opus (model: "opus", subagent_type: "general-purpose") with:
- Input: populated $exploration contract
- Question: "What's missing from this exploration before I move to requirements?"
- Act on response: explore gaps, then proceed to Phase 3
```

Keep the research team branch instructions (Wave 1 → gap → Wave 2) but compress the step labels table.

**Target size:** ~2.5K tokens

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-2-exploration.md
git commit -m "refactor(workflow): extract Phase 2 exploration to phase file

Includes compressed advisor template referencing \$exploration contract."
```

---

### Task 6: Create Phase 3 Requirements File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-3-requirements.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 659-791

**Step 1: Write phase-3-requirements.md**

Extract Phase 3. Keep:
- Step 1: Resolve ambiguities (question categories)
- Step 2: Quality gate (4-axis scoring)
- Step 3: Synthesize structured requirements — but reference `$requirements` contract schema instead of inlining the format
- PRP export (optional, trigger conditions)

**Compression:** The $requirements format block (lines 717-740) is replaced with: "Populate the `$requirements` contract (see `contracts/requirements.schema.md`)"

**Target size:** ~2K tokens

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-3-requirements.md
git commit -m "refactor(workflow): extract Phase 3 requirements to phase file

References \$requirements contract schema instead of inlining format."
```

---

### Task 7: Create Phase 4 Architecture File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-4-architecture.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 793-936

**Step 1: Write phase-4-architecture.md**

Extract Phase 4 (architecture) + Phase 4b (plan stress-test). Keep:
- Step 0: Cross-document consistency check
- Step 1: Executor drafts two options (simplicity vs separation)
- Step 2: Advisor — Architecture Critique (compressed template)
- Step 3: Present to user
- Step 4: Write implementation plan (references writing-plans skill)
- Step 5: Advisor — Plan Stress-Test (compressed template)
- Triage levels (CRITICAL/HIGH/MEDIUM/LOW)

**Advisor compression (both checkpoints):**
```
### Advisor: Architecture Critique
Dispatch Opus with $exploration + both option summaries.
Question: "Blind spots? Which trade-offs am I underweighting? Hybrid approach?"
Add: "Think step by step before responding."

### Advisor: Plan Stress-Test
Dispatch Opus with $plan + $requirements.
Question: "Logic errors, missing edges, integration risks, scope creep?"
Add: "Think step by step before responding."
```

**Target size:** ~3K tokens

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-4-architecture.md
git commit -m "refactor(workflow): extract Phase 4 architecture to phase file

Compressed advisor templates for architecture critique and plan stress-test."
```

---

### Task 8: Create Phase 4c + 4d Files (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-4c-verification.md`
- Create: `skills/code-creation-workflow/phases/phase-4d-skeletons.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 938-1066

**Step 1: Write phase-4c-verification.md**

Extract Phase 4c. Keep:
- File path verification logic
- Requirements coverage mapping (references `$requirements` and `$plan` contracts)
- Scope boundary enforcement
- Edge case coverage check
- Task granularity check
- Outcome actions

**Target size:** ~1.5K tokens

**Step 2: Write phase-4d-skeletons.md**

Extract Phase 4d. Keep:
- Skeleton generation logic
- What Phase 5 does with skeletons
- Skip condition (fast/clone/lite)

**Target size:** ~1K tokens

**Step 3: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-4c-verification.md skills/code-creation-workflow/phases/phase-4d-skeletons.md
git commit -m "refactor(workflow): extract Phase 4c verification + 4d skeletons to phase files"
```

---

### Task 9: Create Phase 5 Implementation File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-5-implementation.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 1068-1379 (context management + Phase 5)

**Step 1: Write phase-5-implementation.md**

Extract Phase 5 + Context Management Strategy. Keep:
- Pre-implementation: fetch API docs gate
- TDD execution loop (steps 1-6 including guard regression)
- Parallel subagent dispatch (dependency-aware)
- Conditional specialist reviews (migration/google-api/async)
- Best practices table
- Context management strategies 1-3 (tool-result clearing, phase-aware compaction, phase output contracts)
- Fresh context for long loops
- Advisor: Mid-Implementation (compressed, optional)

**Context management moves here** because it's most relevant during the longest phase. The strategies compose section (lines 1177-1197) is compressed to a 5-line summary.

**Advisor compression:**
```
### Advisor: Mid-Implementation (optional)
Only when executor hits genuinely ambiguous decision. Not every step.
Dispatch Opus with: $plan step N context + specific decision + options.
```

**Target size:** ~3K tokens

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-5-implementation.md
git commit -m "refactor(workflow): extract Phase 5 implementation to phase file

Includes context management strategy and compressed advisor template."
```

---

### Task 10: Create Phase 5.5 Reflection File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-5.5-reflection.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 1381-1415

**Step 1: Write phase-5.5-reflection.md**

Extract Phase 5.5 verbatim — it's already compact (~1K tokens). Keep the reflect checklist and outcome actions.

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-5.5-reflection.md
git commit -m "refactor(workflow): extract Phase 5.5 reflection to phase file"
```

---

### Task 11: Create Phase 6 Quality File (value_unit)

**Files:**
- Create: `skills/code-creation-workflow/phases/phase-6-quality.md`
- Read: `skills/code-creation-workflow/SKILL.md` lines 1417-1690

**Step 1: Write phase-6-quality.md**

Extract Phase 6. Key changes:

**Reviewer consolidation (Tier 2):**
Replace the 3 separate Tier 2 always-on entries:
```
| 2 | safety-reviewer | sonnet | Always — silent failures + security (combined) |
| 2 | test-coverage-analyzer | sonnet | Always — test gaps |
```

**Payload slimming instructions:** Add explicit guidance:
```
### Reviewer Payload Contract
All reviewers receive:
- $diff.git_diff (full diff — required)
- $requirements.acceptance_criteria only (not full $requirements)
- $plan step IDs + files only (not full descriptions)
- 2-line role description + checklist focus
```

**Code simplifier conditional skip:** Add:
```
Skip code-simplifier if $diff.insertions + $diff.deletions < 100
```

Keep:
- Registry-driven selection logic
- Eval contamination guard
- Review-fix-recheck loop
- Cross-cutting synthesis
- Static analysis gate
- Verification gate
- Finish branch
- Capture learnings
- Workflow retrospective (references `failure-taxonomy.md`)

**Advisor compression (optional Strategic Pre-Review):**
```
### Advisor: Strategic Pre-Review (optional)
Only for full path with complex features.
Dispatch Opus with $diff + $requirements.
Question: "Does this fulfill the original requirements?"
```

**Target size:** ~3K tokens

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/phases/phase-6-quality.md
git commit -m "refactor(workflow): extract Phase 6 quality to phase file

Consolidates Tier 2 reviewers (3→2), adds payload slimming
instructions, conditional code-simplifier skip."
```

---

### Task 12: Rewrite SKILL.md as Thin Router (value_unit)

**depends_on:** Tasks 1-11 (all phase files and contracts must exist)

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md` (full rewrite)

**Step 1: Read current SKILL.md header content**

Read lines 1-100 for model strategy content to preserve.
Read lines 1692-1706 for quick reference table.
Read lines 1811-1845 for common mistakes to compress.

**Step 2: Rewrite SKILL.md**

The new SKILL.md should contain ONLY:

1. **Frontmatter** (unchanged name/description, keep user-invocable: true)

2. **Overview** (3 lines): What the workflow is, executor/advisor strategy, project-agnostic note

3. **Model Assignments** (compact table):
```
| Role | Model | When |
|------|-------|------|
| Executor | sonnet | Every turn |
| Advisor | opus | 3-5 checkpoints |
| Light reviewers | haiku | Phase 6 convention checks |
| Specialist reviewers | sonnet | Phase 6 security/coverage |
```

4. **Phase Loading Instructions**:
```
## How to Use This Workflow

1. Load this file (always resident)
2. Load contracts/*.schema.md (always resident — ~800 tokens total)
3. On entering each phase: load phases/phase-N-*.md
4. On completing each phase: the phase file can be dropped —
   the populated contract ($exploration, $requirements, $plan, $diff)
   carries forward at 1/10th the size
5. Reference files in references/ are lazy-loaded by phases that need them
```

5. **Path Decision Tree** (the compressed flowchart from Phase 1 — this must be in the router because it's Phase 1's core logic and must be immediately available):
```
BUG? → /bug-fix
SMALL (1 file, no schema)? → FAST PATH (make change → test → commit)
HAS PLAN/PRP? → PLAN PATH (read plan → Phase 5)
NEAR-IDENTICAL FEATURE? → CLONE PATH (clone + adapt → Phase 6)
1-2 FILES? → LITE PATH (Phases 2-6, inline arch)
EXPLORATORY? → EXPLORE PATH (sandbox, 60/100 bar)
ELSE → FULL WORKFLOW (all phases)
```

6. **Phase Transition Map** (the table — keep as-is, it's already compact)

7. **Phase Output Contracts** (summary pointing to files):
```
| Contract | File | Produced By | Consumed By |
|----------|------|-------------|-------------|
| $exploration | contracts/exploration.schema.md | Phase 2 | Phases 3, 4, advisors |
| $requirements | contracts/requirements.schema.md | Phase 3 | Phases 4, 4c, 5, 6 |
| $plan | contracts/plan.schema.md | Phase 4b | Phases 4c, 4d, 5, 6 |
| $diff | contracts/diff.schema.md | Phase 5 | Phase 6 |
```

8. **Quick Reference** (existing 6-row table)

9. **Common Mistakes** (compressed to ~15 rows — remove rows that duplicate phase-file content, keep cross-cutting mistakes):
- Skipping Phase 0 context loading
- Exploring without checking prior knowledge
- Skipping Phase 4c verification
- Jumping to fixes without evidence
- Calling advisor every turn (3-5 per workflow, not every step)
- Skipping advisor at required checkpoints
- Coding before clarification
- Single architecture proposal
- Passing full conversation to subagents (use contracts)
- Using full workflow for 1-2 file changes
- Writing tests after code
- Guessing external API patterns
- Not tagging workflow failures
- Letting context grow unbounded
- Running 10-step plans without context breaks

10. **Error Recovery** (existing table — keep, it's already compact)

**What is NOT in the new SKILL.md:**
- No workflow state machine JSON/jq (moved to phase-0)
- No phase instructions (moved to phase files)
- No advisor prompt templates (compressed into phase files)
- No context management strategy (moved to phase-5)
- No failure taxonomy (moved to references/)
- No agent/skill/tools tables (moved to references/)
- No skills eliminated table (moved to references/)

**Step 3: Verify token count**

Run: `wc -c skills/code-creation-workflow/SKILL.md`
Expected: Under 10000 bytes (~2.5K tokens)

**Step 4: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "refactor(workflow): rewrite SKILL.md as thin router (~2.5K tokens)

Replaces 24K-token monolith with progressive-disclosure router.
Phase instructions in phases/*, contracts in contracts/*,
reference tables in references/*. 90% reduction in always-loaded context."
```

---

### Task 13: Validate End-to-End (value_unit)

**depends_on:** Task 12

**Files:**
- Read: all new files for consistency check

**Step 1: Verify all files exist**

```bash
ls -la skills/code-creation-workflow/SKILL.md
ls -la skills/code-creation-workflow/contracts/
ls -la skills/code-creation-workflow/phases/
ls -la skills/code-creation-workflow/references/failure-taxonomy.md
ls -la skills/code-creation-workflow/references/agent-registry.md
```

**Step 2: Verify no content was lost**

Check that every section header from the original SKILL.md has a home:
- Workflow State Machine → phase-0-context.md
- Phase 0 + 0.5 → phase-0-context.md
- Phase 1 → phase-1-discovery.md
- Phase 2 → phase-2-exploration.md
- Phase 3 → phase-3-requirements.md
- Phase 4 + 4b → phase-4-architecture.md
- Phase 4c → phase-4c-verification.md
- Phase 4d → phase-4d-skeletons.md
- Context Management → phase-5-implementation.md
- Phase 5 → phase-5-implementation.md
- Phase 5.5 → phase-5.5-reflection.md
- Phase 6 → phase-6-quality.md
- Quick Reference → SKILL.md (router)
- Agents/Skills/Tools/Eliminated → references/agent-registry.md
- Error Recovery → SKILL.md (router)
- Failure Taxonomy → references/failure-taxonomy.md
- Common Mistakes → SKILL.md (router, compressed)

**Step 3: Verify cross-references**

Grep all phase files for references to other phases — ensure they say "load phases/phase-N.md" not "see below":
```bash
grep -r "see below\|see above\|described above\|described below" skills/code-creation-workflow/phases/
```
Expected: no matches (all cross-references use file paths)

**Step 4: Verify token targets**

```bash
wc -c skills/code-creation-workflow/SKILL.md
wc -c skills/code-creation-workflow/contracts/*.md
wc -c skills/code-creation-workflow/phases/*.md
```

Expected approximate sizes:
- SKILL.md: <10KB (~2.5K tokens)
- contracts/ total: <3.5KB (~800 tokens)
- phases/ total: <80KB (~20K tokens across all phases, but never loaded simultaneously)

**Step 5: Commit validation results**

```bash
git add -A skills/code-creation-workflow/
git commit -m "chore(workflow): validate token efficiency overhaul — all content accounted for"
```

---

## Dependency Graph

```
Task 1 (contracts) ──────────────────────────┐
Task 2 (failure-taxonomy + agent-registry) ──┤
Task 3 (phase-0) ───────────────────────────┤
Task 4 (phase-1) ───────────────────────────┤
Task 5 (phase-2) ───────────────────────────┤
Task 6 (phase-3) ───────────────────────────┤
Task 7 (phase-4) ───────────────────────────┼── Task 12 (router rewrite) ── Task 13 (validate)
Task 8 (phase-4c + 4d) ────────────────────┤
Task 9 (phase-5) ───────────────────────────┤
Task 10 (phase-5.5) ────────────────────────┤
Task 11 (phase-6) ──────────────────────────┘
```

Tasks 1-11 are **parallelizable** (all read from the existing SKILL.md, write to new files — no conflicts). Task 12 depends on all of them. Task 13 depends on Task 12.
