---
name: code-creation-workflow
description: Use when creating new features, implementing complex changes, or executing implementation plans. Agentic workflow with parallel subagents for exploration, architecture, implementation, and review.
user-invocable: true
---

# Code Creation Workflow

## Overview

Agentic multi-phase workflow for building features. Uses parallel subagents for exploration and architecture, TDD for implementation, and parallel reviewers for quality. Replaces manual grep-and-plan with structured agent orchestration.

**This workflow is project-agnostic.** It works for any codebase or greenfield project, not just CourierFlow. Phase 0 adapts to whatever project context exists (CLAUDE.md, core skills, etc.). For greenfield projects with no existing codebase, skip Phase 2 exploration and go straight to clarification and architecture. All phases (discovery, competing architectures, TDD, review) apply universally.

**Announce:** "Running code-creation-workflow — loading context, exploring codebase, then building with you."

---

## Model Strategy

Use **Opus** for thinking-heavy phases (exploration, architecture, planning) and **Sonnet** for execution-heavy phases (implementation, review). This optimizes for deep reasoning where it matters and fast throughput where speed wins.

| Phase | Model | Why |
|-------|-------|-----|
| 0 Context | (main session) | Lightweight loading |
| 1 Discovery | (main session) | Quick triage decision |
| 2 Exploration | **opus** | Deep codebase analysis needs reasoning |
| 3 Clarification | (main session) | Interactive with user |
| 4 Architecture | **opus** | Architectural decisions need deep reasoning |
| 5 Implementation | **sonnet** | Execution speed — patterns are known by now |
| 6 Review | **sonnet** | Pattern-matching against conventions |

When dispatching subagents, pass `model: "opus"` or `model: "sonnet"` on the Agent tool call to enforce this.

### Self-Modification Engine

Patterns that recur across sessions (same failure class 3+ times, domains retrying >50%, etc.) should become skill updates. The pattern detector scans event history and queues proposals for manual review.

```bash
# Detect new patterns from accumulated event data
python3 scripts/pattern-detector.py

# Review pending proposals
python3 scripts/review-proposals.py list

# Inspect one
python3 scripts/review-proposals.py show <id>

# Draft content (in a file), then attach + apply
python3 scripts/review-proposals.py set-content <id> draft.md
python3 scripts/review-proposals.py apply <id>

# Reject with reason
python3 scripts/review-proposals.py reject <id> "already covered"
```

**Safety:** Nothing is auto-applied. Every `apply` backs up the target file to `memory/skill-backups/`. Proposals with `confidence < 0.3` show `[low]` in the list.

Run `scripts/pattern-detector.py` periodically (e.g., after `session-learnings`) to refresh the queue.

### Phase Timing Events

At the end of each phase, emit a timing event for the performance dashboard:

```bash
scripts/emit-phase-event.sh <phase> $TIER $DURATION_S $RETRIES [$DOMAIN]
```

Example: `scripts/emit-phase-event.sh exploration moderate 127 0 routes`

Appends to `memory/phase-events.jsonl`. View the dashboard with:

```bash
python3 scripts/dashboard.py              # text, last 30 days
python3 scripts/dashboard.py --html memory/dashboard.html   # also write HTML
python3 scripts/dashboard.py --days 0     # all time
```

Emitting is best-effort — missed events just reduce the dashboard's data.

### Auto-Tuned Thinking Budgets

Thinking budgets are selected per-dispatch by `scripts/thinking-budget.py` based on (a) the complexity classifier tier from Phase 1 and (b) per-domain historical retry rates in the registry.

| Keyword | Budget | Used For |
|---------|--------|----------|
| `think about this...` | ~4K tokens | Simple steps, straightforward edits |
| `think harder about...` | ~10K tokens | Multi-step logic, integration analysis |
| `ultrathink about...` | ~32K tokens | Architecture, security, complex refactors |

**Resolution:** At each dispatch site, resolve `{{budget}}` via:

```bash
python3 scripts/thinking-budget.py \
  --phase <phase_name> \
  --tier <tier_from_classifier> \
  --domain <task_domain> \
  --registry memory/agent-registry.json
```

Returns one of `think` / `think harder` / `ultrathink`. Prefix the subagent prompt with `{{budget}} about...`.

**Safety floor:** Architecture phase is never below `think harder` regardless of tier or retry rate.

**Override:** Pass `--override ultrathink` to force a specific budget, or `--budget=` at the top level to skip auto-selection for an entire run.

Full table and rationale: `docs/plans/2026-04-07-auto-tuning-thinking-budgets-design.md`

### Swarm Tiers

Non-simple tasks get tiered swarm behavior. The complexity classifier (Phase 1) sets the tier; all subsequent phases adapt.

| Tier | Trigger | Behavior |
|------|---------|----------|
| **simple** | Fast-path (existing) | Single agent, no swarm overhead |
| **moderate** | Classifier score 4-6 | Registry-informed dispatch — agents work independently, registry selects best variants and budgets |
| **complex** | Classifier score 7+ | Shared scratchpad, staggered exploration, adversarial debate, build-state, staged review, meta-reviewer |

**User override:** `--tier=simple|moderate|complex` at any point bypasses the classifier.

Full classifier protocol: `swarm-protocols.md#1-complexity-classifier`
Schemas for all swarm data: `swarm-schemas.md`

**Registry event recording:** Every agent dispatch, finding, and outcome across all phases records events to the agent registry (see `swarm-schemas.md#registry-events-jsonl`). This is a cross-cutting concern noted at each dispatch point below.

### Unified Dispatch Pipeline

Every agent dispatch (Phases 2, 4, 5, 6) flows through a six-stage pipeline: MoE Router, Constraint Compiler, RAG Context Injection, Agent Dispatch, Symbolic Verifier, Post-Dispatch Recording. Components degrade independently -- partial pipeline is always better than no pipeline.

Full pipeline protocol, phase activation matrix, and component data flows: `references/dispatch-pipeline.md`
Expert config format and starter configs: `references/moe-expert-configs.md`
Constraint extraction rules and promotion protocol: `references/constraint-sources.md`
New schemas (expert config, constraint set, vector store, federated contribution, intervention, quality metric, causal effect): `swarm-schemas.md`

**Scripts:** `moe_router.py`, `constraint_compiler.py`, `symbolic_verifier.py`, `rag.py`, `causal.py`, `federation.py` (all in `scripts/`).

### Compaction Recovery Protocol

Long sessions trigger context compression (compaction). After compaction, the agent loses awareness of project rules, current plan state, and workflow position. This protocol prevents post-compaction drift.

**When compaction is detected** (confused behavior, forgetting rules, losing track of plan progress):

1. **Re-read CLAUDE.md** — Reload all project rules and conventions
2. **Re-read current plan** — If a plan file exists in `docs/plans/` or `plans/`, reload it
3. **Check TodoWrite state** — Review current todo items to re-establish where you are in the workflow
4. **Re-read the active skill** — If mid-workflow, re-read this SKILL.md to recover phase awareness
5. **Announce recovery** — Tell the user: "Context was compacted — I've reloaded project rules and plan state. Resuming from Phase X, Step Y."

**Rule:** If you notice yourself unsure about project conventions or your current workflow position, assume compaction occurred and run this protocol. False positives (unnecessary re-reads) are cheap. False negatives (drifting without rules) are expensive.

---

## Phase 0: Context Loading

<HARD-GATE>
Load project context before any exploration or coding.
</HARD-GATE>

### Step 1: Load Project Identity

Read the workspace `CLAUDE.md` (slim version — identity, terminology, boundaries, skill pointers).

### Step 0.5: Confirm Target Repo

Before any file creation or commits, verify: does this task affect the active project, or a skill/tool repo (e.g., claude_flow)?

- Work on a project feature → stay in active project repo
- Work on a skill, workflow tool, or code-creation-workflow itself → target is claude_flow at /Users/summerrae/claude_code/claude_flow/ — do NOT commit to active project

If unclear, ask: "Should this work go into [active-project] or claude_flow?"

### Step 2: Load Core Skill

If workspace has a core skill (e.g. `/courierflow-core`), load it for boundaries, terminology, and the trigger matrix.

### Step 3: Classify Task → Load Contextual Skills

Use the trigger matrix (from core skill or `skills/README.md`) to load **only** the skills relevant to this task:

```
Task touches templates/CSS/HTML?     → load UI skill
Task touches routes/services?        → load API skill
Task touches models/migrations?      → load data skill
Task touches external APIs?          → load integrations skill
Task involves git/deploy/PR?         → load git skill
Task involves auth/security?         → load security skill
```

Load **only** what matches. Don't dump everything into context.

### Step 4: Load Enforcement Skills (Always)

- **coding-best-practices** — Always loaded as baseline reference
- **Defensive skill** matching task type:
  - UI work → `defensive-ui-flows`
  - Backend work → `defensive-backend-flows`
  - Both → load both

### Step 5: Conditional Tools

| Condition | Action |
|-----------|--------|
| Feature uses external API | **REQUIRED:** Invoke `/fetch-api-docs` skill to get current API docs from Context Hub before any implementation. Do NOT code against external APIs from memory — formats change. |
| Codebase >500 files or unfamiliar | Run `python scripts/generate_repo_outline.py app/` for token-efficient context, or `repomix --compress` |
| Need symbol-level precision | Activate Serena project, read relevant memories |
| MCP-heavy exploration (DB queries, Figma imports) | Set `MAX_MCP_OUTPUT_TOKENS=50000` to prevent truncated MCP responses that degrade exploration quality |
| Small familiar codebase | Skip all |

**Token-saving tools available:**
- `generate_repo_outline.py` — Extracts function/class signatures without bodies (use for AI context)
- `semgrep` — Semantic static analysis (catches bugs before review)
- `ast-grep` — AST-based code search (more precise than grep)
- `pyright` — Fast type checking (augments mypy)

### Step 6: Pipeline Init (Federation Pull + Constraint Compiler)

1. **Federation pull** (if enabled): Query Supabase for matching federated priors. Blend into local registry per `references/dispatch-pipeline.md` blending ratios.
2. **Constraint Compiler init**: Compile initial constraint set from CLAUDE.md, loaded defensive skills, and MEMORY.md gotchas. This set is refreshed after Phase 4 architecture decisions and during Phase 5 build-state updates. See `references/constraint-sources.md`.

### Step 7: Git Check

Verify you're on a feature branch. If on main, create one before proceeding.

### Step 8: Bootstrap MEMORY.md (One-Time)

<SKIP-CONDITION>
Skip if a project-scoped `MEMORY.md` already exists. Check these locations in order:
1. `$PROJECT/.claude/memory/MEMORY.md` (Claude Code auto-memory)
2. `$PROJECT/MEMORY.md` (project root)
</SKIP-CONDITION>

If no MEMORY.md exists, create one to enable cross-session context persistence:

1. **Determine the memory directory.** Use `$PROJECT/.claude/memory/` if the `.claude/` directory exists; otherwise use `$PROJECT/`.
2. **Create MEMORY.md** with this starter template:

```markdown
# Project Memory

<!-- Index of memory files. Each entry: - [Title](file.md) — one-line description -->
<!-- Keep entries under 150 chars. Content goes in individual files, not here. -->
```

3. **Announce:** "Created MEMORY.md for cross-session context — I'll populate it as I learn about the project."

**Why this matters:** The memory-injection system (see `references/memory-injection.md`) maps domain-specific gotchas from MEMORY.md into subagent prompts. Without MEMORY.md, that system silently no-ops and gotchas discovered during sessions are lost.

---

## Phase 0.5: Bootstrap Project Hooks (One-Time)

<SKIP-CONDITION>
Skip if `.claude/hooks.json` already exists in the project root.
</SKIP-CONDITION>

Auto-generates Claude Code hooks based on the project's detected stack. Runs once per project, then skips on all subsequent sessions.

**Announce:** "No hooks detected — bootstrapping project hooks based on your stack."

### Step 1: Detect Stack

Check for signal files/dirs per the `references/hook-templates.md` reference. Build a stack profile as a set of tags (e.g., `python, alembic, ruff, has-env, service-layer`).

### Step 2: Generate hooks.json

Using the template library:
- **Always** include Tier 1 (universal) hooks — session context, **pre-compaction transcript backup**, post-commit memory, worktree guard
- Include Tier 2 hooks where stack tags match conditions (e.g., `has-env` → .env blocker, `ruff` → linter-on-save)
- Write to `$PROJECT/.claude/hooks.json`

### Step 3: Generate Hook Scripts + Config

1. Copy parameterized scripts from `~/claude-config/scripts/hooks/` into `$PROJECT/scripts/hooks/`
2. Generate `scripts/hooks/hook-config.sh` sidecar with:
   - Detected file categories (for post-commit memory updates)
   - Skill suggestions (for session-start context)
   - Linter command and glob pattern
3. Make all scripts executable (`chmod +x`)

### Step 4: Confirm

Output a summary table of generated hooks (trigger → what it does). Ask the user to review `hooks.json` before continuing to Phase 1.

---

## Phase 1: Discovery

Understand the request and decide the workflow path.

```
User says "implement X"
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │ Is this a SMALL change?                      │
   │ (single file, no schema, no new endpoints)   │
   │                                               │
   │ YES → FAST PATH                               │
   │   1. Load defensive skill                     │
   │   2. Make the change                          │
   │   3. Run tests                                │
   │   4. Commit → done                            │
   │                                               │
   │ Has EXISTING PLAN file?                       │
   │                                               │
   │ YES → PLAN PATH                               │
   │   1. Read the plan file                       │
   │   2. Skip to Phase 5 (Implementation)         │
   │   3. Execute the plan                         │
   │                                               │
   │ NO to both → FULL WORKFLOW (continue)         │
   └─────────────────────────────────────────────┘
```

**Fast path criteria:** Typo fix, one-line change, config tweak, single-file edit with no ripple effects. If in doubt, use the full workflow.

### Complexity Classification (After Fast-Path)

If not fast-path and not plan-path, classify complexity to set the swarm tier for all subsequent phases.

1. **Static scoring** — Score 4 axes (1-3 each) per `swarm-protocols.md#1-complexity-classifier`:
   - Reasoning depth, Ambiguity, Context dependency, Novelty
   - Sum: 4-6 = `moderate`, 7-9 = `complex`, 10-12 = `complex+` (reserved)
2. **Degradation probe** — At Phase 2 boundary (moderate/complex only): dispatch one Sonnet explorer with minimal context. If it succeeds → downgrade tier. If it fails → confirm tier.
3. **Record** `complexity_calibration` history entry (see `swarm-schemas.md#complexity-calibration-history-entry`). Record `dispatched` registry event for probe agent.
4. **Propagate** the tier to all subsequent phases. Announce: "Complexity tier: [moderate/complex]. Swarm protocols active."

---

## Phase 2: Exploration (Parallel Subagents)

### Pre-Exploration: Generate Repo Outline (Token Saver)

Before launching explorers, generate a token-efficient codebase map:

```bash
python scripts/generate_repo_outline.py app/services/ --max-depth 2
```

This provides function/class signatures WITHOUT implementation bodies — dramatically reduces tokens while preserving structure awareness. Share this outline with explorer agents.

### Launch Explorers

**Pipeline active:** All explorer dispatches go through the unified dispatch pipeline. MoE Router selects explorer experts from the matched expert config (see `references/moe-expert-configs.md`). RAG injects relevant past exploration findings into explorer prompts. Causal controlled skip applies at 5% rate for MODERATE/LOW value explorers.

#### Simple Tier (fast-path)

Not applicable — simple tasks skip exploration entirely.

#### Moderate Tier: Registry-Informed Dispatch

1. **Query registry:** For `[task_category]` in `[project_type]`, rank explorer prompt variants by `findings_used_rate`. Record `dispatched` event per explorer.
2. **Dispatch top 2 variants** (registry-selected, not hardcoded) in parallel as **opus** subagents.
3. **Run missed-context audit** after each explorer completes — see `swarm-protocols.md#7-missed-context-audit`. Log to `missed-context-log/SESSION_ID.json`.
4. **Record** `files_found` per explorer (keyed by variant_id) for outcome tracking.

**Fallback (no registry data):** Use prompts from `prompt-library.md` directly. Treat as UNKNOWN agents (dispatch with default budget).

#### Complex Tier: Staggered Exploration with Scratchpad

Explorers build on each other's findings via staggered (not parallel) dispatch. Full protocol: `swarm-protocols.md#2-exploration-scratchpad`.

1. **Create** empty `exploration-scratchpad.json` (schema: `swarm-schemas.md#exploration-scratchpad-ephemeral`).
2. **Dispatch Explorer A** (broadest prompt, no scratchpad yet). Record `dispatched` event.
3. **Explorer A writes** findings to scratchpad: `key_files`, `patterns_found`, `gaps_identified`.
4. **Run missed-context audit** on Explorer A output.
5. **Dispatch Explorer B** with scratchpad injected — prompt template in `swarm-protocols.md#2`. Record `dispatched` event.
6. **Explorer B appends** its findings, fills gaps where possible.
7. **Run missed-context audit** on Explorer B output.
8. **If unresolved gaps remain:** dispatch Explorer C (targeted, narrow scope). Run missed-context audit.
9. **Record** `files_found` per explorer (keyed by variant_id).

**Cost:** ~30s per staggered explorer, but eliminates redundant exploration and catches gaps.

#### Common (All Tiers)

**Variant selection (before dispatch):** Select optimized prompts via the prompt tracker for A/B testing:

```bash
python3 scripts/prompt-tracker.py select explorer <category> A
python3 scripts/prompt-tracker.py select explorer <category> B
```

Use returned prompt instead of `prompt-library.md` default. Record `variant_id` for Phase 5 outcome tracking.

**Subagent dispatch:** Use Agent tool with `subagent_type: "feature-dev:code-explorer"` or `"Explore"` and **`model: "opus"`**.

**Serena integration:** Use `find_symbol` / `find_referencing_symbols` instead of grep chains. Use `write_memory` to persist discoveries.

**Minimum output per explorer:** 5-10 key files, patterns, concerns/constraints.

### Post-Exploration: Context Hydration

<HARD-GATE>
The main session must read key files firsthand before Phases 3-4. Explorer summaries alone are not enough — the orchestrator needs the actual code in context to ask good clarification questions and evaluate architectures.
</HARD-GATE>

After explorers return, the **main session** (not a subagent) must:

1. **Deduplicate** — Merge file lists from all explorers, remove duplicates
2. **Prioritize** — Rank files by how many explorers flagged them (mentioned by 2+ explorers = highest priority)
3. **Read the top 5-10 files** directly using the Read tool — these are the files that will anchor Phases 3, 4, and 5
4. **Skim the next 5-10** — Read just the first 50-100 lines (signatures, imports, class structure) for supporting files

**Why this matters:** Subagent findings are summaries — they compress away the details the orchestrator needs for clarification questions (Phase 3) and architecture evaluation (Phase 4). Reading the actual files gives the main session firsthand knowledge of naming conventions, error patterns, data shapes, and integration seams that summaries miss.

**Token budget:** Aim for ~5,000-10,000 lines of firsthand file context. If the feature area is large, prefer reading complete files for the top 5 over skimming 20 files superficially.

**What to pass forward:** The hydrated file contents stay in the main session's context and naturally inform Phases 3 and 4. When dispatching architect subagents in Phase 4, reference specific file paths and patterns you observed — don't just forward explorer summaries.

**Memory injection:** After exploration completes, invoke the `memory-injection` skill with the deduplicated list of key files identified. Append the returned PROJECT GOTCHAS block to all subsequent subagent prompts (Phases 4, 5, and 6).

**Exploration persistence (moderate + complex):** After hydration, write exploration log to `.claude/swarm/exploration-log/SESSION_ID.json` (schema: `swarm-schemas.md#exploration-log`). Record `finding_used` / `finding_ignored` registry events per explorer based on which files were hydrated vs skipped.

---

## Phase 3: Clarification (Hard Gate)

<HARD-GATE>
All ambiguities must be resolved before architecture work begins.
</HARD-GATE>

Review exploration findings against the original request. Identify **every** underspecified aspect:

- **Edge cases** — What happens when input is empty, duplicated, or malformed?
- **Error handling** — What should the user see when things fail?
- **Integration points** — Which existing systems does this touch?
- **Scope boundaries** — What is explicitly NOT included?
- **Performance** — Will this hit large datasets or high concurrency?
- **Backward compatibility** — Does this change existing behavior?

Present an organized question list to the user. Group questions by category. Wait for answers before proceeding.

**If no ambiguities exist** (rare — usually means the request is very well-specified), state that explicitly and proceed to Phase 4.

### Optional: Export Context Packet (PRP)

After clarification is complete, optionally save a **Product Requirement Prompt (PRP)** — a reusable context packet that survives across sessions. A PRP is the minimum viable packet an AI needs to ship production-ready code on the first pass: requirements + curated codebase intelligence + implementation constraints.

**Trigger conditions** (export if ANY apply):
- Feature is complex enough to span multiple sessions
- User says "save context", "export this", or "I'll continue later"
- Task involves 3+ integration points or schema changes

**PRP format** — write to `plans/PRP-<feature-slug>.md`:

```markdown
# PRP: <Feature Name>
**Created:** <date> | **Status:** ready-for-implementation

## Requirements
- <resolved requirements from clarification>
- <scope boundaries — what's explicitly OUT>

## Codebase Intelligence
- **Key files:** <5-10 files from exploration with their roles>
- **Patterns to follow:** <discovered conventions from Phase 2>
- **Integration points:** <systems this touches>

## Constraints & Edge Cases
- <resolved edge cases from Phase 3>
- <performance considerations>
- <backward compatibility notes>

## Implementation Notes
- <API docs fetched (if applicable)>
- <defensive patterns required>
- <test strategy hints>
```

**How it's consumed:** Phase 1 Discovery detects PRP files via the PLAN PATH branch. A PRP provides richer context than a bare plan — it includes the codebase intelligence that would otherwise require re-running Phase 2 exploration.

If not triggered, skip — most single-session features don't need this.

---

## Phase 4: Architecture (Multi-Model Competition + Iterative Refinement)

**Pipeline active:** Architect dispatches go through the unified dispatch pipeline. MoE Router selects architect bias from expert config. RAG injects past architecture decisions for similar fingerprints. After the user chooses an architecture, the Constraint Compiler refreshes -- architecture rules become constraints for Phase 5 verification.

### Step 1: Competing Architecture Proposals

Launch 3 **code-architect** subagents in parallel with deliberately different optimization targets. The third "reuse" perspective prevents groupthink and surfaces approaches the other two miss.

#### Moderate Tier: Registry-Weighted Architects

ALL architects receive the full exploration context (not just orchestrator's summary):
- Full exploration scratchpad (if exists) or deduplicated explorer findings
- Gap chain: gaps found, which were resolved, which remain
- Explorer disagreements: areas characterized differently by different explorers

1. **Query registry** for user's historical `architecture_preferences` weights.
2. **Dispatch 3 architects** (simplicity, separation, reuse) with registry-weighted optimization targets. Record `dispatched` event per architect.
3. **Synthesis:** Weight toward historically preferred style. Sharpen reuse lens based on registry data.
4. **Record** `architecture_adopted` / `architecture_rejected` events after user chooses.

#### Complex Tier: Adversarial Debate + Gap Detection

Full protocol: `swarm-protocols.md#3-adversarial-architecture`.

**Round 1** (parallel, all receive full scratchpad):
- Architect A: simplicity | Architect B: separation | Architect C: reuse
- Record `dispatched` event per architect.

**Gap detection** (between Round 1 and Round 2):
1. Scan all 3 proposals for references to files/patterns NOT in scratchpad.
2. Detect unverified assumptions and open questions.
3. If gaps found → dispatch one Sonnet gap-fill explorer (narrow scope). Record `dispatched` event.
4. Append gap-fill findings to scratchpad. Log gap detections as exploration misses in `missed-context-log`.
5. If no gaps → skip to Round 2.

**Round 2** (parallel critics — each rebuts the other two):
- Critic A (simplicity lens), Critic B (separation lens), Critic C (reuse lens)
- All receive gap-fill findings + all Round 1 proposals. Record `dispatched` event per critic.
- Prompt template: `swarm-protocols.md#3-adversarial-architecture`

**Round 3** (single Opus synthesis judge):
- Reads all proposals + all rebuttals + gap-fill findings + registry `architecture_preferences` weights
- Produces recommendation with per-decision reasoning: adopted from whom, rejected which objection and why
- Record `dispatched` event. Record `critique_changed_outcome` / `critique_ignored` per critic.

**Cost:** 3 extra sonnet calls (critics) + 1 opus call (synthesis) + optional 1 sonnet (gap-fill).

#### Common (All Tiers)

```
Present ALL THREE architectures to user:
- Files to create/modify (with line counts)
- Component designs and responsibilities
- Data flow, trade-off analysis
- Best-of-all-worlds synthesis recommendation
        │
        ▼
◆ USER CHOOSES architecture (A, B, C, or hybrid) ◆
```

**Subagent dispatch:** Use Agent tool with `subagent_type: "feature-dev:code-architect"` and **`model: "opus"`**. Each gets exploration findings + clarification answers + PROJECT GOTCHAS from memory-injection.

**Architect variant tracking:**

```bash
python3 scripts/prompt-tracker.py select architect default simplicity
python3 scripts/prompt-tracker.py select architect default separation
python3 scripts/prompt-tracker.py select architect default reuse
```

Record `variant_id` of user's choice. After Phase 6, record outcome:

```bash
python3 scripts/prompt-tracker.py record '{
  "agent_type": "architect", "variant_id": "<chosen>",
  "role": "<simplicity|separation|reuse>", "user_chose_this": true,
  "refinement_rounds": <N>, "review_issues_critical": <N>, "review_issues_total": <N>
}'
```

**Architect C rotation:** Vary the third target by feature: "FUTURE EXTENSIBILITY", "PERFORMANCE", "MINIMAL RISK".

### Step 2: Write Implementation Plan

After user chooses, write a structured plan using the `writing-plans` skill:
- Numbered steps with specific files and changes
- Test requirements per step
- Dependencies between steps marked clearly

### Step 3: Iterative Plan Refinement

<HARD-GATE>
Do not skip refinement for complex features (3+ files, schema changes, or new endpoints). Simple features (single file, config tweaks) may skip to Step 4.
</HARD-GATE>

After the plan is written, refine it through 2-3 rounds. Each round uses a **fresh subagent** (clean context prevents anchoring on prior output).

**Refinement prompt template:**
```
ultrathink about... Carefully review this implementation plan.
Find every issue — I'm positive there are at least 30 problems
including architectural weaknesses, missing edge cases, unclear
steps, dependency gaps, and testing blind spots.

For each issue, provide:
1. What's wrong
2. Why it matters
3. The specific fix (as a diff against the plan)

Plan to review:
<PASTE CURRENT PLAN>
```

**The "overshoot" technique:** Models tend to stop finding problems after 20-25 issues. Telling them to find "at least 30" pushes them past this plateau. The number is deliberately ambitious — they'll find what they can, which is always more than without the target.

**Per-round process:**
1. Dispatch fresh `general-purpose` subagent with `model: "opus"` and the refinement prompt
2. Review suggested changes — accept the good ones, reject overengineering
3. Update the plan in-place
4. Check for convergence (see below)

### Convergence Detection

Stop refining when any of these signals appear:

| Signal | What It Looks Like |
|--------|-------------------|
| **Suggestions become cosmetic** | "Consider renaming this variable" instead of "This architecture won't handle concurrent access" |
| **No architectural changes** | All suggestions are about implementation details, not structure |
| **Declining rate of change** | Round N finds 5 issues, Round N+1 finds 2, Round N+2 finds 1 |
| **Oscillation** | Two rounds alternating between approaches — pick one and commit |

**Rule of thumb:** 2 rounds minimum for complex features, 3 rounds maximum. If Round 3 still finds architectural issues, step back and reconsider the chosen architecture.

**Early termination red flags:**
- Oscillation (alternating between two versions) → reframe the problem, don't keep refining
- Expansion (output growing instead of shrinking) → step back, simplify
- Plateau at low quality → kill approach, restart architecture with different constraints

### Optional: PlanCraft AI Review

Triggered when:
- User says "review the plan" or "validate this"
- Task is high-complexity (3+ layers, schema changes, external API integration)

If triggered:
1. Run `plancraft_review.py` (DeepSeek + Codex validation)
2. Present critique and suggestions
3. Revise plan if needed
4. Get user re-approval

If not triggered: Skip. The multi-model competition + iterative refinement already provides robust validation.

```
◆ USER APPROVES final plan before implementation ◆
```

---

## Phase 5: Implementation (TDD + Defensive Patterns)

**Pipeline active:** Full dispatch pipeline with all stages. MoE Router selects thinking budgets per domain. Constraint Compiler provides the full constraint set (CLAUDE.md + skills + architecture + build-state). Symbolic Verifier runs hard + soft checks after each agent produces code. RAG injects failed approaches from past sessions. Causal controlled skip applies at 5% rate for MODERATE/LOW agents. Build-state decisions feed back to the Constraint Compiler as new consistency constraints.

<HARD-GATE>
User must approve the plan before any implementation begins.
</HARD-GATE>

### Swarm Tier: Moderate — Registry-Informed Execution

Per plan step:
1. **Query registry** for historical failure rate and thinking budget by domain.
2. **Set thinking budget:** <10% failure → `think about`, 10-30% → `think harder`, >30% → `ultrathink`.
3. **Skip specialist reviewers** with zero findings across 5+ dispatches (re-enable every 10th session).
4. Record `dispatched` event per implementation agent. Record `step_passed` / `step_failed` on completion.

### Swarm Tier: Complex — Build-State + Agent Signals

Full protocols: `swarm-protocols.md#4-build-state`, `swarm-protocols.md#5-agent-signals`.

**Build-state** (`.claude/swarm/build-state.json`, schema: `swarm-schemas.md#build-state-ephemeral`):
- Before first step: create empty build-state.
- After each step: agent writes `files_created`, `files_modified`, `interfaces_exposed`, `patterns_used`, `decisions_made`, `gotchas_encountered`, `failed_approaches`, `test_files`, `signal`.
- Next agent reads build-state → knows interfaces, patterns, and what NOT to try.

**Full context chain per implementation agent** (inject all 8 items):

| # | Item | Source |
|---|------|--------|
| 1 | Plan step | Phase 4 plan |
| 2 | Architecture decision | Chosen approach + trade-offs |
| 3 | Exploration scratchpad | Phase 2 scratchpad or explorer findings |
| 4 | Build-state | Interfaces, patterns, decisions from prior steps |
| 5 | Failed-approach log | Extracted from build-state |
| 6 | Gap-fill findings | Phase 4 gap-fill (if relevant area) |
| 7 | Registry priors | Historical failure rate + recommended thinking budget |
| 8 | Missed-context flags | `available_in_*` misses from prior steps in this area |

**Agent signals** — implementation agents return structured signals (not just pass/fail):

| Signal | Orchestrator action |
|--------|-------------------|
| `completed` | Dispatch next step normally |
| `completed_with_deviation` | Run architecture deviation check immediately |
| `completed_with_discovery` | Update build-state, re-evaluate downstream steps |
| `blocked` | PAUSE — surface to user, do not retry |

**Architecture deviation detection** (after every 3 steps, or immediately on deviation signal):
- Compare build-state against architecture decision (patterns, interfaces, assumptions).
- >50% steps deviated → PAUSE, surface to user.
- Single critical assumption violated → PAUSE immediately.

**Collaborative rescue** (before retry loop):
1. Package failure context: error + build-state + failed-approach log.
2. Query registry: highest success rate agent type for `[error_class]` in `[domain]`?
3. Different type with >20% higher rate AND >5 dispatches → dispatch that type. Record `rescue_succeeded` / `rescue_failed`.
4. No better type → fall back to standard retry loop.

### Pre-Implementation: Fetch External API Docs

<HARD-GATE>
If ANY plan step involves calling an external API (Google Calendar, Twilio, OpenAI, DocuSeal, Stripe, etc.), invoke `/fetch-api-docs` BEFORE writing code. Do NOT code against external APIs from memory — endpoints, request formats, and auth patterns change between versions. This gate applies even if you loaded the integrations skill in Phase 0.
</HARD-GATE>

```
Plan step touches external API?
  YES → Invoke /fetch-api-docs skill
      → Fetch current docs from Context Hub (or web if unavailable)
      → Verify: endpoints, auth method, request/response shapes, rate limits
      → Pass verified API contract to implementation subagents
  NO  → Skip, proceed to implementation
```

### Create TodoWrite Items

Break the plan into individual TodoWrite items. Mark each complete as you finish it.

### Execute Each Step

Include PROJECT GOTCHAS from memory-injection in each implementation subagent's prompt.

For each plan step:

```
1. Write test FIRST (test-driven-development skill)
   - Test the expected behavior, not the implementation
   - Include edge cases identified in Phase 3

2. Implement to make the test pass
   - Follow patterns discovered in Phase 2
   - Apply defensive patterns throughout:
     UI → guard clauses, feedback states, loading/error/success
     Backend → input validation, error handling, no silent swallows

3. Run test → verify green
   If PASS → continue to step 4
   If FAIL → enter RETRY LOOP (see below)

4. Run static analysis on changed files (catch issues early):
   semgrep --config=.semgrep.yml <changed-files>
   ast-grep scan <changed-directory>
   If PASS → continue to step 5
   If FAIL → enter RETRY LOOP for lint_violation

5. Mark TodoWrite item complete
```

### Phase 5 Retry Loop

When a test or static analysis check fails during implementation:

```
RETRY LOOP (max 3 attempts):
  attempt = 1
  thinking_levels = [original_level, one_level_up, "ultrathink"]

  WHILE attempt <= 3 AND failure unresolved:

    1. EMIT failure event:
       Run: scripts/emit-failure-event.sh '{
         "session": "<session-id>",
         "phase": 5,
         "type": "failure:test|failure:lint",
         "step": "<step-number>",
         "files": [<files-touched>],
         "error_class": "<best-guess-class>",
         "error_summary": "<first 200 chars of error output>",
         "attempt": <attempt>,
         "resolution": null
       }'

    2. COMPLEX TIER: Check for collaborative rescue (swarm-protocols.md#5)
       before diagnosis — if registry shows a better agent type for this
       error_class, dispatch it with full failure context + build-state.

    3. MATCH against failure catalog:
       - Load catalog entries for matched domains (via memory-injection mapping)
       - Compare error output against each entry's Signal field
       - If match with high/medium confidence:
           → Apply the documented Fix strategy
           → EMIT resolution:known event
       - If no match or low confidence:
           → Dispatch DIAGNOSIS SUBAGENT (see references/diagnosis-subagent.md)
           → Model: sonnet (attempt 1-2), opus (attempt 3)
           → Thinking: thinking_levels[attempt - 1]
           → Complex tier: include build-state + failed-approach log in diagnosis context
           → Apply the returned fix_strategy / fix_code
           → If recurrence_likelihood is medium or high:
               → Draft new catalog entry
               → Run multi-model validation (plancraft_review.py)
               → If approved: append to memory/failure-catalog.md
               → Run: hooks/tier1/failure-catalog-push.sh
           → EMIT resolution:novel event

    4. RE-RUN verification (test or static analysis)
       If PASS → EMIT resolution event, EXIT loop, continue to next step
       If FAIL → increment attempt, CONTINUE loop

  IF attempt > 3:
    EMIT failure:unresolved event
    Surface to user: "Step X failed after 3 attempts. Root cause: [diagnosis].
    Last error: [output]. Manual intervention needed."
    WAIT for user guidance before proceeding.
```

**Token budget escalation during retries:**

| Attempt | Thinking Budget | Model |
|---------|----------------|-------|
| 1 | Same as original step | sonnet |
| 2 | One level up from original | sonnet |
| 3 | `ultrathink` | opus |

### Fresh Eyes Self-Review (After Major Chunks)

After completing a major implementation chunk (3+ files modified or a logically complete subsystem), pause and review your own work before proceeding.

```
After every 3+ file chunk:
  │
  ▼
  Re-read ALL new/modified code with "fresh eyes"
  │
  ▼
  Look for: obvious bugs, incorrect logic, missing error
  handling, violated patterns from Phase 2, edge cases
  from Phase 3 that weren't covered
  │
  ▼
  Fix anything found → re-run tests → then continue
```

**Fresh eyes prompt (self-directed):**
```
think harder about... Re-read all the code I just wrote
and modified in this chunk with fresh eyes. Look carefully
for obvious bugs, logic errors, missing error handling,
pattern violations, and edge cases I may have missed.
Fix anything found before moving on.
```

**Why this matters:** The cheapest bugs to fix are the ones you catch yourself immediately. This gate costs ~30 seconds of reasoning but prevents expensive rework discovered in Phase 6 review.

### Strategic Drift Detection

Every 5 completed plan steps (or when ~30 minutes of implementation have passed), run a drift checkpoint:

```
┌─────────────────────────────────────────────────────┐
│ DRIFT CHECK:                                         │
│                                                       │
│ 1. What did the user originally ask for?             │
│ 2. What have we built so far?                        │
│ 3. If we implement all remaining steps, do we        │
│    actually produce the thing we're building?        │
│ 4. Are any steps now redundant or missing?           │
│                                                       │
│ If drift detected:                                    │
│   → Stop implementation                              │
│   → Report to user: "We've drifted — here's how"    │
│   → Revise remaining steps before continuing         │
│                                                       │
│ If on track:                                          │
│   → Continue (no user interruption needed)           │
└─────────────────────────────────────────────────────┘
```

**Rule:** Drift detection is a silent self-check when on track. Only surface it to the user when drift is actually detected. A swarm (or agent) can look productive while heading in the wrong direction — this catches it early.

### Parallel Subagent Dispatch (Swarm-Adapted Coordination)

When the plan has 3+ steps with no dependencies between them:

```
Use subagent-driven-development skill:
  → Dispatch parallel implementation agents with model: "sonnet"
  → Each follows the same TDD + defensive pattern
  → Merge results when all complete
```

Only parallelize truly independent work — shared state or sequential dependencies must stay sequential.

**Complex tier parallel dispatch with build-state:**
1. All parallel agents receive same build-state snapshot.
2. All write to build-state on completion.
3. Orchestrator merges entries before dispatching next sequential step.
4. Conflicting pattern decisions flagged as `parallel_conflicts` — resolve before proceeding.

**Swarm coordination protocol** (when dispatching 3+ parallel agents):

1. **Stagger dispatch** — Wait 2-3 seconds between agent launches. Sending all at once causes the "thundering herd" problem where agents pick the same work.

2. **Structured marching orders** — Each agent gets an explicit prompt:
   ```
   think about this... You are implementing Step [N]: [description].

   FILES YOU OWN (do not modify others):
   - [file1.py] — [what you're doing to it]
   - [file2.py] — [what you're doing to it]

   CONTEXT:
   - Patterns to follow: [from Phase 2 exploration]
   - Edge cases to handle: [from Phase 3 clarification]
   - Dependencies: [what must exist before your code works]

   WORKFLOW: Write test → implement → verify green → report done.
   ```

3. **Explicit file claims** — Each agent's prompt explicitly lists which files it will touch. No agent modifies files outside its claim without coordinating.

4. **Work announcement** — Each agent's first action is announcing what it's working on (via its return message), not silently starting.

### Conditional Specialist Reviews (During Implementation)

When a plan step produces code matching a specialist's domain, dispatch the specialist immediately (**sonnet**, background) before proceeding to the next step:

| Trigger | Agent | Action on CRITICAL |
|---------|-------|--------------------|
| Alembic migration file created/modified | `migration-reviewer` | Fix before next step |
| Google Calendar/Drive/Gmail API code | `google-api-reviewer` | Fix before next step |
| `async def` with I/O operations | `async-reviewer` | Fix before next step |

MEDIUM/LOW findings defer to Phase 6 review. Agents that ran in Phase 5 are **skipped** in Phase 6 (no double review).

### Best Practices Applied Throughout

| When | Apply |
|------|-------|
| Writing code | Type hints, async patterns, service layer |
| Changing schema | Migration checklist, foreign keys |
| Adding endpoints | Route naming, HTTP methods, rate limiting |
| Modifying JS | Null checks, event handlers, cache bust |
| UI flows | defensive-ui-flows: guard feedback, state flags, overlay inline |
| Backend error handling | defensive-backend-flows: no silent swallows, log or re-raise |
| Data migrations | defensive-backend-flows: copy before delete, reversible ops |
| Cross-module calls | defensive-backend-flows: respect encapsulation, public wrappers |

### Post-Implementation: Record Exploration Outcomes

After Phase 5 completes, record which files were actually used in implementation. This closes the feedback loop for explorer prompt optimization:

```bash
# For each explorer that ran in Phase 2, record the outcome
python3 scripts/prompt-tracker.py record '{
  "agent_type": "explorer",
  "session_id": "<session>",
  "task_category": "<category>",
  "variant_id": "<variant_id_from_phase2>",
  "explorer_role": "<A or B>",
  "files_found": ["file1.py", "file2.py"],
  "files_used_in_impl": ["file1.py", "file3.py", "file4.py"],
  "phase5_retries": <retry_count>,
  "plan_steps": <total_steps>,
  "domain": "<task_domain: routes|migrations|tests|ui|auth|...>"
}'
```

Where:
- `files_found` = files listed in explorer output (Phase 2)
- `files_used_in_impl` = all files read/edited during Phase 5 implementation
- `phase5_retries` = total retry loop iterations across all steps
- `plan_steps` = number of plan steps executed
- `domain` = task domain from smart-exploration; used by thinking-budget auto-tuning to track per-domain retry rates

---

## Phase 6: Quality + Finish

**Pipeline active:** MoE Router selects reviewer priority from expert config. Symbolic Verifier runs hard checks on reviewer-proposed fixes. Causal controlled skip applies at 5% rate for MODERATE/LOW reviewers. Full constraint verification ensures all hard constraints pass before the verification gate.

### Swarm Tier: Moderate — Registry-Selective Dispatch

Classify reviewers by registry data before dispatch:

| Category | Criteria | Action |
|----------|----------|--------|
| HIGH VALUE | >20% finding rate AND >50% accepted | Full thinking budget |
| MODERATE VALUE | Findings exist, mixed acceptance | Reduced thinking budget |
| LOW VALUE | <5% finding rate across 5+ dispatches | Skip (re-enable every 10th session) |
| UNKNOWN | <5 dispatches | Default budget (building priors) |

Dispatch order: HIGH → MODERATE + UNKNOWN → skip LOW. Record `dispatched` event per reviewer. Record `review_finding_accepted` / `review_finding_dismissed` per finding.

### Swarm Tier: Complex — Wave Protocol + Meta-Reviewer

Full protocol: `swarm-protocols.md#6-staged-review`.

**Wave 1** (parallel — highest-value reviewers from registry):
- Code Reviewer A, Security Reviewer, Silent Failure Hunter
- Each writes to `review-findings.json` (schema: `swarm-schemas.md#review-findings-ephemeral`): `areas_reviewed`, `findings[]`, `patterns_noticed`
- Record `dispatched` event per reviewer.

**Wave 2** (parallel — receives Wave 1 findings):
- Code Reviewer B: check if Wave 1 patterns extend to uncovered areas.
- QA Edge-Case Reviewer: verify tests cover Wave 1 bugs + adjacent edge cases.
- Production Readiness: verify Wave 1 security fixes are production-safe.
- Prompt templates: `swarm-protocols.md#6-staged-review`. Record `dispatched` event per reviewer.

**Wave 3 — Meta-Reviewer** (single agent, receives ALL findings + build-state):
1. **Pattern escalation:** findings across different files/reviewers with shared root cause → mark SYSTEMIC.
2. **Deduplication:** merge overlapping findings, keep highest-severity.
3. **Priority synthesis:** re-rank by actual production impact.
4. **Gap detection:** areas in build-state with high complexity that no reviewer examined.
5. **Contradiction resolution:** investigate, pick side, show reasoning.
- Record `dispatched` event. Record `meta_escalation_led_to_fix` / `meta_escalation_was_noise` per escalation.

**Both tiers:** Run missed-context audit on reviewers — was each bug catchable by implementation agent, fresh-eyes review, or documented in CLAUDE.md/MEMORY.md? Log to `missed-context-log`. Feed review-found issues back to exploration scope for future sessions.

### 4-Tier Parallel Review

Dispatch all applicable agents in a single parallel batch with **`model: "sonnet"`**. Each gets the diff + the plan + project conventions. Include PROJECT GOTCHAS from memory-injection in each reviewer's prompt.

**Overshoot technique for ALL review prompts:** Append this to every reviewer's prompt: *"I'm positive there are at least 30 issues in this code — find them all. Look for bugs, logic errors, security issues, pattern violations, edge cases, and quality gaps."* Models find 30-50% more issues when given an ambitious target versus "find any problems." The number is deliberately unreachable — it prevents the model from stopping after finding 20-25 issues, which is the typical plateau.

**Tier 1 — Core (always run):**

| Agent | `subagent_type` | Focus |
|-------|-----------------|-------|
| Reviewer A | `feature-dev:code-reviewer` | Bugs, logic errors, race conditions |
| Reviewer B | `feature-dev:code-reviewer` | Conventions, patterns, plan adherence |
| Silent Failure Hunter | `pr-review-toolkit:silent-failure-hunter` | Swallowed errors, empty catches, hidden failures |
| Security Reviewer | `security-reviewer` | Auth, data exposure, injection, OWASP |
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | Test coverage gaps, missing edge cases, untested error paths |
| Production Readiness | `general-purpose` | Auth config, data protection, monitoring, IaC gaps — uses `production-readiness-check` skill (structured checklist — do NOT apply overshoot prompt) |

**Production Readiness dispatch prompt:**
```
You are running a production readiness check. Load and follow the `production-readiness-check` skill exactly.

Diff to review: [paste git diff or provide file list]
Branch: [branch name]

Run the skill's 6-step process: get diff → minimal core checks → match deep-dive triggers → expanded checks → report findings table → propose fix plan (wait for user approval before fixing).

Do NOT freelance — follow the skill's checklist and scoring. Report in the skill's table format.
```

**Tier 2 — Conditional (skip if already ran in Phase 5):**

| Condition | Agent | `subagent_type` |
|-----------|-------|-----------------|
| New/modified Alembic migrations | Migration Reviewer | `migration-reviewer` |
| Google API integration code | Google API Reviewer | `google-api-reviewer` |
| Async code paths | Async Reviewer | `async-reviewer` |
| New types/models/Pydantic schemas | Type Design Analyzer | `pr-review-toolkit:type-design-analyzer` |
| New/modified API routes | API Doc Auditor | `api-doc-auditor` |

**Tier 3 — Domain (always for CourierFlow projects):**

| Agent | `subagent_type` | Focus |
|-------|-----------------|-------|
| Invariant Checker | `courierflow-invariant-checker` | Client sync, column names, query safety, eager loading |
| Defensive Verifier | `defensive-pattern-verifier` | Guard clauses, error handling, UI state management |

**Tier 4 — Design Review (when UI was modified):**

<SKIP-CONDITION>
Skip if no templates, CSS, HTML, or JS files were modified in this feature.
</SKIP-CONDITION>

Dispatch a design-review agent that tests the **live rendered UI**, not just the code. Uses Claude Preview or Playwright MCP to interact with the running application.

| Agent | `subagent_type` | Focus |
|-------|-----------------|-------|
| Design Reviewer | `general-purpose` | Visual consistency, responsiveness, accessibility, interaction quality |

**Design Reviewer prompt must include these 5 checks:**

1. **Interaction & User Flow** — Execute the primary user flow. Test hover/active/disabled states. Verify destructive action confirmations. Assess perceived performance.
2. **Responsiveness** — Test at desktop (1440px), tablet (768px), and mobile (375px) viewports. Verify no overflow, no horizontal scroll, touch targets adequate.
3. **Visual Polish** — Layout alignment, spacing consistency, typography hierarchy, color palette adherence, visual hierarchy guides attention correctly.
4. **Accessibility (WCAG 2.1 AA)** — Keyboard navigation (Tab order), visible focus states, Enter/Space activation, semantic HTML, form labels, alt text, color contrast (4.5:1 minimum).
5. **Robustness** — Form validation with invalid inputs, content overflow, loading/empty/error states rendered correctly.

**Design Review triage levels:**
- **[Blocker]** — Critical failures (broken flow, inaccessible, overflow at standard viewport)
- **[High-Priority]** — Fix before merge (contrast failure, missing focus state, broken responsive layout)
- **[Medium-Priority]** — Follow-up task (minor spacing inconsistency, polish items)
- **[Nitpick]** — Aesthetic preference (prefix with "Nit:")

**Prerequisites:** The dev server must be running for the design reviewer to work. If using Claude Preview, ensure `preview_start` is configured in `.claude/launch.json`. If the server can't be started, fall back to code-only review and note that visual testing was skipped.

**Merge & fix:** Collect all findings across all tiers, deduplicate, fix HIGH+ issues (including Design Review Blockers and High-Priority). Post summary of findings to user.

### Phase 6 Retry Loop

When fixing a review finding, use the same retry loop as Phase 5. Review fixes are especially prone to introducing new issues — the retry loop catches cascading failures.

```
For each HIGH+ review finding to fix:

  1. Apply fix
  2. Run affected tests + static analysis
  3. If PASS → mark finding resolved, continue
  4. If FAIL → enter RETRY LOOP (same as Phase 5, but with):
     - type: "failure:review"
     - Include the original review finding in the diagnosis context
     - Diagnosis subagent gets both the review comment AND the error output

  After all findings fixed:
  5. Re-run FULL test suite (not just affected tests)
  6. If new failures → these are regressions from fixes
     Enter RETRY LOOP with error_class "regression"
```

**Tier 5 — UI/UX Polish (when UI was modified):**

<SKIP-CONDITION>
Skip if no templates, CSS, HTML, or JS files were modified, OR if Design Review (Tier 4) found no UI to polish.
</SKIP-CONDITION>

This is distinct from Tier 4 Design Review. Tier 4 finds bugs (broken flows, accessibility failures, overflow). Tier 5 finds friction, ugliness, and missed opportunities to delight. The problems here aren't bugs — they're quality gaps.

Dispatch a `general-purpose` subagent with **`model: "opus"`** (needs taste, not speed):

**UI/UX Polish prompt:**
```
ultrathink about... Scrutinize every aspect of the application
workflow and look for things that are sub-optimal from a
user-friendliness and intuitiveness standpoint. Look for places
where the UI/UX could be improved to feel slicker, more visually
appealing, and more premium — like Stripe-level quality.

Evaluate SEPARATELY for:
1. DESKTOP (1440px+) — hover states, keyboard shortcuts,
   information density, whitespace balance
2. MOBILE (375px) — touch targets, thumb zones, swipe
   affordances, content priority

For each finding, categorize as:
- [Friction] — something that slows the user down
- [Delight] — a missed opportunity to surprise/please
- [Polish] — visual inconsistency or rough edge
- [Flow] — a workflow that could be streamlined

Only flag things that would noticeably improve the user experience.
Skip nitpicks.
```

**Triage:** Fix [Friction] and [Flow] items. [Delight] and [Polish] items are user's choice — present them and ask.

### Random Code Exploration Review

After structured review tiers complete, dispatch one more agent for unstructured exploration. This catches cross-cutting issues that per-file review misses — problems only visible when you see how pieces fit together.

Dispatch a `general-purpose` subagent with **`model: "opus"`**:

**Random exploration prompt:**
```
ultrathink about... Randomly explore code files in this project.
Pick files to deeply investigate — trace their functionality and
execution flows through related files they import or are imported by.

Once you understand each file's purpose in the larger context,
do a careful check with fresh eyes for:
- Obvious bugs or logic errors
- Inconsistencies between related files
- Dead code or unreachable paths
- Assumptions that don't hold across the codebase
- Error handling gaps in call chains

I'm positive there are at least 20 issues across this codebase
that structured review missed. Find them.
```

**Rule:** This agent explores freely — don't constrain it to modified files. The value is in finding issues at the seams between components.

### Post-Review Simplifier

After fixing review issues, run a single code-simplifier pass before the verification gate:
- Dispatch `code-simplifier:code-simplifier` (inherits **opus** per plugin spec)
- Scope: only files modified during this feature
- Accept changes only if tests still pass afterward
- Skip for trivial changes (single-file edits, config tweaks)

### De-Slopification Pass

<SKIP-CONDITION>
Skip if no documentation, README sections, docstrings, or user-facing comments were written or modified.
</SKIP-CONDITION>

After code simplification, scan any generated documentation or substantial comments for telltale AI writing patterns. These patterns mark output as obviously machine-generated and reduce perceived quality.

**Patterns to find and fix:**

| Pattern | Problem | Fix |
|---------|---------|-----|
| Emdash overuse (—) | LLMs use emdashes constantly | Use semicolons, commas, or periods |
| "It's not X, it's Y" | Formulaic contrast structure | Rewrite directly |
| "Here's why" / "Here's why it matters:" | Clickbait-style lead-in | State the reason directly |
| "Let's dive in" / "Let's explore" | Forced enthusiasm | Delete or replace with substance |
| "At its core..." | Pseudo-profound opener | Start with the actual point |
| "It's worth noting..." | Unnecessary hedge | Just state the thing |
| "This ensures that..." | Weak causal claim | Use "because" or restructure |
| "Robust" / "Seamless" / "Leverage" | Buzzwords with no content | Use specific, concrete language |
| Bullet lists where prose works better | Over-structuring | Convert to sentences when natural |

**How to apply:** Read each documentation section aloud mentally. If it sounds like a corporate blog post, rewrite it to sound like a competent engineer explaining something to a colleague.

### Static Analysis Gate

Before verification, run comprehensive static analysis on all changed files:

```bash
# Type checking (fast, catches type errors)
pyright

# Semantic analysis (catches security + logic issues)
semgrep --config=.semgrep.yml --error app/

# Structural analysis (catches anti-patterns)
ast-grep scan app/
```

Fix any ERROR-level issues. Warnings/hints can be addressed later.

### Post-Review: Record Reviewer and Architect Outcomes

After all review tiers complete and fixes are applied, record outcomes for the prompt optimization system:

**Reviewer outcomes** — For each reviewer variant used, record signal quality:

```bash
python3 scripts/prompt-tracker.py record '{
  "agent_type": "reviewer",
  "variant_id": "<reviewer_variant_id>",
  "role": "<overshoot|focused>",
  "issues_found": <total_issues_reported>,
  "issues_fixed": <issues_that_were_actually_fixed>,
  "issues_dismissed": <issues_skipped_as_not_worth_fixing>,
  "false_positives": <issues_that_were_wrong_or_not_real>
}'
```

**Architect outcomes** — Record final quality signal for the chosen architecture:

```bash
python3 scripts/prompt-tracker.py record '{
  "agent_type": "architect",
  "variant_id": "<chosen_architect_variant_id>",
  "role": "<simplicity|separation|reuse>",
  "user_chose_this": true,
  "refinement_rounds": <rounds_in_phase4>,
  "review_issues_critical": <critical_issues_from_phase6>,
  "review_issues_total": <total_issues_from_phase6>
}'
```

### Verification Gate

Invoke `verification-before-completion` skill:
- All tests pass?
- No unintended file changes?
- Implementation matches the original request?
- No regressions in existing functionality?
- Static analysis passes (no ERROR-level issues)?

**Optional: Headless CI validation** — If the project has a CI pipeline (GitHub Actions, etc.), run `claude -p "Review the diff on this branch for issues"` as a headless smoke check before creating the PR. This catches issues that local tests miss (linting configs, CI-specific checks). Skip if no CI is configured.

### Finish Branch

Invoke `finishing-a-development-branch` skill:
1. Run full test suite (`pytest tests/ -v` or project equivalent)
2. **CourierFlow:** Run `./scripts/quick_ci.sh` or `just ci`
3. Commit with conventional message
4. Present options: merge, PR, keep branch, discard
5. Execute user's choice

### Capture Learnings

Invoke `session-learnings` skill:
- What patterns were discovered?
- What defensive rules were applied or should be added?
- Any Serena memories to persist?

### Pipeline Session-End Actions

After learnings capture, run the pipeline's session-end stage:

1. **RAG write:** Extract embeddable chunks from exploration-log (findings, failed approaches, discoveries, review patterns). Embed via OpenAI text-embedding-3-small. Append to vector store.
2. **Federation push** (if enabled and this is every 5th session): Anonymize registry deltas. Push to Supabase `federated_priors` table. See `references/dispatch-pipeline.md`.
3. **Intervention recording:** If any skill files, prompts, or protocols changed during this session, record an intervention entry in the registry for causal tracking.
4. **Session quality metric:** Compute composite quality score from test pass rate, review severity, retry count, violation count, and user satisfaction. Store in registry for causal inference.

---

## Quick Reference: All Phases

| Phase | Name | Model | Tier Behavior | Gate |
|-------|------|-------|--------------|------|
| 0 | Context | — | Same for all tiers | None |
| 1 | Discovery | — | Fast-path + complexity classifier (sets tier) | Auto |
| 2 | Exploration | **opus** | **mod:** registry-informed dispatch, parallel. **cx:** staggered scratchpad, gap-filling | **Context hydration** |
| 3 | Clarification | — | Same for all tiers | **User answers** |
| 4 | Architecture | **opus** | **mod:** registry-weighted synthesis. **cx:** adversarial debate (3 rounds) + gap detection | **User chooses + approves plan** |
| 5 | Implementation | **sonnet** | **mod:** registry-informed budgets. **cx:** build-state, agent signals, deviation detection, rescue | Tests pass |
| 6 | Quality + Finish | **sonnet/opus** | **mod:** registry-selective dispatch. **cx:** wave protocol + meta-reviewer | **Verification** |

**Legend:** mod = moderate tier, cx = complex tier.

## Agents Used Within This Workflow

| Agent | `subagent_type` | Phase | Trigger | Tier | Model |
|-------|-----------------|-------|---------|------|-------|
| Degradation Probe | `feature-dev:code-explorer` | 1 | moderate/complex | mod+cx | sonnet |
| Code Explorer (x2-3) | `feature-dev:code-explorer` | 2 | Always | all | opus |
| Gap-Fill Explorer | `feature-dev:code-explorer` | 2, 4 | Unresolved gaps (complex) | cx | sonnet |
| Code Architect (x3) | `feature-dev:code-architect` | 4 | Always | all | opus |
| Critic (x3) | `feature-dev:code-architect` | 4 | Complex tier | cx | sonnet |
| Synthesis Judge | `general-purpose` | 4 | Complex tier | cx | opus |
| Plan Refiner (x2-3 rounds) | `general-purpose` | 4 | Complex features | all | opus |
| Rescue Agent | (registry-selected type) | 5 | Failure + better agent type in registry | cx | varies |
| Migration Reviewer | `migration-reviewer` | 5, 6 | Alembic files | all | sonnet |
| Google API Reviewer | `google-api-reviewer` | 5, 6 | Google API code | all | sonnet |
| Async Reviewer | `async-reviewer` | 5, 6 | async I/O code | all | sonnet |
| Code Reviewer (x2) | `feature-dev:code-reviewer` | 6 | Always (overshoot prompts) | all | sonnet |
| Silent Failure Hunter | `pr-review-toolkit:silent-failure-hunter` | 6 | Always (overshoot prompts) | all | sonnet |
| Security Reviewer | `security-reviewer` | 6 | Always (overshoot prompts) | all | sonnet |
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | 6 | Always (overshoot prompts) | all | sonnet |
| Production Readiness | `general-purpose` | 6 | Always (hybrid trigger) | all | sonnet |
| Meta-Reviewer | `general-purpose` | 6 | Complex tier Wave 3 | cx | opus |
| Design Reviewer | `general-purpose` | 6 | UI files modified | all | sonnet |
| Type Design Analyzer | `pr-review-toolkit:type-design-analyzer` | 6 | New types/models | all | sonnet |
| API Doc Auditor | `api-doc-auditor` | 6 | New/modified routes | all | sonnet |
| Invariant Checker | `courierflow-invariant-checker` | 6 | Always (CF projects) | all | sonnet |
| Defensive Verifier | `defensive-pattern-verifier` | 6 | Always (CF projects) | all | sonnet |
| UX Polish Reviewer | `general-purpose` | 6 | UI files modified | all | opus |
| Random Code Explorer | `general-purpose` | 6 | Always (complex features) | all | opus |
| Code Simplifier | `code-simplifier:code-simplifier` | 6 | After review fixes | opus |

## Skills Invoked Within This Workflow

| Skill | Where Used |
|-------|-----------|
| fetch-api-docs | Phase 5 (pre-implementation gate for external APIs) |
| coding-best-practices | Phase 0 (loaded), Phase 5 (applied) |
| defensive-ui-flows | Phase 0 (loaded), Phase 5 (applied) |
| defensive-backend-flows | Phase 0 (loaded), Phase 5 (applied) |
| writing-plans | Phase 4 (plan creation) |
| executing-plans | Phase 5 (plan execution) |
| test-driven-development | Phase 5 (TDD per step) |
| subagent-driven-development | Phase 5 (parallel independent steps) |
| verification-before-completion | Phase 6 (pre-finish check) |
| finishing-a-development-branch | Phase 6 (branch completion) |
| session-learnings | Phase 6 (capture discoveries) |
| production-readiness-check | Phase 6 (production infra/ops review) |
| smart-exploration | Phase 2 (task classification + variant selection for explorers) |
| prompt-optimization | Phase 6 (triggered by session-learnings when exploration events exist) |
| memory-injection | Phase 2/4/5/6 (gotcha injection into subagent prompts) |

## Static Analysis Tools (Automatic)

| Tool | Where Used | Purpose |
|------|------------|---------|
| `generate_repo_outline.py` | Phase 2 (pre-exploration) | Token-efficient codebase context |
| `semgrep` | Phase 5 (per-step), Phase 6 (gate) | Semantic analysis, security checks |
| `ast-grep` | Phase 5 (per-step), Phase 6 (gate) | Structural anti-pattern detection |
| `pyright` | Phase 6 (gate) | Fast type checking |

## Pipeline Scripts

| Script | Where Used | Purpose |
|--------|------------|---------|
| `moe_router.py` | All dispatch phases | Fingerprint matching, expert config selection |
| `constraint_compiler.py` | Phase 0 (init), Phase 4-5 (refresh) | Rule extraction, constraint set assembly |
| `symbolic_verifier.py` | Phase 5-6 (post-agent) | Hard checks (grep/ast-grep) + soft checks (LLM) |
| `rag.py` | All dispatch phases + session end | Embed, store, retrieve, re-rank experience |
| `causal.py` | All dispatch phases + session end | Controlled skip, quality metric, effect estimation |
| `federation.py` | Phase 0 (pull) + session end (push) | Anonymized push/pull to Supabase |
| `prompt-tracker.py` | Phase 2 (select), Phase 5 (record), Phase 6 (record + metrics) | Variant selection, outcome recording, metric computation |

## Skills Eliminated (Absorbed)

| Former Skill | Absorbed Into |
|-------------|---------------|
| plancraft brainstorming | Phases 1-3 (discovery + exploration + clarification) |
| brainstorming skill | Phases 1-3 (interactive exploration replaces separate brainstorm) |
| PlanCraft full pipeline | Phase 4 optional AI review only (DeepSeek + Codex) |

## Error Recovery

| Situation | Action |
|-----------|--------|
| Explorer agent returns poor results | Re-dispatch with more specific prompt, or explore manually |
| All architecture options rejected | Ask user what they want different, re-run 3 architects with revised constraints |
| Tests fail during implementation | Fix immediately, don't proceed to next step |
| Reviewer finds critical issue | Fix before finishing, re-run verification |
| User wants to stop mid-workflow | Stop. Summarize state (phase, what's done, what's left). |
| Wrong architecture chosen | Revert to plan, re-architect with new constraints |
| Plan refinement oscillating | Two rounds alternating — pick one and commit, don't keep refining |
| Plan refinement expanding | Output growing instead of shrinking — step back, simplify |
| Strategic drift detected mid-implementation | Stop, report to user, revise remaining steps before continuing |
| Scratchpad write fails | Explorer continues without scratchpad — log warning, next explorer dispatches without prior context |
| Gap-fill returns nothing useful | Proceed to Round 2 without gap-fill — note in synthesis judge prompt |
| No registry data available | Treat all agents as UNKNOWN — default budgets, build priors from this session |
| Build-state parallel conflicts | Surface conflicting patterns to user, resolve before next sequential step |
| Meta-reviewer finds systemic pattern | Escalate as SYSTEMIC — fix root cause, not individual symptoms |
| Rescue agent fails | Fall back to standard retry loop with increased thinking budget |
| Tier seems wrong mid-session | User can override with `--tier=X` at any time; orchestrator re-adjusts |
| `available_in_prompt` miss rate >20% | Flag for prompt quality review after session (see periodic review) |
| Post-compaction confusion | Run Compaction Recovery Protocol immediately |
| Parallel agents touching same files | Review file claims, split work more granularly |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Skipping Phase 0 context loading | Always load project context first |
| Exploring sequentially instead of parallel | Use 2-3 explorer subagents |
| Proceeding to clarification with only explorer summaries | Context hydration is a hard gate — main session must read top 5-10 files firsthand before Phase 3 |
| Coding before clarification | Phase 3 is a hard gate — resolve ambiguities first |
| Only 2 architecture proposals | Always present 3 competing perspectives (simplicity vs separation vs reuse) |
| Skipping plan refinement | Complex features need 2-3 refinement rounds with fresh subagents |
| Implementing without polishing the plan | "Check your plan N times, implement once" — planning is 85% of the work |
| Writing tests after code | TDD — test first, then implement |
| Not doing fresh eyes self-review | After every 3+ file chunk, re-read your own code before continuing |
| Ignoring strategic drift | Every 5 steps, check: "Are remaining steps still producing the right thing?" |
| Dispatching all parallel agents at once | Stagger dispatch by 2-3 seconds to prevent thundering herd |
| Reviewer prompts without ambitious targets | Use overshoot: "find at least 30 issues" in every review prompt |
| Skipping random code exploration | Structured review misses cross-cutting issues — always run the explorer |
| AI-sounding documentation | Run de-slopification pass on all generated docs and comments |
| Not finishing the branch | Always run Phase 6 to completion |
| Guessing external API patterns | **Hard gate:** Invoke `/fetch-api-docs` before any API implementation — never code from memory |
| Multiple grep iterations for a symbol | Use Serena `find_symbol` or `find_referencing_symbols` |
| Re-discovering context each session | Use Serena `write_memory` / `read_memory` |
| Confused after long session | Run Compaction Recovery Protocol — re-read CLAUDE.md, plan, and todos |
