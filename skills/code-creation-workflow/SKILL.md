---
name: code-creation-workflow
description: Use when creating new features, implementing complex changes, or executing implementation plans. Agentic workflow using the Executor/Advisor strategy — Sonnet executes, Opus advises at key decision points.
user-invocable: true
---

# Code Creation Workflow

## Overview

Agentic multi-phase workflow for building features using the **Executor/Advisor strategy**. A Sonnet executor runs the main loop — exploring code, drafting architectures, implementing features. An Opus advisor is called on-demand at key decision points to review the shared context and provide strategic guidance. TDD for implementation, cascading reviewers for quality.

**This workflow is project-agnostic.** It works for any codebase or greenfield project, not just CourierFlow. Phase 0 adapts to whatever project context exists (CLAUDE.md, core skills, etc.). For greenfield projects with no existing codebase, skip Phase 2 exploration and go straight to clarification and architecture. All phases (discovery, competing architectures, TDD, review) apply universally.

**Announce:** "Running code-creation-workflow — loading context, exploring codebase, then building with you."

---

## Model Strategy: Executor/Advisor

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│   ┌─────────────────────┐         ┌─────────────────────┐    │
│   │     Executor         │  Tool   │      Advisor         │    │
│   │     Sonnet           │  call   │      Opus            │    │
│   │                      │ ──────► │                      │    │
│   │  Runs every turn     │         │  On-demand           │    │
│   │  Explores, drafts,   │         │  Reviews context,    │    │
│   │  implements          │ ◄────── │  sends advice        │    │
│   └──────────┬───────────┘         └──────────▲───────────┘    │
│              │                                │               │
│         Read / write                   Reviews context        │
│              │                                │               │
│              ▼                                │               │
│   ┌──────────────────────────────────────────┘               │
│   │     Shared context                                        │
│   │     Conversation · tools · history · files read           │
│   └──────────────────────────────────────────────────────────┘│
│                                                               │
│   Advisor reads the same context as Executor                  │
└───────────────────────────────────────────────────────────────┘
```

**The core principle:** Sonnet does the legwork (file reads, greps, code writing). Opus provides strategic guidance at checkpoints. Opus never executes — it advises.

**Why this beats parallel Opus subagents:**

| Old Problem | Advisor Fix |
|---|---|
| Context hydration gate — main session had to re-read files that explorer subagents already found | Eliminated — Sonnet reads files directly, context accumulates naturally |
| Explorer summaries "compress away details" | No summaries needed — Opus advisor sees the same files Sonnet read |
| Architect subagents lack cross-phase knowledge | Opus advisor sees full conversation history including exploration |
| Expensive — Opus ran entire exploration and architecture phases | Cheaper — Opus fires only at 3-5 decision points, Sonnet does the legwork |

### Model Assignments

| Role | Model | When |
|------|-------|------|
| **Executor** | **sonnet** | Every turn — exploration, drafting, implementation, all file I/O |
| **Advisor** | **opus** | On-demand at checkpoints — reviews shared context, returns strategic guidance |
| **Light reviewers** | **haiku** | Phase 6 — convention checks, defensive patterns, invariants |
| **Specialist reviewers** | **sonnet** | Phase 6 — security, silent failures, test coverage |

### Advisor Checkpoints (3-5 per workflow)

The advisor is called at these specific decision points, each with a focused question:

| Checkpoint | Phase | Advisor Question |
|------------|-------|-----------------|
| **Exploration Review** | End of Phase 2 | "Here's what I found about the codebase for this feature. What am I missing? What should I investigate deeper?" |
| **Architecture Critique** | Phase 4 | "Review these two architecture options against the exploration findings. What are the blind spots? Which trade-offs am I underweighting?" |
| **Plan Stress-Test** | Phase 4b | "Review this implementation plan. Find logic errors, missing edge cases, integration risks, and scope creep." |
| **Mid-Implementation** | Phase 5 (optional) | "I'm at a complex decision point in step N. Here's the context — which pattern should I follow and why?" |
| **Strategic Pre-Review** | Phase 6 (optional) | "Before code-level review, does this implementation fulfill the original requirements? Any architectural-level issues?" |

**How to dispatch the advisor:** Use the Agent tool with `model: "opus"` and `subagent_type: "general-purpose"`. The advisor prompt must include:
1. The specific question (from the table above)
2. A summary of what the executor has done so far
3. Key file paths and patterns discovered
4. The decision or artifact being reviewed

The advisor returns guidance — the executor acts on it.

### Extended Thinking for Critical Checkpoints

The Architecture Critique (Phase 4) and Plan Stress-Test (Phase 4b) checkpoints benefit from deeper reasoning. These are the highest-stakes decision points — a missed blind spot here propagates through all of implementation.

**When to request extended thinking in advisor prompts:**

| Checkpoint | Extended Thinking? | Rationale |
|------------|-------------------|-----------|
| Exploration Review (Phase 2) | No | Broad gap-finding, not deep analysis |
| **Architecture Critique (Phase 4)** | **Yes** | Trade-off analysis requires weighing multiple competing factors |
| **Plan Stress-Test (Phase 4b)** | **Yes** | Finding logic errors and edge cases in a multi-step plan requires systematic reasoning |
| Mid-Implementation (Phase 5) | No | Focused decision, speed matters more |
| Strategic Pre-Review (Phase 6) | No | High-level check, not deep reasoning |

**How to request it:** Add to the advisor prompt: "Think through this step by step before responding. Consider each constraint independently, then look for interactions between constraints."

This is a prompt-level technique — not the API-level `thinking` parameter (which applies to direct API calls). In Claude Code, the advisor subagent benefits from explicit "think step by step" instructions for complex architectural reasoning.

---

## Phase 0: Context Loading

<HARD-GATE>
Load project context before any exploration or coding.
</HARD-GATE>

### Step 1: Load Project Identity

Read the workspace `CLAUDE.md` (slim version — identity, terminology, boundaries, skill pointers).

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
| Codebase >500 files or unfamiliar | Run `python scripts/generate_repo_outline.py app/` for signatures + `repomix --compress` for full compressed context |
| Need symbol-level precision | Activate Serena project, read relevant memories |
| MCP-heavy exploration (DB queries, Figma imports) | Set `MAX_MCP_OUTPUT_TOKENS=50000` to prevent truncated MCP responses that degrade exploration quality |
| Small familiar codebase | Skip all |

**Token-saving tools available:**
- `generate_repo_outline.py` — Extracts function/class signatures without bodies (use for AI context)
- `semgrep` — Semantic static analysis (catches bugs before review)
- `ast-grep` — AST-based code search (more precise than grep)
- `pyright` — Fast type checking (augments mypy)

### Step 6: Git Check

Verify you're on a feature branch. If on main, create one before proceeding.

### Step 7: Bootstrap MEMORY.md (One-Time)

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
- **Always** include Tier 1 (universal) hooks — session context, **pre-compaction transcript backup**, post-commit memory, worktree guard, **credential leak scanner**
- Include Tier 2 hooks where stack tags match conditions (e.g., `has-env` → .env blocker, `ruff` → linter-on-save)
- Write to `$PROJECT/.claude/hooks.json`

**Credential Leak Scanner (Tier 1 — always include):**
Before any subagent dispatch or subprocess spawn, scan for unallowlisted environment variables that could leak credentials into AI context. Inspired by Archon's env sanitization pattern:
```
SUBPROCESS_ENV_ALLOWLIST:
  - PATH, HOME, USER, SHELL, TERM, LANG, LC_*
  - BUILD_ENV, NODE_ENV, PYTHON_VERSION
  - CI, GITHUB_ACTIONS (CI detection only)

Block from AI context:
  - *_TOKEN, *_SECRET, *_KEY, *_PASSWORD, *_CREDENTIAL
  - AWS_*, STRIPE_*, OPENAI_*, ANTHROPIC_*
  - DATABASE_URL, REDIS_URL (connection strings with credentials)
```
Implementation: Pre-tool hook that scrubs process environment before spawning Claude subprocesses. Log `[REDACTED]` for any blocked var.

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
User says "implement X" / "fix Y"
        │
        ▼
   ┌─────────────────────────────────────────────┐
   │ Is this a BUG FIX?                           │
   │ (error report, regression, "broken",         │
   │  stack trace, bug issue reference)            │
   │                                               │
   │ YES → BUG PATH                                │
   │   Invoke /bug-fix skill                       │
   │   (Reproduce → Diagnose → Fix → Verify)       │
   │                                               │
   │ Is this a SMALL change?                      │
   │ (single file, no schema, no new endpoints)   │
   │                                               │
   │ YES → FAST PATH                               │
   │   1. Load defensive skill                     │
   │   2. Make the change                          │
   │   3. Run tests                                │
   │   4. Commit → done                            │
   │                                               │
   │ Has EXISTING PLAN file or PRP?                │
   │                                               │
   │ YES → PLAN PATH                               │
   │   1. Read the plan/PRP file                   │
   │   2. Skip to Phase 5 (Implementation)         │
   │   3. Execute the plan                         │
   │                                               │
   │ Is there a NEAR-IDENTICAL existing feature?   │
   │ (quick grep/glob check — 2-3 searches max)    │
   │                                               │
   │ YES → CLONE PATH                              │
   │   1. Read the existing feature code           │
   │   2. Clone + adapt (skip Phases 2-4)          │
   │   3. TDD the differences                      │
   │   4. Run Phase 6 review → done                │
   │                                               │
   │ Does this touch ONLY 1-2 files?               │
   │ (no new endpoints, no schema, no new models)  │
   │                                               │
   │ YES → LITE PATH                               │
   │   1. Read the files directly (skip Phase 2    │
   │      parallel explorers)                      │
   │   2. Inline architecture (skip Phase 4        │
   │      parallel architects — write plan inline) │
   │   3. TDD implementation                       │
   │   4. Run Phase 6 review → done                │
   │                                               │
   │ Is this EXPLORATORY?                          │
   │ ("try this", "experiment with", "spike",      │
   │  "prototype", "proof of concept",             │
   │  "see if X works")                            │
   │                                               │
   │ YES → EXPLORE PATH                            │
   │   1. Create explorations/<topic>/ directory   │
   │   2. Write README.md (goal, hypothesis,       │
   │      success criteria)                        │
   │   3. Code freely — no TDD, no Phase 6 review │
   │   4. Defensive patterns still loaded,         │
   │      secret detection + lint still active     │
   │   5. At decision point:                       │
   │      a. Graduate → full workflow from Phase 4 │
   │         (exploration = Phase 2 input)         │
   │      b. Archive → /session-handoff --abandon  │
   │                                               │
   │ NO to all → FULL WORKFLOW (continue)           │
   └─────────────────────────────────────────────┘
```

**Path criteria:**
- **Bug path:** Error report, regression, stack trace, "fix this bug", GitHub issue tagged as bug. Routes to `/bug-fix` skill — the dedicated bug fix orchestrator.
- **Fast path:** Typo fix, one-line change, config tweak, single-file edit with no ripple effects
- **Clone path:** Feature X already exists and you're building Feature X' (e.g., "add a delete endpoint" when create/update endpoints already exist)
- **Explore path:** User wants to test an idea before committing to the full workflow. Signals: "try this", "experiment with", "spike", "prototype", "proof of concept", "see if X works". Quality bar is 60/100 (no TDD, no Phase 6 review). Graduation: "this works, let's ship it" → exploration findings become Phase 2 input, skip parallel explorers, flow into normal pipeline from Phase 4. Archive: invoke `/session-handoff --abandon` to document what was tried and why it was abandoned.
- **Lite path:** Contained change touching 1-2 files — doesn't justify 5+ parallel subagents
- **Full workflow:** Everything else. If in doubt, use the full workflow.

### Artifact Requirements by Scale

Each path produces different artifacts. This table makes explicit what each path requires:

| Path | Files Touched | PRP | Design Doc | Work Plan | Test Skeletons | Review Tiers |
|------|---------------|-----|------------|-----------|----------------|--------------|
| **Bug** | 1-5 | No | No | No | No (test in Step 1) | Tier 1-3 (via /bug-fix) |
| **Fast** | 1 | No | No | No | No | Tests only |
| **Clone** | 1-3 | No | No | Inline | No | Tier 1-2 |
| **Lite** | 1-2 | No | Inline | Inline | No | Tier 1-3 |
| **Full** | 3+ | Optional | Yes | Yes | Yes (Phase 4d) | All tiers |

**Reading the table:**
- "Inline" means the artifact is written directly in the conversation, not as a separate doc.
- "Test Skeletons" refers to Phase 4d acceptance test generation (Full path only — smaller changes don't benefit from pre-generated skeletons).
- PRP is optional even on Full path — only export when the feature spans sessions or has 3+ integration points.

---

## Phase 2: Exploration (Executor + Advisor)

The **executor (Sonnet)** explores the codebase directly — reading files, tracing patterns, mapping architecture. No parallel explorer subagents. The executor builds firsthand context that persists naturally through Phases 3-5, eliminating the old context hydration gate.

### Step 0: Prior Knowledge Check (Token Saver)

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

### Step 1: Compressed Codebase Context (Token Saver)

Generate token-efficient codebase maps before deep exploration:

```bash
# Signatures only — function/class headers without bodies
python scripts/generate_repo_outline.py app/services/ --max-depth 2

# Full compressed context — entire codebase packed into minimal tokens
repomix --compress --output .repomix-output.txt
```

For small/familiar codebases, `generate_repo_outline.py` alone is sufficient. For large or unfamiliar codebases, always run both.

### Step 2: Executor Explores Directly

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

### Step 3: Advisor Checkpoint — Exploration Review

<ADVISOR-CHECKPOINT>
After the executor finishes exploring, call the **Opus advisor** to review what was found and identify gaps.
</ADVISOR-CHECKPOINT>

Dispatch an Opus advisor with `model: "opus"`, `subagent_type: "general-purpose"`:

**Advisor prompt template:**
```
I'm building [feature description]. I've explored the codebase and found:

**Key files read:**
- [file1] — [role/pattern observed]
- [file2] — [role/pattern observed]
- ...

**Patterns discovered:**
- [pattern 1]
- [pattern 2]

**Integration points:**
- [system 1]
- [system 2]

**My concerns:**
- [concern 1]
- [concern 2]

QUESTION: What am I missing? What should I investigate deeper
before moving to clarification and architecture?
```

**Act on advisor response:** If the advisor identifies gaps, explore those areas before proceeding. If the advisor confirms coverage is sufficient, move to Phase 3.

**Why this works better than parallel explorers:** The executor has firsthand knowledge of every file it read — naming conventions, error patterns, data shapes, integration seams. This context persists naturally into Phases 3 and 4 without any hydration step. The Opus advisor adds strategic depth without requiring Opus to do the expensive file I/O work.

---

## Phase 3: Clarification + Requirements (Hard Gate)

<HARD-GATE>
All ambiguities must be resolved and requirements formalized before architecture work begins.
</HARD-GATE>

### Step 1: Resolve Ambiguities

Review exploration findings against the original request. Identify **every** underspecified aspect:

- **Edge cases** — What happens when input is empty, duplicated, or malformed?
- **Error handling** — What should the user see when things fail?
- **Integration points** — Which existing systems does this touch?
- **Scope boundaries** — What is explicitly NOT included?
- **Performance** — Will this hit large datasets or high concurrency?
- **Backward compatibility** — Does this change existing behavior?

Present an organized question list to the user. Group questions by category. Wait for answers before proceeding.

**If no ambiguities exist** (rare — usually means the request is very well-specified), state that explicitly and proceed to Step 2.

### Step 2: Synthesize Structured Requirements

After all ambiguities are resolved, synthesize the answers into a structured requirements document. This is the `$requirements` output contract — it flows downstream to Phase 4 (architecture references it), Phase 4c (validates plan coverage against it), and Phase 6 (reviewers check adherence).

**Format:**

```
## Requirements: <Feature Name>

### User Stories
- As a [role], I want [feature], so that [benefit]
(1-5 stories covering the core functionality)

### Acceptance Criteria (EARS format)
- WHEN [trigger] IF [condition] THEN [outcome]
(Every testable behavior — these become the coverage checklist in Phase 4c)

### Scope Boundaries
- IN: [explicitly included]
- OUT: [explicitly excluded]
(OUT items are enforced as scope creep detection in Phase 4c)

### Edge Cases (resolved)
- [case]: [resolution]
(Each resolved edge case from Step 1 — checked for test coverage in Phase 4c)

### Non-Functional Requirements (if applicable)
- Performance: [constraints]
- Backward compat: [notes]
```

**Present to user for approval.** The structured requirements are the contract for everything downstream. If the user provides feedback, revise and re-present.

```
◆ USER APPROVES structured requirements before architecture ◆
```

### Optional: Export Context Packet (PRP)

After requirements are approved, optionally save a **Product Requirement Prompt (PRP)** — a reusable context packet that survives across sessions.

**Trigger conditions** (export if ANY apply):
- Feature is complex enough to span multiple sessions
- User says "save context", "export this", or "I'll continue later"
- Task involves 3+ integration points or schema changes

**PRP format** — write to `plans/PRP-<feature-slug>.md`:

```
# PRP: <Feature Name>
**Created:** <date> | **Status:** ready-for-implementation

## Requirements
(Reference or inline the structured $requirements from Step 2)

## Codebase Intelligence
- **Key files:** <5-10 files from exploration with their roles>
- **Patterns to follow:** <discovered conventions from Phase 2>
- **Integration points:** <systems this touches>

## Constraints & Edge Cases
(Reference the Edge Cases section from $requirements)

## Ruled Out
- <approach/tool/path> — <why it failed or was abandoned>
- <investigation that hit a dead end> — <what was discovered>
<!-- Prevents future sessions from re-exploring dead ends -->

## Implementation Notes
- <API docs fetched (if applicable)>
- <defensive patterns required>
- <test strategy hints>
```

**How it's consumed:** Phase 1 Discovery detects PRP files via the PLAN PATH branch. A PRP provides richer context than a bare plan — it includes the codebase intelligence that would otherwise require re-running Phase 2 exploration.

If not triggered, skip — most single-session features don't need this.

---

## Phase 4: Architecture (Executor Drafts + Advisor Critiques)

The **executor (Sonnet)** drafts two competing architecture options. It has full context from Phase 2 exploration — it read the files firsthand, knows the patterns, understands the integration points. No architect subagents needed.

### Step 0: Cross-Document Consistency Check

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

### Step 1: Executor Drafts Two Options

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

### Step 2: Advisor Checkpoint — Architecture Critique

<ADVISOR-CHECKPOINT>
Before presenting architectures to the user, call the **Opus advisor** to stress-test both options.
</ADVISOR-CHECKPOINT>

Dispatch an Opus advisor with `model: "opus"`, `subagent_type: "general-purpose"`:

**Advisor prompt template:**
```
I'm designing architecture for [feature]. I have two options:

**Option A (Simplicity):**
[summary of option A with files and trade-offs]

**Option B (Clean Separation):**
[summary of option B with files and trade-offs]

**Codebase context:**
- Key patterns from exploration: [patterns]
- Integration points: [systems]
- Resolved requirements: [from Phase 3]

QUESTIONS:
1. What blind spots exist in each option?
2. Which trade-offs am I underweighting?
3. Is there a hybrid approach that captures the best of both?
4. Any architectural risks I'm not seeing?
```

**Act on advisor response:** Revise the options based on advisor critique. If the advisor identifies a clear winner or a superior hybrid, note that in the presentation.

### Step 3: Present to User

Present both options (post-advisor-refinement) to the user with the advisor's analysis included:
- The two options with trade-offs
- Advisor's critique and any identified risks
- Advisor's recommendation (if any)

```
◆ USER CHOOSES architecture (A, B, or hybrid) ◆
```

### Step 4: Write Implementation Plan

After user chooses, write a structured plan using the `writing-plans` skill:
- Numbered steps with specific files and changes
- Test requirements per step
- Dependencies between steps marked clearly

### Step 5: Advisor Checkpoint — Plan Stress-Test

<ADVISOR-CHECKPOINT>
Every implementation plan must pass Opus advisor review before user approval. This catches logic errors, missing edge cases, and scope creep that the executor's own drafting might miss.
</ADVISOR-CHECKPOINT>

Dispatch an Opus advisor with `model: "opus"`, `subagent_type: "general-purpose"`:

**Advisor prompt template:**
```
Review this implementation plan for [feature]:

[the full plan]

**Chosen architecture:** [summary]
**Key codebase patterns:** [from exploration]
**Resolved requirements:** [from Phase 3]

Find:
1. Logic errors or impossible steps
2. Missing edge cases from requirements
3. Integration risks with existing systems
4. Scope creep beyond what was asked
5. Steps that should be reordered for safety
```

**Triage advisor findings:**
- **CRITICAL** — Must fix before approval (architectural flaw, missing requirement, security gap)
- **HIGH** — Should fix before approval (scope creep, untested edge case, fragile integration)
- **MEDIUM** — Note for implementation phase (style preference, minor optimization)
- **LOW** — Informational only (alternative approaches, future considerations)

Revise plan to address HIGH+ findings. Present consolidated findings to user alongside the plan.

```
◆ USER APPROVES final plan (post-advisor-review) before implementation ◆
```

---

## Phase 4c: Pre-Implementation Plan Verification

<HARD-GATE>
After user approves the plan and before any implementation begins, verify the plan's factual claims against the actual codebase. The Phase 4b stress-test catches logical issues — this step catches factual inaccuracies (stale file paths, renamed functions, changed API contracts).
</HARD-GATE>

The executor (Sonnet) runs a mechanical verification pass — no subagent needed:

```
For each file path in the plan:
  → Does the file exist? (glob/ls)
  → Are the referenced functions/classes/methods actually in that file? (grep)
  → If a file is listed as "create new": does a file with that name already exist?

For each pattern claim ("follows existing X pattern"):
  → Grep to confirm the pattern exists in the referenced location
  → If the pattern was discovered in Phase 2 but the file has since changed
    (unlikely but possible in multi-session work), flag it

For each API contract claim (endpoint signatures, model fields, service methods):
  → Verify the signature/fields exist as described
  → Check parameter types and return types match

For integration points:
  → Verify the interface hasn't changed since Phase 2 exploration
  → If another session's work landed between Phase 2 and now (e.g., a merged PR),
    check for breaking changes in shared interfaces
```

### Requirements Coverage Validation

Cross-reference `$requirements` (from Phase 3) against `$plan` to catch gaps before implementation:

```
ACCEPTANCE CRITERIA COVERAGE:
  For each acceptance criterion in $requirements:
    → Is there at least one plan step that addresses it?
    → Is there a test skeleton (Phase 4d) or test note for it?
    → If not: flag as UNCOVERED CRITERION

SCOPE BOUNDARY ENFORCEMENT:
  For each scope boundary (OUT items) in $requirements:
    → Does any plan step implement something marked OUT?
    → If yes: flag as SCOPE CREEP

EDGE CASE COVERAGE:
  For each edge case in $requirements:
    → Is it addressed in the plan (either in a step or as a test)?
    → If not: flag as UNTESTED EDGE CASE
```

**Outcome:**
- **All claims verified + all requirements covered** → Proceed to Phase 4d (test skeletons) or Phase 5.
- **Minor mismatches** (renamed variable, moved function) → Fix the plan silently. Log the corrections.
- **Minor coverage gaps** (1-2 criteria clearly handled implicitly by existing plan steps) → Log and proceed.
- **Material mismatches** (deleted file, changed API contract, restructured module) → Re-present the affected plan steps to the user with corrections. Get re-approval before proceeding.
- **Material coverage gaps** (uncovered acceptance criteria, scope creep detected, untested edge cases) → Present gaps to user, revise plan to address them, get re-approval before proceeding.

**Why this exists:** Plans are drafted against Phase 2 exploration findings. Between exploration and implementation, the codebase can drift (especially in multi-session work or when other contributors merge changes). A 30-60 second mechanical check prevents building on false assumptions — the most expensive kind of bug to find in Phase 6.

**Skip condition:** Fast path, clone path, and lite path skip this (the executor reads files immediately before editing them — no drift window). Only runs on the Full workflow path where there's a meaningful gap between exploration and implementation.

---

## Phase 4d: Acceptance Test Skeleton Generation

<SKIP-CONDITION>
Skip for Fast path, Clone path, and Lite path. Only run on Full workflow where the plan has explicit acceptance criteria.
</SKIP-CONDITION>

Before Phase 5 TDD begins, generate test skeletons from the approved plan's acceptance criteria. This pre-seeds the Red phase of TDD — implementers start with a clear contract instead of writing tests from scratch.

### How It Works

```
1. Extract testable acceptance criteria from the approved plan:
   - Each plan step's "test requirements" section
   - Edge cases resolved in Phase 3 ($requirements)
   - Any "verify that X" statements in the plan

2. For each criterion, generate a skeleton:

   def test_<criterion_slug>():
       """AC: <acceptance criterion text from plan>"""
       # Phase 5 will implement this test
       raise NotImplementedError("Skeleton from Phase 4d — implement in Phase 5")

3. Group skeletons by the test file they belong to:
   - Match to existing test files when the plan modifies existing code
   - Create new test files when the plan creates new modules

4. Write skeleton files to the test directory
   - Use the project's existing test structure and naming conventions
   - Import the modules referenced in the plan (even if they don't exist yet)
```

### What Phase 5 Does With Skeletons

Phase 5 TDD treats each skeleton as a pre-seeded Red test:
1. **Fill in** the skeleton with concrete assertions (the Red test)
2. **Implement** to make it pass (Green)
3. **Refactor** as needed
4. **Delete** any skeleton that turns out to be redundant or incorrectly scoped

The skeletons are a starting point, not a constraint. Phase 5 can modify, split, or remove them as understanding deepens during implementation.

### Why Pre-Generate

- **Coverage contract:** The plan says "test X" — now there's an actual test stub enforcing that. Harder to accidentally skip.
- **Faster Red phase:** Writing the test function signature, docstring, and imports is mechanical work. Pre-generating it lets Phase 5 focus on the interesting part (what to assert).
- **Review signal:** Phase 6 reviewers can check whether every skeleton was either implemented or explicitly deleted with justification.

---

## Context Management Strategy

The full workflow (Phases 0-6) is a long-running agentic session that reads 8-15+ files, dispatches advisor calls, and runs multi-tier reviews. Without active context management, the session will hit limits. This section defines three composable strategies (from the Claude Cookbook's context engineering patterns) plus pruning rules for subagent dispatch.

### Strategy 1: Tool-Result Clearing (Automatic, Zero-Cost)

Phase 2 reads 8-15 files. By Phase 5, those old file reads are stale context bloat — the executor already synthesized the relevant patterns. Tool-result clearing drops old Read/Grep results while keeping the tool_use records (so the model remembers *what* it read and *why*).

**When to apply:** Automatically during Phases 4-6 when context grows.

**Configuration (mental model for executor behavior):**
```
Trigger:     Context exceeds ~50K tokens (roughly end of Phase 2)
Keep:        4 most recent tool results (active working set)
Exclude:     Memory tool results (MEMORY.md reads must survive)
Clear:       At least 10K tokens per clearing event (avoid thrashing)
```

**What gets cleared vs retained:**
- **Cleared:** Content of old file reads, grep results, API responses (replaced with `[cleared — re-read if needed]`)
- **Retained:** The tool_use records (model knows it read the file and what input it used), all agent reasoning, user messages, advisor responses

**Why this works:** Phase 2 file reads are re-fetchable — if Phase 5 needs a file again, it can re-read it. The executor's synthesis of those files (patterns documented, concerns identified) persists naturally in the conversation.

### Strategy 2: Phase-Aware Compaction (At Threshold)

When dialogue and reasoning accumulate beyond what clearing handles, compact the conversation with phase-specific preservation instructions.

**When to apply:** When context exceeds ~80% capacity despite clearing (typically mid-Phase 5 on large features).

**Soft threshold (proactive):** At ~60% capacity, mentally prepare a session summary in the background — note current phase, completed steps, key decisions, active working files.

**Hard threshold (swap):** At ~80% capacity, compact the conversation using phase-specific instructions:

```
After Phase 2 (exploration complete):
  Preserve: key file paths + their roles, discovered patterns,
            integration points, concerns identified
  Drop:     raw file contents, grep output, repomix output

After Phase 4 (plan approved):
  Preserve: approved plan (numbered steps), chosen architecture,
            resolved requirements, edge cases, API contracts
  Drop:     rejected architecture details, advisor conversation
            transcripts, exploration file reads

During Phase 5 (mid-implementation):
  Preserve: plan with completion status per step, test results,
            files modified so far, current step context,
            any advisor guidance received
  Drop:     completed step details (code is in git), old test output

During Phase 6 (review):
  Preserve: git diff summary, plan, reviewer findings (HIGH+),
            fix actions taken
  Drop:     PASS findings, Tier 4 haiku output (low signal)
```

**The key insight:** Different phases have different "what must survive" profiles. A generic compaction prompt loses critical details; phase-specific prompts preserve exactly what the next phase needs.

### Strategy 3: Phase Output Contracts (Explicit Data Flow)

Each phase produces a defined output that downstream phases consume. Inspired by Archon's `$nodeId.output` variable substitution pattern — making data flow between phases explicit rather than implicit.

**Phase output contracts:**

| Phase | Output Name | Contains | Consumed By |
|-------|-------------|----------|-------------|
| Phase 2 | `$exploration` | Key file paths + roles, patterns discovered, integration points, concerns | Phases 3, 4, advisor prompts |
| Phase 3 | `$requirements` | Structured document: user stories, acceptance criteria (EARS), scope boundaries (IN/OUT), resolved edge cases, non-functional requirements | Phases 4, 4c, 5, reviewer prompts |
| Phase 4 | `$architecture` | Chosen architecture summary, component responsibilities, data flow | Phase 5 |
| Phase 4b | `$plan` | Approved numbered implementation plan with dependencies | Phase 4c, 4d, Phase 5, Phase 6 reviewers |
| Phase 4c | `$verified_plan` | Plan with all factual claims verified against codebase (or corrections applied) | Phase 4d, Phase 5 |
| Phase 4d | `$test_skeletons` | Test skeleton file paths and criterion-to-test mapping | Phase 5 (TDD pre-seeds) |
| Phase 5 | `$diff` | Git diff of all changes + files modified list | Phase 6 reviewers |

**How to use:** When dispatching a subagent, reference the contract explicitly. Don't pass raw conversation — pass the named output:

```
Phase 5 subagent receives:
  $verified_plan — steps assigned (use $verified_plan when 4c ran, else $plan)
  $exploration   — key file paths + patterns (not full contents)
  $requirements  — resolved edge cases and constraints
  $test_skeletons — skeleton file paths + criterion mapping (Full path only)
  Defensive patterns to apply

Phase 6 reviewer receives:
  $diff          — git diff (primary input)
  $plan          — for adherence checking
  Project conventions (from CLAUDE.md / loaded skills)
```

**What to NEVER pass to subagents:**
- Advisor conversation transcripts
- Rejected architecture option details
- Phase 0 skill loading decisions
- Raw clarification Q&A (pass `$requirements` instead)

**Why explicit contracts matter:** When pruning is described as "pass only what they need," the executor has to decide what that means every time. Named outputs make it mechanical — the contract defines the interface between phases, just as function signatures define interfaces between modules.

### Composing the Strategies

The three strategies compose naturally across the workflow:

```
Phase 0-2:  Context grows as files are read
            → Tool-result clearing fires at ~50K tokens
            → Old file reads cleared, patterns retained

Phase 3-4:  Advisor calls add context
            → Tool-result clearing continues
            → If approaching 80%, compact with Phase 4 instructions

Phase 5:    Implementation generates code + test output
            → Tool-result clearing drops old test runs
            → Subagent pruning for parallel dispatch
            → If approaching 80%, compact with Phase 5 instructions

Phase 6:    Reviewers generate findings
            → Subagent pruning for reviewer dispatch
            → Tool-result clearing drops old reviewer outputs
            → Compact only if needed (Phase 6 is usually the end)
```

---

## Phase 5: Implementation (TDD + Defensive Patterns)

<HARD-GATE>
User must approve the plan before any implementation begins.
</HARD-GATE>

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
   - If test fails and the error is NOT self-explanatory:
     invoke /investigator with the failure as input.
     Review the evidence matrix BEFORE attempting a fix.
     (Prevents fix-retry loops on complex failures.)

4. Run static analysis on changed files (catch issues early):
   semgrep --config=.semgrep.yml <changed-files>
   ast-grep scan <changed-directory>

   Fix any ERROR-level issues before proceeding.

5. Mark TodoWrite item complete

6. Inter-task verification gate (proactive, not just reactive):
   Run full test suite + lint + build check BEFORE starting next task.
   Catches regressions early. See subagent-driven-development skill
   for full gate protocol. Skip full suite for Task 1 or trivial tasks.
   If gate fails → fix regression → re-verify → then proceed.
```

### Fresh Context for Long Implementation Loops

When a plan has 5+ steps, context accumulates across the TDD cycle — old test output, stale file reads, and prior step reasoning bloat the window. Inspired by Archon's "fresh context per iteration" pattern:

**When to apply:** Plan has 5+ sequential steps AND context exceeds ~60% capacity mid-implementation.

**How it works:**
```
Steps 1-3: Execute normally (context is fresh)
Step 4+:   If context is growing heavy:
  1. Capture step completion state:
     - Plan with checkmarks per completed step
     - Files modified so far (paths only)
     - Current step number and requirements
     - Any advisor guidance still relevant
  2. Trigger phase-aware compaction (Strategy 2)
     with Phase 5 preservation rules
  3. Continue with clean working context

For parallel subagent dispatch:
  Each subagent starts with FRESH context:
  - The specific step(s) assigned to it
  - Key file paths + patterns (not full file contents)
  - Defensive patterns to apply
  No prior step history — the plan is the contract.
```

**Why this matters:** A 10-step plan where each step reads 3 files and runs tests accumulates ~100K tokens of stale context by step 7. Fresh context per subagent (or compaction at the threshold) keeps each step operating at peak quality instead of degrading as context fills.

### Optional: Advisor Checkpoint — Mid-Implementation

<ADVISOR-CHECKPOINT>
Call the Opus advisor during implementation only when the executor hits a **genuinely ambiguous decision point** — not every step.
</ADVISOR-CHECKPOINT>

**When to call:**
- A step involves a non-obvious integration pattern (multiple valid approaches)
- The executor isn't sure which existing pattern to follow (conflicting precedents)
- A step's implementation diverges from the plan in a way that might affect later steps

**When NOT to call:**
- Routine implementation following established patterns
- Standard TDD cycles with clear requirements
- Steps where the plan is unambiguous

**Advisor prompt:** Keep it focused — state the specific decision, the options considered, and why it's ambiguous. The advisor returns a recommendation; the executor acts on it.

### Parallel Subagent Dispatch (For Independent Steps)

When the plan has 3+ steps with no dependencies between them:

```
Use subagent-driven-development skill:
  → Dispatch parallel implementation agents with model: "sonnet"
  → Each follows the same TDD + defensive pattern
  → Merge results when all complete
```

Only parallelize truly independent work — shared state or sequential dependencies must stay sequential.

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

---

## Phase 5.5: Self-Reflection (RARV Reflect)

Before dispatching expensive reviewers, the executor pauses to self-assess. Inspired by loki-mode's RARV (Reason-Act-Reflect-Verify) cycle — this is the "Reflect" step that sits between implementation (Act) and review (Verify).

### The Reflect Checklist

Run through these questions. If any answer is "no" or "unsure", fix before Phase 6:

1. **Plan adherence** — Does the diff match every numbered step in the plan? Any steps skipped or partially done?
2. **Requirement coverage** — Does `$requirements` from Phase 3 have full coverage? Check each resolved edge case.
3. **Pattern consistency** — Does new code follow the patterns discovered in `$exploration`? Any deviations?
4. **Test quality** — Do tests verify behavior (not implementation)? Are edge cases from Phase 3 tested?
5. **Obvious issues** — Read the full diff as if seeing it for the first time. Any code smells, missing error handling, or hardcoded values?

### How to Execute

```
git diff main --stat           # What files changed
git diff main                  # Full diff review
```

Read the diff. For each file changed, mentally trace the happy path AND the error path. Note issues.

### Outcome

- **All clear** → Proceed to Phase 6
- **Issues found** → Fix them. Re-run affected tests. Then proceed.
- **Architectural concern** → Call Opus advisor (Mid-Implementation checkpoint) before proceeding

### Why This Saves Money

A 2-minute self-check catches ~40% of the issues that Tier 1-2 reviewers would find. At ~$0.08-0.40 per review round, catching these early avoids expensive re-review cycles.

---

## Phase 6: Quality + Finish

### 5-Tier Cascading Review (Registry-Driven)

Reviews are structured as a cascade: Tier 1 runs first (broad, fast), then specialized agents fill gaps. Reviewer selection is driven by `reviewer-registry.json` — a declarative config file that maps file patterns to reviewer agents.

**How it works:**

1. Read `reviewer-registry.json` (from project `.claude/` first, then global `~/.claude/hooks/claude-flow/`)
2. Get the diff file list: `git diff --name-only HEAD~1`
3. Partition reviewers: `always` tier runs unconditionally, `conditional` tier runs when `file_patterns` match files in the diff (and optionally `content_pattern` count exceeds `threshold`)
4. Group by `cascade_tier` — Tier 1 runs first, wait for results, then Tier 2+ run in parallel within their tier
5. Reviewers with `dynamic_prompt: true` get context-specific prompts generated by the executor based on the actual diff (see below)

**Registry format** (see `reviewer-registry.json` at repo root):

```json
{
  "id": "migration-reviewer",
  "tier": "conditional",
  "cascade_tier": 3,
  "file_patterns": ["alembic/**/*.py", "**/migrations/**/*.py"],
  "subagent_type": "migration-reviewer",
  "model": "sonnet",
  "description": "Alembic migration safety checks"
}
```

**Adding project-specific reviewers:** Drop a `reviewer-registry.json` in your project's `.claude/` directory. Project reviewers are merged with (and override by `id`) the global registry.

**Default reviewers (bundled):**

| Cascade Tier | ID | Model | Condition |
|--------------|----|-------|-----------|
| 1 | `coderabbit` | sonnet | Always — consolidated first pass |
| 2 | `silent-failure-hunter` | sonnet | Always — swallowed errors |
| 2 | `security-reviewer` | sonnet | Always — auth, injection, OWASP |
| 2 | `test-coverage-analyzer` | sonnet | Always — test gaps |
| 3 | `migration-reviewer` | sonnet | Alembic/migration files in diff |
| 3 | `google-api-reviewer` | sonnet | Google/calendar files + content match |
| 3 | `async-reviewer` | sonnet | 3+ async patterns in Python files |
| 3 | `type-design-analyzer` | haiku | Models/schemas/types files |
| 3 | `api-doc-auditor` | haiku | Route/API/endpoint files |
| 4 | `invariant-checker` | haiku | Models/services/routes (dynamic prompt) |
| 4 | `defensive-verifier` | haiku | Templates/static/routes/services (dynamic prompt) |

**Dynamic prompt generation (Tier 4):** Before dispatching reviewers with `dynamic_prompt: true`, the executor generates context-specific review prompts based on the actual diff:

```
For Defensive Verifier:
  "This feature added [3 new route handlers and a modal form].
   Check specifically for:
   - Guard clauses on the [route parameter validation]
   - Try-catch with user feedback in the [modal submit handler]
   - Loading/error/success states in the [form component]
   Skip checking: [unchanged utility files, test files]"
```

**Why dynamic prompts:** Static prompts make Haiku scan the entire diff for every possible pattern. Dynamic prompts focus Haiku on the 2-3 specific patterns most likely to appear in *this* diff, reducing false positives and improving signal quality.

**Tier 5 — Design Review (when UI was modified):**

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

### Review-Fix-Recheck Loop (Evaluator-Optimizer Pattern)

Findings from all tiers are collected, deduplicated, and triaged. But **fixing is not a single pass** — it follows an iterative evaluate→fix→re-evaluate loop inspired by the Claude Cookbook's evaluator-optimizer pattern.

```
Collect all findings across tiers
        │
        ▼
  Deduplicate + triage (CRITICAL / HIGH / MEDIUM / LOW)
        │
        ▼
  ┌─────────────────────────────────────────┐
  │ For each HIGH+ finding:                  │
  │                                          │
  │   1. Fix the issue                       │
  │   2. Re-run the SPECIFIC reviewer        │
  │      that flagged it (not all reviewers) │
  │   3. Did it pass?                        │
  │      YES → mark resolved, next finding   │
  │      NO  → fix again (max 3 iterations)  │
  │      3 failures → escalate to user       │
  │                                          │
  │ Design Review Blockers and High-Priority │
  │ follow the same loop.                    │
  └─────────────────────────────────────────┘
        │
        ▼
  Post summary to user:
    - Findings by tier and severity
    - Fixes applied + verification status
    - Any escalated items needing user decision
```

**Why re-run the specific reviewer:** A fix for a security issue might introduce a silent failure. Re-running only the flagging reviewer keeps the loop fast (seconds, not minutes) while confirming the fix actually resolved the issue. Cross-cutting regressions are caught by the verification gate later.

**Iteration limit:** Max 3 fix attempts per finding. If a fix doesn't resolve the issue after 3 tries, escalate to the user with the finding, the attempted fixes, and why they didn't work. Don't loop forever.

**MEDIUM/LOW findings:** Log for awareness but don't fix automatically. Present to user in the summary for their judgment.

### Cross-Cutting Synthesis (Orchestrator Pattern)

After all review tiers complete and fixes are applied, run a single synthesis pass. Individual reviewers catch domain-specific issues but can miss cross-cutting concerns that span multiple reviewers' domains.

Dispatch a **sonnet** general-purpose agent with this prompt:

```
You are reviewing the consolidated findings from a multi-tier code review.
Here are the findings from each reviewer tier:

[Tier 1 - CodeRabbit]: [findings summary]
[Tier 2 - Specialists]: [findings summary]
[Tier 3 - Conditional]: [findings summary]
[Tier 4 - Lightweight]: [findings summary]
[Tier 5 - Design]: [findings summary]

And the git diff being reviewed: [diff summary]

Identify cross-cutting issues that individual reviewers may have missed:
1. Are there contradictory findings between reviewers?
2. Do the fixes for one finding create issues in another domain?
3. Is there an architectural-level concern that no single reviewer would catch?
4. Overall health assessment: is this feature ready to ship?

Be concise. Only report issues not already covered by individual reviewers.
If everything looks clean, say so in one sentence.
```

**Skip condition:** If all tiers returned clean (no HIGH+ findings), skip synthesis — there's nothing to cross-reference.

### Post-Review Simplifier

After fixing review issues, run a single code-simplifier pass before the verification gate:
- Dispatch `code-simplifier:code-simplifier` (inherits **opus** per plugin spec)
- Scope: only files modified during this feature
- Accept changes only if tests still pass afterward
- Skip for trivial changes (single-file edits, config tweaks)

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

### Verification Gate

Invoke `verification-before-completion` skill:
- All tests pass?
- No unintended file changes?
- Implementation matches the original request?
- No regressions in existing functionality?
- Static analysis passes (no ERROR-level issues)?
- **Workflow regression check:** If this session modified the workflow skill itself (e.g., added a skip-condition, changed a reviewer tier, updated an advisor prompt), verify that existing passing behaviors are preserved — don't optimize for the current feature at the expense of the general case

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
- **Workflow trace:** Which phases caught which issues? (from Workflow Retrospective)
- **Failure tags:** What behavioral categories appeared? (from Workflow Failure Taxonomy)
- **Workflow improvement proposal:** One scoped change to the workflow, if any emerged

### Workflow Retrospective (Self-Improvement Signal)

After completing a feature, capture structured workflow metrics. This is the "trace" that enables iterating on the workflow itself — not just the code.

**Capture these metrics (mental model, not a file):**

1. **Phase Effectiveness** — Which phase caught each issue?
   - Issues caught in Phase 2 (exploration) → working as designed
   - Issues caught in Phase 4b (plan stress-test) → advisor is earning its keep
   - Issues caught in Phase 6 (review) → should Phase 3 or 4b have caught this earlier?
   - Issues caught post-merge → review-escape, needs workflow fix

2. **Failure Tags** — Apply taxonomy tags (from Workflow Failure Taxonomy) to every issue encountered during the run. Note which phase caught it.

3. **Workflow-Level Questions** — Feed these into session-learnings:
   - "Did any phase feel wasted for this type of feature?" → candidate for skip-condition
   - "Did any phase miss something another phase caught?" → coverage gap
   - "Did the advisor add value at each checkpoint?" → checkpoint tuning
   - "Were review tiers appropriately scoped?" → reviewer calibration

4. **One-Change Principle** — If this retrospective suggests a workflow improvement, scope it to ONE targeted change (inspired by Better-Harness's "one change at a time to avoid confounding"). Examples:
   - Add a specific instruction to the advisor prompt template
   - Add a skip-condition to a review tier
   - Add an entry to the Common Mistakes table
   Don't batch multiple workflow changes — each should be validated independently.

**Pass to session-learnings:** When invoking the session-learnings skill, include:
- The failure tags applied during this run
- Which phase caught each issue (the "trace")
- Any workflow-level improvement suggestion (scoped to one change)

---

## Quick Reference: All Phases

| Phase | Name | Model | Key Pattern | Gate |
|-------|------|-------|-------------|------|
| 0 | Context | executor | Trigger matrix → load relevant skills only | None |
| 1 | Discovery | executor | 6-path triage (bug/fast/clone/plan/lite/full) | Auto |
| 2 | Exploration | executor + **advisor** | Executor explores directly → advisor reviews gaps | **Advisor confirms coverage** |
| 3 | Clarification + Requirements | executor | Surface ambiguities + synthesize structured $requirements | **User approves requirements** |
| 4 | Architecture | executor + **advisor** | Executor drafts 2 options → advisor critiques | **User chooses** |
| 4b | Plan Stress-Test | **advisor** | Advisor reviews implementation plan for risks | **Advisor passes** |
| — | Context Management | — | Tool-result clearing → phase-aware compaction → subagent pruning | Auto |
| 5 | Implementation | executor (+ **advisor** optional) | TDD per step, advisor at complex decision points | Tests pass |
| 6 | Quality + Finish | **sonnet/haiku** | CodeRabbit first pass → cascading specialists → verify → commit | **Verification** |
| 6b | Retrospective | executor | Tag failures → trace phases → propose one workflow change | Auto |

## Agents Used Within This Workflow

### Advisor (Opus, On-Demand)

| Checkpoint | Phase | Question Focus | Required? |
|------------|-------|----------------|-----------|
| Exploration Review | 2 | "What am I missing?" | Yes |
| Architecture Critique | 4 | "What are the blind spots?" | Yes |
| Plan Stress-Test | 4b | "Find logic errors, scope creep" | Yes |
| Mid-Implementation | 5 | "Which pattern at this decision point?" | Optional |
| Strategic Pre-Review | 6 | "Does this fulfill requirements?" | Optional |

All advisor calls use `model: "opus"`, `subagent_type: "general-purpose"`.

### Review Agents (Phase 5-6)

| Agent | `subagent_type` | Phase | Trigger | Model |
|-------|-----------------|-------|---------|-------|
| Migration Reviewer | `migration-reviewer` | 5, 6 | Alembic files | sonnet |
| Google API Reviewer | `google-api-reviewer` | 5, 6 | Google API code | sonnet |
| Async Reviewer | `async-reviewer` | 5, 6 | async I/O code | sonnet |
| CodeRabbit | `coderabbit:code-reviewer` | 6 (T1) | Always | sonnet |
| Silent Failure Hunter | `pr-review-toolkit:silent-failure-hunter` | 6 (T2) | Always | sonnet |
| Security Reviewer | `security-reviewer` | 6 (T2) | Always | sonnet |
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | 6 (T2) | Always | sonnet |
| Type Design Analyzer | `pr-review-toolkit:type-design-analyzer` | 6 (T3) | New types/models | haiku |
| API Doc Auditor | `api-doc-auditor` | 6 (T3) | New/modified routes | haiku |
| Invariant Checker | `courierflow-invariant-checker` | 6 (T4) | Always (CF projects) | haiku |
| Defensive Verifier | `defensive-pattern-verifier` | 6 (T4) | Always | haiku |
| Design Reviewer | `general-purpose` | 6 (T5) | UI files modified | sonnet |
| Cross-Cutting Synthesizer | `general-purpose` | 6 (post-tiers) | If any HIGH+ findings | sonnet |
| Code Simplifier | `code-simplifier:code-simplifier` | 6 | After review fixes | opus |

## Skills Invoked Within This Workflow

| Skill | Where Used |
|-------|-----------|
| fetch-api-docs | Phase 5 (pre-implementation gate for external APIs) |
| coding-best-practices | Phase 0 (loaded), Phase 5 (applied) |
| defensive-ui-flows | Phase 0 (loaded), Phase 5 (applied) |
| defensive-backend-flows | Phase 0 (loaded), Phase 5 (applied) |
| writing-plans | Phase 4 (plan creation) |
| investigator | Phase 5 (on unexpected TDD failures — evidence-first before retrying) |
| executing-plans | Phase 5 (plan execution) |
| test-driven-development | Phase 5 (TDD per step) |
| subagent-driven-development | Phase 5 (parallel independent steps) |
| **coderabbit:review** | **Phase 6 Tier 1 (consolidated first-pass code review)** |
| verification-before-completion | Phase 6 (pre-finish check) |
| finishing-a-development-branch | Phase 6 (branch completion) |
| session-learnings | Phase 6 (capture discoveries) |

## Static Analysis & Context Tools (Automatic)

| Tool | Where Used | Purpose |
|------|------------|---------|
| `generate_repo_outline.py` | Phase 2 (pre-exploration) | Token-efficient signatures (targeted areas) |
| `repomix --compress` | Phase 2 (pre-exploration) | Full codebase compressed context (broad awareness) |
| `semgrep` | Phase 5 (per-step), Phase 6 (gate) | Semantic analysis, security checks |
| `ast-grep` | Phase 5 (per-step), Phase 6 (gate) | Structural anti-pattern detection |
| `pyright` | Phase 6 (gate) | Fast type checking |

## Skills Eliminated (Absorbed)

| Former Skill/Pattern | Absorbed Into |
|---------------------|---------------|
| Parallel Opus explorer subagents (x2-3) | **Executor explores directly** — Sonnet reads files firsthand, Opus advisor reviews at the end |
| Parallel Opus architect subagents (x2) | **Executor drafts architectures** — Sonnet proposes options, Opus advisor critiques them |
| Context hydration gate | **Eliminated** — executor already has firsthand context from doing the exploration |
| debate-team (Phase 4b) | **Replaced by Opus advisor plan stress-test** — same rigor, fewer moving parts |
| plancraft brainstorming | Phases 1-3 (discovery + exploration + clarification) |
| brainstorming skill | Phases 1-3 (interactive exploration replaces separate brainstorm) |
| Dual code-reviewer agents | Replaced by **CodeRabbit** (Phase 6 Tier 1) — single consolidated pass |

## Error Recovery

| Situation | Action |
|-----------|--------|
| Exploration misses key area | Re-explore; call advisor again with "I also found X, reassess" |
| Advisor identifies critical gap | Investigate the gap before proceeding |
| Architecture options both rejected | Ask user what they want different, executor re-drafts |
| Tests fail during implementation | Fix immediately, don't proceed to next step |
| Reviewer finds critical issue | Fix → re-run that specific reviewer → repeat (max 3x) → escalate to user if still failing |
| User wants to stop mid-workflow | Stop. Summarize state (phase, what's done, what's left). |
| Wrong architecture chosen | Revert to plan, re-architect with new constraints |

## Workflow Failure Taxonomy

Tag failures to behavioral categories when they occur. These tags feed into the Workflow Retrospective (Phase 6) and session-learnings to detect patterns across runs.

| Tag | Description | Example |
|-----|-------------|---------|
| `exploration-gap` | Phase 2 missed a key file, pattern, or integration point | Didn't find the existing validation util → duplicated logic |
| `architecture-miss` | Phase 4 options didn't account for a constraint | Neither option handled the existing caching layer |
| `clarification-skip` | Ambiguity wasn't surfaced in Phase 3 | Edge case discovered during implementation that should have been asked |
| `plan-gap` | Plan missing a step or misordering dependencies | Migration step listed after the code that depends on it |
| `plan-verification-miss` | Plan referenced stale file paths, renamed functions, or changed APIs that Phase 4c should have caught | Plan says "modify `get_user()` in `user_service.py`" but the function was renamed to `fetch_user()` |
| `review-escape` | Bug/issue shipped past Phase 6 review tiers | Silent failure not caught by any reviewer tier |
| `integration-failure` | Code works in isolation but breaks at integration points | Service call succeeds but caller doesn't handle new response shape |
| `regression` | Change broke previously working behavior | New route handler shadowed existing route |
| `tool-selection` | Wrong tool or pattern chosen for the job | Used raw SQL when the ORM had a built-in method |
| `over-engineering` | Built more than was needed | Added abstraction layer for a one-time operation |
| `under-specification` | Requirements were technically met but user intent was missed | Implemented delete but user wanted soft-delete |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Skipping Phase 0 context loading | Always load project context first |
| Exploring from scratch without checking prior knowledge | **Step 0:** Check MEMORY.md, PRPs, and Serena memories before exploring — prior sessions may have already mapped this area |
| Skipping Phase 4c plan verification | Plans reference files and functions from Phase 2 exploration — the codebase can drift between exploration and implementation. Always verify factual claims before coding. |
| Jumping to fixes without evidence | When Phase 5 TDD hits unexpected failures, use `/investigator` to collect evidence before retrying — the first hypothesis is usually wrong for complex bugs |
| Dispatching parallel Opus explorer subagents | **Executor/Advisor pattern:** Sonnet explores directly, Opus advises at the end |
| Dispatching parallel Opus architect subagents | **Executor/Advisor pattern:** Sonnet drafts architectures, Opus critiques |
| Calling the advisor every turn | Advisor is **on-demand at checkpoints** — 3-5 calls per workflow, not every step |
| Skipping the advisor at required checkpoints | Phases 2, 4, and 4b advisor checkpoints are required — don't skip |
| Skipping `repomix --compress` for large codebases | Always run both repo outline + repomix for unfamiliar codebases |
| Coding before clarification | Phase 3 is a hard gate — resolve ambiguities first |
| Single architecture proposal | Always present 2 options (simplicity vs separation) |
| Passing full conversation to Phase 5-6 subagents | **Context management:** Tool-result clearing + phase-aware compaction + subagent pruning (see Context Management Strategy section) |
| Using full workflow for 1-2 file changes | Use Lite path — skip exploration/architecture |
| Using full workflow when cloning existing feature | Use Clone path — skip Phases 2-4 |
| Running all Phase 6 reviewers on Sonnet | Convention checks and pattern matching use **haiku** |
| Writing tests after code | TDD — test first, then implement |
| Not finishing the branch | Always run Phase 6 to completion |
| Guessing external API patterns | **Hard gate:** Invoke `/fetch-api-docs` before any API implementation — never code from memory |
| Multiple grep iterations for a symbol | Use Serena `find_symbol` or `find_referencing_symbols` |
| Re-discovering context each session | Use Serena `write_memory` / `read_memory` |
| Not tagging workflow failures | Apply failure taxonomy tags to every issue — untagged failures can't feed back into workflow improvement |
| Batching multiple workflow changes | One change at a time — each workflow edit should be validated independently before stacking |
| Ignoring workflow regression | When modifying the workflow skill, verify existing behaviors still work — don't overfit to the current feature |
| Skipping Workflow Retrospective | Always run the retrospective — it's the trace data that makes the workflow self-improving |
| Fixing review findings without re-checking | **Evaluator-optimizer loop:** After fixing a HIGH+ finding, re-run the specific reviewer that flagged it. Max 3 iterations, then escalate to user |
| Letting context grow unbounded | **Context management:** Tool-result clearing at ~50K tokens, phase-aware compaction at ~80%. Don't wait for context to break — manage it proactively |
| Passing vague "relevant context" to subagents | **Phase output contracts:** Reference named outputs ($plan, $requirements, $exploration, $diff) — don't ad-hoc decide what to pass each time |
| Running 10-step plans without context breaks | **Fresh context for long loops:** At 5+ steps, compact at ~60% capacity threshold or dispatch independent steps as fresh-context subagents |
| Using generic prompts for Haiku reviewers | **Dynamic prompts:** Generate context-specific review prompts for Tier 4 based on the actual diff, not static catch-all instructions |
| Skipping cross-cutting synthesis after reviews | Run the synthesizer when any HIGH+ findings exist — individual reviewers catch domain issues, synthesis catches cross-domain interactions |
| Using flat reasoning for architecture critique | **Extended thinking:** Ask the advisor to "think step by step" for Phase 4 and 4b checkpoints — trade-off analysis and plan stress-testing benefit from systematic reasoning |
