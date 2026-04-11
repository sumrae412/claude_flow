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

Three-tier model routing: **Opus** for thinking-heavy phases, **Sonnet** for execution, **Haiku** for lightweight pattern-matching reviews. This optimizes cost and speed — deep reasoning where it matters, fast throughput for implementation, and cheap passes for convention checks.

| Phase | Model | Why |
|-------|-------|-----|
| 0 Context | (main session) | Lightweight loading |
| 1 Discovery | (main session) | Quick triage decision |
| 2 Exploration | **opus** | Deep codebase analysis needs reasoning |
| 3 Clarification | (main session) | Interactive with user |
| 4 Architecture | **opus** | Architectural decisions need deep reasoning |
| 4 Debate Review | **sonnet** | Multi-model plan validation (debate-team dispatches its own models) |
| 5 Implementation | **sonnet** | Execution speed — patterns are known by now |
| 6 CodeRabbit Pass | **sonnet** | Consolidated first-pass review |
| 6 Deep Review | **sonnet** | Security, silent failures, test coverage |
| 6 Light Review | **haiku** | Convention checks, defensive patterns, invariants |

When dispatching subagents, pass `model: "opus"`, `model: "sonnet"`, or `model: "haiku"` on the Agent tool call to enforce this.

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

## Phase 2: Exploration (Parallel Subagents)

### Pre-Exploration: Compressed Codebase Context (Token Saver)

Before launching explorers, generate token-efficient codebase maps using **both** tools:

```bash
# Signatures only — function/class headers without bodies
python scripts/generate_repo_outline.py app/services/ --max-depth 2

# Full compressed context — entire codebase packed into minimal tokens
repomix --compress --output .repomix-output.txt
```

**`generate_repo_outline.py`** gives precise signatures for targeted areas. **`repomix --compress`** gives broad codebase awareness in minimal tokens — useful when explorers need to understand cross-cutting concerns or unfamiliar areas. Share both outputs with explorer agents.

For small/familiar codebases, `generate_repo_outline.py` alone is sufficient. For large or unfamiliar codebases, always run both.

### Launch Explorers

Launch 2-3 **code-explorer** subagents in parallel to understand the codebase:

```
┌─────────────────────────────────────────────────────┐
│ Explorer A: "Trace how similar features are         │
│              implemented — find patterns, data flow" │
│                                                      │
│ Explorer B: "Map architecture for [feature area] —  │
│              key files, layers, dependencies"        │
│                                                      │
│ Explorer C: "Analyze test patterns and UI patterns   │
│              used in this area" (if relevant)        │
└─────────────────────────────────────────────────────┘
                    │
                    ▼
   Each agent returns key files + structured findings
                    │
                    ▼
   ◆ CONTEXT HYDRATION (see below) ◆
                    │
                    ▼
   Present summary of codebase understanding to user
```

**Subagent dispatch:** Use the Agent tool with `subagent_type: "feature-dev:code-explorer"` or `"Explore"` and **`model: "opus"`**. Each agent gets a focused prompt describing what to find.

**Serena integration:** When agents identify symbols to trace, use `find_symbol` / `find_referencing_symbols` instead of grep chains. Use `write_memory` to persist discoveries for cross-session continuity.

**Minimum output per explorer:** 5-10 key files, the patterns they follow, and any concerns or constraints discovered.

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

## Phase 4: Architecture (Parallel Design + Optional AI Review)

Launch 2 **code-architect** subagents in parallel with different optimization targets:

```
┌──────────────────────────────────────────────────┐
│ Architect A: "Design optimizing for SIMPLICITY — │
│  reuse existing patterns, minimal new files,     │
│  least moving parts"                             │
│                                                   │
│ Architect B: "Design optimizing for CLEAN        │
│  SEPARATION — extensibility, testability,        │
│  clear boundaries between concerns"              │
└──────────────────────────────────────────────────┘
                    │
                    ▼
   Present BOTH architectures to user:
   - Files to create/modify (with line counts)
   - Component designs and responsibilities
   - Data flow (how data moves through the system)
   - Trade-off analysis (what each approach sacrifices)
                    │
                    ▼
   ◆ USER CHOOSES architecture (A, B, or hybrid) ◆
```

**Subagent dispatch:** Use the Agent tool with `subagent_type: "feature-dev:code-architect"` and **`model: "opus"`**. Each gets the exploration findings + clarification answers + a clear optimization directive.

### Write Implementation Plan

After user chooses, write a structured plan using the `writing-plans` skill:
- Numbered steps with specific files and changes
- Test requirements per step
- Dependencies between steps marked clearly

### Debate Team Review (Required)

<HARD-GATE>
Every implementation plan must pass debate-team review before user approval. This catches architectural flaws, scope creep, and blind spots that competing proposals alone miss.
</HARD-GATE>

After writing the plan, invoke the `debate-team` skill:

1. **DeepSeek Bug-Hunter** — Probes for logic errors, missing edge cases, integration risks
2. **GPT-4o Architecture Critic** — Challenges structural decisions, separation of concerns, scalability
3. **Haiku Style Critic** (conditional) — Fires only if DeepSeek and GPT-4o disagree, breaks ties on convention adherence

**Process:**
1. Pass the implementation plan + chosen architecture + key file context to debate-team
2. Collect critiques from all models
3. Present consolidated findings to user alongside the plan
4. Revise plan to address HIGH+ critiques
5. If revisions are substantial, re-run debate-team on the revised plan (max 2 iterations)

**What debate-team receives (context-pruned):**
- The implementation plan
- The chosen architecture summary (not both options)
- Key file paths and patterns (from exploration)
- Resolved requirements (from clarification)

**Triage:**
- **CRITICAL** — Must fix before approval (architectural flaw, missing requirement, security gap)
- **HIGH** — Should fix before approval (scope creep, untested edge case, fragile integration)
- **MEDIUM** — Note for implementation phase (style preference, minor optimization)
- **LOW** — Informational only (alternative approaches, future considerations)

```
◆ USER APPROVES final plan (post-debate-team) before implementation ◆
```

---

## Context Pruning Between Phases

<IMPORTANT>
Phases 0-4 accumulate significant context (exploration findings, architecture discussions, clarification Q&A). Phases 5-6 don't need all of it. Prune aggressively when dispatching implementation and review subagents.
</IMPORTANT>

**What to pass to Phase 5 subagents:**
- The approved implementation plan (numbered steps)
- Key file paths and their roles (from exploration)
- Resolved requirements and edge cases (from clarification)
- Defensive patterns to apply
- API docs fetched (if applicable)

**What to NOT pass:**
- Full exploration agent transcripts
- Rejected architecture option details
- Phase 0 skill loading decisions
- Raw clarification Q&A (pass resolved answers only)

**What to pass to Phase 6 reviewers:**
- The git diff (primary input)
- The plan (for adherence checking)
- Project conventions summary (from CLAUDE.md / loaded skills)

**Why this matters:** A subagent dispatched with 50K tokens of pruned context is faster, cheaper, and more focused than one with 150K tokens of accumulated conversation. The plan is the contract — everything else is noise for execution agents.

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

**Tier 4 — Lightweight Checks (parallel, haiku):**

Pattern-matching checks that don't need deep reasoning — run on **haiku** for cost efficiency:

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

**Merge & fix:** Collect all findings across all tiers (CodeRabbit + specialists + lightweight + design), deduplicate, fix HIGH+ issues (including Design Review Blockers and High-Priority). Post summary of findings to user.

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

---

## Quick Reference: All Phases

| Phase | Name | Model | Key Pattern | Gate |
|-------|------|-------|-------------|------|
| 0 | Context | — | Trigger matrix → load relevant skills only | None |
| 1 | Discovery | — | 4-path triage (fast/clone/lite/full) | Auto |
| 2 | Exploration | **opus** | 2-3 parallel code-explorer subagents + repomix + context hydration | **Context hydration** |
| 3 | Clarification | — | Surface all ambiguities + optional PRP export | **User answers** |
| 4 | Architecture | **opus** | 2 parallel code-architect subagents | **User chooses** |
| 4b | Debate Review | **sonnet** | Tri-model adversarial plan review (required) | **Debate-team passes** |
| — | Context Pruning | — | Pass only plan + key files to execution phases | Auto |
| 5 | Implementation | **sonnet** | TDD per step + parallel dispatch | Tests pass |
| 6 | Quality + Finish | **sonnet/haiku** | CodeRabbit first pass → cascading specialists → verify → commit | **Verification** |

## Agents Used Within This Workflow

| Agent | `subagent_type` | Phase | Trigger | Model |
|-------|-----------------|-------|---------|-------|
| Code Explorer (x2-3) | `feature-dev:code-explorer` | 2 | Always (full workflow) | opus |
| Code Architect (x2) | `feature-dev:code-architect` | 4 | Always (full workflow) | opus |
| Debate Team | `debate-team` (skill) | 4b | **Always (required)** | sonnet (dispatches own models) |
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
| Code Simplifier | `code-simplifier:code-simplifier` | 6 | After review fixes | opus |

## Skills Invoked Within This Workflow

| Skill | Where Used |
|-------|-----------|
| fetch-api-docs | Phase 5 (pre-implementation gate for external APIs) |
| coding-best-practices | Phase 0 (loaded), Phase 5 (applied) |
| defensive-ui-flows | Phase 0 (loaded), Phase 5 (applied) |
| defensive-backend-flows | Phase 0 (loaded), Phase 5 (applied) |
| writing-plans | Phase 4 (plan creation) |
| **debate-team** | **Phase 4b (required — tri-model adversarial plan review)** |
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

| Former Skill | Absorbed Into |
|-------------|---------------|
| plancraft brainstorming | Phases 1-3 (discovery + exploration + clarification) |
| brainstorming skill | Phases 1-3 (interactive exploration replaces separate brainstorm) |
| PlanCraft full pipeline | Replaced by **debate-team** (required Phase 4b) — tri-model adversarial review is more rigorous |
| Dual code-reviewer agents | Replaced by **CodeRabbit** (Phase 6 Tier 1) — single consolidated pass |

## Error Recovery

| Situation | Action |
|-----------|--------|
| Explorer agent returns poor results | Re-dispatch with more specific prompt, or explore manually |
| Architecture options both rejected | Ask user what they want different, re-run architects |
| Tests fail during implementation | Fix immediately, don't proceed to next step |
| Reviewer finds critical issue | Fix before finishing, re-run verification |
| User wants to stop mid-workflow | Stop. Summarize state (phase, what's done, what's left). |
| Wrong architecture chosen | Revert to plan, re-architect with new constraints |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Skipping Phase 0 context loading | Always load project context first |
| Exploring sequentially instead of parallel | Use 2-3 explorer subagents |
| Skipping `repomix --compress` for large codebases | Always run both repo outline + repomix for unfamiliar codebases |
| Proceeding to clarification with only explorer summaries | Context hydration is a hard gate — main session must read top 5-10 files firsthand before Phase 3 |
| Coding before clarification | Phase 3 is a hard gate — resolve ambiguities first |
| Single architecture proposal | Always present 2 options (simplicity vs separation) |
| Skipping debate-team review | **Hard gate:** Every plan must pass debate-team before user approval |
| Passing full conversation to Phase 5-6 subagents | **Context prune:** Pass only plan + key files + resolved requirements |
| Using full workflow for 1-2 file changes | Use Lite path — skip parallel explorers/architects |
| Using full workflow when cloning existing feature | Use Clone path — skip Phases 2-4 |
| Running all Phase 6 reviewers on Sonnet | Convention checks and pattern matching use **haiku** |
| Running dual code-reviewers in Phase 6 | CodeRabbit replaces both — single consolidated pass |
| Writing tests after code | TDD — test first, then implement |
| Not finishing the branch | Always run Phase 6 to completion |
| Guessing external API patterns | **Hard gate:** Invoke `/fetch-api-docs` before any API implementation — never code from memory |
| Multiple grep iterations for a symbol | Use Serena `find_symbol` or `find_referencing_symbols` |
| Re-discovering context each session | Use Serena `write_memory` / `read_memory` |
