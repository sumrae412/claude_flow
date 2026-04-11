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
   │ NO to all → FULL WORKFLOW (continue)           │
   └─────────────────────────────────────────────┘
```

**Path criteria:**
- **Fast path:** Typo fix, one-line change, config tweak, single-file edit with no ripple effects
- **Clone path:** Feature X already exists and you're building Feature X' (e.g., "add a delete endpoint" when create/update endpoints already exist)
- **Lite path:** Contained change touching 1-2 files — doesn't justify 5+ parallel subagents
- **Full workflow:** Everything else. If in doubt, use the full workflow.

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

## Phase 4: Architecture (Executor Drafts + Advisor Critiques)

The **executor (Sonnet)** drafts two competing architecture options. It has full context from Phase 2 exploration — it read the files firsthand, knows the patterns, understands the integration points. No architect subagents needed.

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
| Phase 3 | `$requirements` | Resolved requirements, edge cases, scope boundaries | Phases 4, 5, reviewer prompts |
| Phase 4 | `$architecture` | Chosen architecture summary, component responsibilities, data flow | Phase 5 |
| Phase 4b | `$plan` | Approved numbered implementation plan with dependencies | Phase 5, Phase 6 reviewers |
| Phase 5 | `$diff` | Git diff of all changes + files modified list | Phase 6 reviewers |

**How to use:** When dispatching a subagent, reference the contract explicitly. Don't pass raw conversation — pass the named output:

```
Phase 5 subagent receives:
  $plan          — the specific steps assigned
  $exploration   — key file paths + patterns (not full contents)
  $requirements  — resolved edge cases and constraints
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

4. Run static analysis on changed files (catch issues early):
   semgrep --config=.semgrep.yml <changed-files>
   ast-grep scan <changed-directory>

   Fix any ERROR-level issues before proceeding.

5. Mark TodoWrite item complete
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

## Phase 6: Quality + Finish

### 5-Tier Cascading Review

Reviews are structured as a cascade: CodeRabbit runs first (broad, fast), then specialized agents fill gaps CodeRabbit can't cover. This replaces the previous all-parallel approach — fewer agents, fewer tokens, same coverage.

**Tier 1 — CodeRabbit First Pass (always run):**

| Agent | `subagent_type` | Model | Focus |
|-------|-----------------|-------|-------|
| CodeRabbit | `coderabbit:code-reviewer` | **sonnet** | Consolidated review: bugs, logic errors, conventions, patterns, plan adherence, code quality |

CodeRabbit replaces the previous dual `feature-dev:code-reviewer` agents (Reviewer A + B). It covers bugs, conventions, and patterns in a single pass. Wait for CodeRabbit results before dispatching Tier 2.

**Tier 2 — Deep Specialists (parallel, always run):**

These catch what CodeRabbit doesn't specialize in — dispatch in parallel after Tier 1 completes:

| Agent | `subagent_type` | Model | Focus |
|-------|-----------------|-------|-------|
| Silent Failure Hunter | `pr-review-toolkit:silent-failure-hunter` | **sonnet** | Swallowed errors, empty catches, hidden failures |
| Security Reviewer | `security-reviewer` | **sonnet** | Auth, data exposure, injection, OWASP |
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | **sonnet** | Test coverage gaps, missing edge cases, untested error paths |

**Tier 3 — Conditional Specialists (parallel, skip if already ran in Phase 5):**

| Condition | Agent | `subagent_type` | Model |
|-----------|-------|-----------------|-------|
| New/modified Alembic migrations | Migration Reviewer | `migration-reviewer` | **sonnet** |
| Google API integration code | Google API Reviewer | `google-api-reviewer` | **sonnet** |
| Async code paths | Async Reviewer | `async-reviewer` | **sonnet** |
| New types/models/Pydantic schemas | Type Design Analyzer | `pr-review-toolkit:type-design-analyzer` | **haiku** |
| New/modified API routes | API Doc Auditor | `api-doc-auditor` | **haiku** |

**Tier 4 — Lightweight Checks (parallel, haiku with dynamic prompts):**

Pattern-matching checks that don't need deep reasoning — run on **haiku** for cost efficiency. However, instead of static generic prompts, the executor generates **context-specific review prompts** based on what was actually changed (inspired by the Claude Cookbook's Haiku sub-agent pattern where Opus generates targeted extraction prompts for Haiku).

**Dynamic prompt generation:** Before dispatching Tier 4 agents, the executor (Sonnet) generates a focused prompt for each based on the actual diff:

```
For Defensive Verifier:
  "This feature added [3 new route handlers and a modal form].
   Check specifically for:
   - Guard clauses on the [route parameter validation]
   - Try-catch with user feedback in the [modal submit handler]
   - Loading/error/success states in the [form component]
   Skip checking: [unchanged utility files, test files]"

For Invariant Checker (CF projects):
  "This feature modified [the appointment model and calendar service].
   Check specifically for:
   - Column name consistency between [appointment table] and [calendar queries]
   - Eager loading on the [new relationship added in models.py]
   Skip checking: [frontend files, migration boilerplate]"
```

**Why dynamic prompts:** Static prompts make Haiku scan the entire diff for every possible pattern. Dynamic prompts focus Haiku on the 2-3 specific patterns most likely to appear in *this* diff, reducing false positives and improving signal quality.

| Agent | `subagent_type` | Model | Focus |
|-------|-----------------|-------|-------|
| Invariant Checker | `courierflow-invariant-checker` | **haiku** | Client sync, column names, query safety, eager loading (CF projects only) |
| Defensive Verifier | `defensive-pattern-verifier` | **haiku** | Guard clauses, error handling, UI state management |

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
| 1 | Discovery | executor | 4-path triage (fast/clone/lite/full) | Auto |
| 2 | Exploration | executor + **advisor** | Executor explores directly → advisor reviews gaps | **Advisor confirms coverage** |
| 3 | Clarification | executor | Surface all ambiguities + optional PRP export | **User answers** |
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
