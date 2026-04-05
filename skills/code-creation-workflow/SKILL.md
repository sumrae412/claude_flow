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

### Thinking Budget Control

Use thinking budget keywords in subagent prompts to control how deeply Claude reasons at each step. This prevents over-thinking simple tasks and ensures critical decisions get adequate analysis.

| Keyword | Budget | Use When |
|---------|--------|----------|
| `think about this...` | ~4K tokens (fast) | Simple file reads, straightforward edits, config changes |
| `think harder about...` | ~10K tokens (deep) | Multi-step logic, debugging, integration analysis |
| `ultrathink about...` | ~32K tokens (max) | Architecture decisions, security review, complex refactors |

**Phase-to-thinking mapping:**

| Phase | Default Thinking | Escalate When |
|-------|-----------------|---------------|
| 0 Context | `think about` | — (always lightweight) |
| 1 Discovery | `think about` | Complex triage with many branching paths → `think harder` |
| 2 Exploration | `think harder` | Unfamiliar codebase or 10+ integration points → `ultrathink` |
| 3 Clarification | `think about` | Conflicting requirements or subtle edge cases → `think harder` |
| 4 Architecture | `ultrathink` | — (always max for architecture decisions) |
| 5 Implementation | `think about` | Complex business logic or concurrency → `think harder` |
| 6 Review | `think harder` | Security-sensitive code or auth flows → `ultrathink` |

**How to apply:** Prefix subagent prompts with the keyword. Examples:

```
# Phase 2 explorer — default
"think harder about... Trace how authentication middleware is implemented — find patterns, data flow, and key files"

# Phase 4 architect — always max (3 competing perspectives)
"ultrathink about... Design an architecture for the multi-tenant permission system optimizing for SIMPLICITY — reuse existing patterns, minimal new files"

# Phase 5 implementation — simple step
"think about this... Add the new column to the User model following the existing pattern in models/client.py"

# Phase 5 implementation — complex step
"think harder about... Implement the rate limiting middleware with sliding window algorithm and Redis backend"

# Phase 6 security review — escalated
"ultrathink about... Review this authentication flow for JWT vulnerabilities, token storage issues, and session fixation risks"
```

**Rule:** Default to the phase mapping above. Escalate one level when the specific step is more complex than typical for that phase. Never under-think architecture (Phase 4) or security reviews.

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

---

## Phase 2: Exploration (Parallel Subagents)

### Pre-Exploration: Generate Repo Outline (Token Saver)

Before launching explorers, generate a token-efficient codebase map:

```bash
python scripts/generate_repo_outline.py app/services/ --max-depth 2
```

This provides function/class signatures WITHOUT implementation bodies — dramatically reduces tokens while preserving structure awareness. Share this outline with explorer agents.

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

**Memory injection:** After exploration completes, invoke the `memory-injection` skill with the deduplicated list of key files identified. Append the returned PROJECT GOTCHAS block to all subsequent subagent prompts (Phases 4, 5, and 6).

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

### Step 1: Competing Architecture Proposals

Launch 3 **code-architect** subagents in parallel with deliberately different optimization targets. The third "contrarian" perspective prevents groupthink and surfaces approaches the other two miss.

```
┌──────────────────────────────────────────────────────┐
│ Architect A: "Design optimizing for SIMPLICITY —     │
│  reuse existing patterns, minimal new files,         │
│  least moving parts"                                 │
│                                                       │
│ Architect B: "Design optimizing for CLEAN            │
│  SEPARATION — extensibility, testability,            │
│  clear boundaries between concerns"                  │
│                                                       │
│ Architect C: "Design optimizing for MAXIMUM REUSE —  │
│  leverage every existing abstraction, minimize new   │
│  code, build on what's already there even if it      │
│  means bending existing patterns slightly"           │
└──────────────────────────────────────────────────────┘
                    │
                    ▼
   Present ALL THREE architectures to user:
   - Files to create/modify (with line counts)
   - Component designs and responsibilities
   - Data flow (how data moves through the system)
   - Trade-off analysis (what each approach sacrifices)
   - Best-of-all-worlds synthesis recommendation
                    │
                    ▼
   ◆ USER CHOOSES architecture (A, B, C, or hybrid) ◆
```

**Subagent dispatch:** Use the Agent tool with `subagent_type: "feature-dev:code-architect"` and **`model: "opus"`**. Each gets the exploration findings + clarification answers + a clear optimization directive. Include PROJECT GOTCHAS from memory-injection in each architect's prompt.

**Synthesis step:** After all 3 return, present a "best-of-all-worlds" recommendation that blends the strongest ideas from each. Be intellectually honest about which architect had the better approach for each aspect.

**Architect C rotation:** The third target should vary based on what matters most for this feature. Options beyond "maximum reuse":
- "FUTURE EXTENSIBILITY — design for the next 3 features, not just this one"
- "PERFORMANCE — minimize allocations, queries, and round-trips"
- "MINIMAL RISK — fewest changes to existing code, safest migration path"

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

4. Run static analysis on changed files (catch issues early):
   semgrep --config=.semgrep.yml <changed-files>
   ast-grep scan <changed-directory>

   Fix any ERROR-level issues before proceeding.

5. Mark TodoWrite item complete
```

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

---

## Phase 6: Quality + Finish

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
| 1 | Discovery | — | Fast-path escape for small changes | Auto |
| 2 | Exploration | **opus** | 2-3 parallel code-explorer subagents + context hydration | **Context hydration** |
| 3 | Clarification | — | Surface all ambiguities + optional PRP export | **User answers** |
| 4 | Architecture | **opus** | 3 competing architects + iterative refinement with convergence detection | **User chooses + approves plan** |
| 5 | Implementation | **sonnet** | TDD per step + fresh eyes self-review + drift detection + swarm coordination | Tests pass |
| 6 | Quality + Finish | **sonnet/opus** | 5-tier review (overshoot technique) + random exploration + UX polish + de-slopification → verify → commit | **Verification** |

## Agents Used Within This Workflow

| Agent | `subagent_type` | Phase | Trigger | Model |
|-------|-----------------|-------|---------|-------|
| Code Explorer (x2-3) | `feature-dev:code-explorer` | 2 | Always | opus |
| Code Architect (x3) | `feature-dev:code-architect` | 4 | Always | opus |
| Plan Refiner (x2-3 rounds) | `general-purpose` | 4 | Complex features | opus |
| Migration Reviewer | `migration-reviewer` | 5, 6 | Alembic files | sonnet |
| Google API Reviewer | `google-api-reviewer` | 5, 6 | Google API code | sonnet |
| Async Reviewer | `async-reviewer` | 5, 6 | async I/O code | sonnet |
| Code Reviewer (x2) | `feature-dev:code-reviewer` | 6 | Always (overshoot prompts) | sonnet |
| Silent Failure Hunter | `pr-review-toolkit:silent-failure-hunter` | 6 | Always (overshoot prompts) | sonnet |
| Security Reviewer | `security-reviewer` | 6 | Always (overshoot prompts) | sonnet |
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | 6 | Always (overshoot prompts) | sonnet |
| Design Reviewer | `general-purpose` | 6 | UI files modified | sonnet |
| Type Design Analyzer | `pr-review-toolkit:type-design-analyzer` | 6 | New types/models | sonnet |
| API Doc Auditor | `api-doc-auditor` | 6 | New/modified routes | sonnet |
| Invariant Checker | `courierflow-invariant-checker` | 6 | Always (CF projects) | sonnet |
| Defensive Verifier | `defensive-pattern-verifier` | 6 | Always (CF projects) | sonnet |
| UX Polish Reviewer | `general-purpose` | 6 | UI files modified | opus |
| Random Code Explorer | `general-purpose` | 6 | Always (complex features) | opus |
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

## Static Analysis Tools (Automatic)

| Tool | Where Used | Purpose |
|------|------------|---------|
| `generate_repo_outline.py` | Phase 2 (pre-exploration) | Token-efficient codebase context |
| `semgrep` | Phase 5 (per-step), Phase 6 (gate) | Semantic analysis, security checks |
| `ast-grep` | Phase 5 (per-step), Phase 6 (gate) | Structural anti-pattern detection |
| `pyright` | Phase 6 (gate) | Fast type checking |

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
| Post-compaction confusion | Run Compaction Recovery Protocol immediately |
| Parallel agents touching same files | Review file claims, split work more granularly |

## Common Mistakes

| Mistake | Fix |
|---------|-----|
| Skipping Phase 0 context loading | Always load project context first |
| Exploring sequentially instead of parallel | Use 2-3 explorer subagents |
| Proceeding to clarification with only explorer summaries | Context hydration is a hard gate — main session must read top 5-10 files firsthand before Phase 3 |
| Coding before clarification | Phase 3 is a hard gate — resolve ambiguities first |
| Only 2 architecture proposals | Always present 3 competing perspectives (simplicity vs separation vs contrarian) |
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
