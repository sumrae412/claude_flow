# Phase 4: Architecture (Executor Drafts + Advisor Critiques)

<!-- Loaded: after Phase 3 | Dropped: after user approves plan -->
<!-- Output: $plan contract -->

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

---

## User Approval Gate

```
◆ USER APPROVES final plan (post-advisor-review) before implementation ◆
```

**State transition:** Write `artifacts.implementation_plan` with steps array, then transition to phase-4d (full path) or phase-5 (lite path).

---

**Output:** Populate `$plan` contract (see `contracts/plan.schema.md`). User must approve before implementation.
