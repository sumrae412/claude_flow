# Phase 5: Implementation (TDD + Defensive Patterns)

<!-- Loaded: after Phase 4d (or Phase 4 for lite) | Dropped: after tests+lint pass -->
<!-- Output: $diff contract -->
<!-- Implementation detail for mutation gate, visual verify, authoring-time lookups, and cross-model retry has moved to memory/ entries (mutation_gate_component, visual_verify_gate, authoring_time_lookups, cross_model_retry_ladder). This file orchestrates; it no longer documents internals. See memory/phase5_inline_to_references.md. -->

---

## Context Management Strategy

The full workflow (Phases 0-6) is a long-running agentic session that reads 8-15+ files, dispatches advisor calls, and runs multi-tier reviews. Without active context management, the session will hit limits. Three composable strategies apply here most intensely.

### Strategy 1: Tool-Result Clearing (Automatic, Zero-Cost)

Phase 2 reads 8-15 files. By Phase 5, those old file reads are stale context bloat — the executor already synthesized the relevant patterns. Tool-result clearing drops old Read/Grep results while keeping the tool_use records (so the model remembers *what* it read and *why*).

**When to apply:** Automatically during Phases 4-6 when context grows.

```
Trigger:     Context exceeds ~50K tokens (roughly end of Phase 2)
Keep:        4 most recent tool results (active working set)
Exclude:     Memory tool results (MEMORY.md reads must survive)
Clear:       At least 10K tokens per clearing event (avoid thrashing)
```

- **Cleared:** Content of old file reads, grep results, API responses (replaced with `[cleared — re-read if needed]`)
- **Retained:** The tool_use records, all agent reasoning, user messages, advisor responses

### Strategy 2: Phase-Aware Compaction (At Threshold)

**Soft threshold:** At ~60% capacity, mentally prepare a session summary — note current phase, completed steps, key decisions, active working files.

**Hard threshold:** At ~80% capacity, compact with phase-specific instructions:

```
During Phase 5 (mid-implementation):
  Preserve: plan with completion status per step, test results,
            files modified so far, current step context,
            any advisor guidance still relevant
  Drop:     completed step details (code is in git), old test output
```

### Strategy 3: Phase Output Contracts (Explicit Data Flow)

See `contracts/` files for full definitions. Phase 5 consumes:

- `$verified_plan` (use when Phase 4c ran, else `$plan`) — steps assigned
- `$exploration` — key file paths + patterns (not full file contents)
- `$requirements` — resolved edge cases and constraints
- `$test_skeletons` — skeleton file paths + criterion mapping (Full path only)

Phase 5 produces: `$diff` — git diff of all changes + files modified list → consumed by Phase 6 reviewers.

**What to NEVER pass to subagents:** advisor transcripts, rejected architecture details, Phase 0 loading decisions, raw clarification Q&A.

### Composing the Strategies

```
Phase 5:    Implementation generates code + test output
            → Tool-result clearing drops old test runs
            → Subagent pruning for parallel dispatch
            → If approaching 80%, compact with Phase 5 instructions
            → Each subagent starts with FRESH context (step assigned,
               key file paths, defensive patterns — no prior history)
```

---

## Phase 5: Implementation

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

3a. Explain-before-fix (retry iter 2 gate):
    When a fix has already been attempted once and the test still fails,
    BEFORE writing any new code, ask the executor (same model) to explain
    WHY the first attempt failed. Prompt shape:

      "The previous fix didn't resolve the failure. Explain why the
       current code still fails the test. Don't write any code."

    Read the explanation. Only then attempt iter-2. This breaks the
    confirmation-bias loop where iter-2 rewrites variants of iter-1's
    mental model. Cheap (~1 call, no code change) and complements the
    iter-3 cross-model escalation documented in the state transition.

3b. GUARD — scoped regression check
    After the target test passes, run a broader check to catch
    regressions introduced by the fix:

    Guard scope (choose the narrowest that covers the change):
    a) Same test module: pytest <test_module> (single module changed)
    b) Affected package: pytest <package>/tests/ (multi-file change)
    c) Full suite: only if changes span packages

    Default to (a) — it's fast and catches most regressions.

    Guard MUST pass before proceeding to step 4.
    If guard fails:
    - The fix introduced a regression — fix it (don't revert target fix)
    - Re-run BOTH the target test AND the guard
    - Max 2 guard-fix cycles → then escalate to user
    - Emit failure event with tag: guard-regression

    Why separate from step 6: Step 6 catches cross-TASK regressions
    (after the task is marked complete). Step 3b catches within-FIX
    regressions before you move on — cheaper to fix in place.

3e. CONTEXT EXTRACTION — capture reusable domain facts
    After tests pass and the guard clears, before static analysis,
    extract reusable domain facts discovered during this task. Runs INLINE
    (Sonnet executor, no subagent spawn) so facts are available immediately
    for the next task and survive context compaction.

    Run this extraction prompt against the just-completed task:

    ```
    Review the task you just completed. Extract reusable domain facts in
    these categories:

    1. SCHEMA: Column names, table relationships, enum values discovered
    2. API: Endpoint signatures, response shapes, error codes encountered
    3. PATTERN: Code patterns that worked (import paths, service method
       signatures, conventions)
    4. GOTCHA: Anything that failed first and required a different approach

    Output as structured YAML matching the $diff.context_facts schema.
    Max 10 facts per task. Only NOVEL discoveries — skip facts already
    in $plan, $requirements, or earlier $diff.context_facts entries.
    ```

    Append the YAML output to $diff.context_facts under a new entry keyed
    by the current task identifier:

    ```yaml
    context_facts:
      - task: "<task-id-from-plan>"
        facts:
          - type: SCHEMA
            fact: "HouseholdMember.is_primary_contact (not is_primary)"
          - type: PATTERN
            fact: "household_service.ensure_client_for_member() required after create"
          - type: GOTCHA
            fact: "scalar_one_or_none() crashes on email lookup — use scalars().first()"
    ```

    Skip conditions (no facts to extract; do not block):
    - Task changed zero test files (documentation-only / config-only task)
    - Task is a pure refactor with no new domain knowledge
    - Extraction returned an empty array (no novel facts)

    Performance budget:
    - ~200 tokens in, ~100 tokens out per task
    - Estimated overhead: 5-10 seconds per task (no subagent spawn)
    - Hard cap: skip if extraction takes >30 seconds (log and continue)

    Consumption points (no action needed here — downstream consumers handle):
    - Next-task executor injects facts as "known context" in the task prompt
      (see "Parallel Subagent Dispatch" section below)
    - Phase 6 reviewers receive facts via $diff contract
    - Session-learnings dedupes against context_facts before promoting to MEMORY.md
    - GOTCHA-tagged facts are candidates for memory-injection promotion

    Why separate from session-learnings: session-learnings runs at end of
    workflow (or end of session) — facts captured there are lost across
    context compaction and unavailable to subsequent in-workflow tasks.
    Step 3e captures facts WHILE they are fresh and propagates them
    forward.

4. Run static analysis on changed files (catch issues early):
   semgrep --config=.semgrep.yml <changed-files>
   ast-grep scan <changed-directory>

   Fix any ERROR-level issues before proceeding.

5. Mark TodoWrite item complete

6. Inter-task verification gate (proactive, not just reactive):
   Run full test suite + lint + build check BEFORE starting next task.
   Catches cross-TASK regressions (step 3b catches within-FIX ones).
   See subagent-driven-development skill for full gate protocol.
   Skip full suite for Task 1 or trivial tasks.
   If gate fails → fix regression → re-verify → then proceed.
```

### Fresh Context for Long Implementation Loops

When a plan has 5+ steps, context accumulates across the TDD cycle. Apply when: plan has 5+ sequential steps AND context exceeds ~60% capacity mid-implementation.

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
  - $diff.context_facts entries from prior completed tasks
    (injected as "Known context from earlier tasks: ..." preamble;
    populated by Step 3e after each task)
  No prior step history — the plan is the contract.
```

**Inter-task fact injection (sequential dispatch too):** When the
controller dispatches the NEXT task's subagent (sequential or parallel),
prepend a "Known context from earlier tasks" section to the prompt
containing all `$diff.context_facts` entries from prior tasks. This
makes prior-task discoveries available without re-discovery and is the
primary consumer of Step 3e output. Format the injected block as:

```
Known context from earlier tasks (from $diff.context_facts):
- [task-1] SCHEMA: HouseholdMember.is_primary_contact (not is_primary)
- [task-1] GOTCHA: scalar_one_or_none() crashes on email lookup — use scalars().first()
- [task-2] PATTERN: ensure_client_for_member() required after create
```

### Advisor: Mid-Implementation (optional)

Only at genuinely ambiguous decision points. Not routine steps.
Dispatch Opus with: specific decision context from current `$plan` step.
Question: focused on the specific ambiguity.

**When to call:** non-obvious integration patterns, conflicting precedents, step diverging from plan in ways affecting later steps.
**When NOT to call:** routine implementation, standard TDD cycles with clear requirements, unambiguous plan steps.

### Parallel Subagent Dispatch (For Independent Steps)

When the plan has 3+ steps with no dependencies between them:

```
Use subagent-driven-development skill:
  → Dispatch parallel implementation agents with model: "sonnet"
  → Each follows the same TDD + defensive pattern
  → Merge results when all complete
```

<!-- Task taxonomy (types + dependency types) defined in writing-plans/SKILL.md. Keep in sync. -->
**Dependency-aware dispatch:**
- `data` or `build` dependencies → strictly sequential (predecessor must complete first)
- `knowledge` dependencies → parallelizable (dispatch concurrently, record assumptions in each subagent's context)
- Tasks with no dependencies → parallelizable
- `shared_prerequisite` tasks → always execute before dependent `value_unit` tasks

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

**State transition:** If tests+lint pass, transition to phase-5.5. If failed and iteration < 3, increment iteration and retry phase-5 following the retry ladder:
- **iter 1:** same executor, same thinking budget
- **iter 2:** same executor, escalated thinking budget — **preceded by the Step 3a explain-before-fix gate**
- **iter 3:** cross-model investigator (Sonnet executor → Opus, or vice versa); see `memory/cross_model_retry_ladder.md`

If iteration limit reached, set status to "failed" and surface to user.
