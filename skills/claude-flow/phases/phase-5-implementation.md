# Phase 5: Implementation (TDD + Defensive Patterns)

<!-- Loaded: after Phase 4d (or Phase 4 for lite) | Dropped: after tests+lint pass -->
<!-- Output: $diff contract -->

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

### Pre-Implementation: Inject Plan-Wide Lookups

Before dispatching any implementer subagent, run the plan-wide lookup pass.
This gathers deterministic facts about the repo (current migration heads,
existing route paths, etc.) and prevents hallucination at authoring time.

Inspired by Brian/Notion's `find-icon` skill — don't let the LLM guess
when a script can look up the truth.

```
Collect all file paths from $plan (files to create OR modify across all tasks).
Run:
    python skills/claude-flow/scripts/inject_lookups.py \
        --scope plan \
        --files <all-plan-files> \
        --json

Cache the output JSON. Inject its `lookups` section into the
PROJECT CONTEXT block of every implementer subagent prompt:

    REPO LOOKUPS (verified facts — do not invent alternatives):
    [alembic_heads]
    <output>

    [fastapi_routes]
    <output>
```

If `lookups` is empty (all detectors skipped for this project), omit the
section from subagent prompts. Large `skipped_detectors` lists are fine —
most projects won't match all detectors.

See `skills/claude-flow/references/lookup-detectors.md` for the registry.

### Create TodoWrite Items

Break the plan into individual TodoWrite items. Mark each complete as you finish it.

### Per-Task Context: Mockup Inputs for UI Work

For any task touching UI files — patterns `*.tsx`, `*.jsx`, `*.vue`, `*.svelte`, `*.html`, `*.css`, `*.scss`, or template directories (e.g. `app/templates/*`, `views/*`, `pages/*`) — check whether Phase 4 emitted Excalidraw mockups for this feature:

```
If docs/design/<feature>/mockups/*.excalidraw exists:
  → Include the matching mockup file path(s) in the implementer subagent's context
    alongside $plan and the step's file list
  → The implementer should read the mockup before writing templates/CSS to
    ensure the rendered UI matches the approved layout
If docs/design/<feature>/architecture.excalidraw exists (one-way diagram):
  → Include as reference context for any task that touches >1 component
    (helps the implementer see how their piece connects)
```

Mockups are optional context — if none exist (backend-only feature, `--visual` not used), skip. Do not fail a task because a mockup is missing.

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

   - CROSS-MODEL DIAGNOSIS on retry exhaustion (iteration ≥ 3):
     When the same test has failed in ≥2 prior retries under the
     executor's model family, the model is likely stuck in a wrong
     mental model. Same-model "think harder" (thinking-budget
     escalation) does not break confirmation-bias loops.

     On the 3rd retry, dispatch /investigator with an EXPLICITLY
     DIFFERENT model family than the executor:
       - Executor is Sonnet → dispatch investigator on Opus
       - Executor is Opus → dispatch investigator on Sonnet
       - Haiku executor → escalate to Sonnet (never rely on Haiku
         for diagnosis)

     Pass the /investigator call:
       - The evidence matrix from prior retries (not the transcript)
       - The specific failing assertion + stack trace
       - A 1-line hypothesis from each prior retry ("last attempt
         assumed X — that may be the wrong mental model")
       - Explicit ask: "What mental model is the prior attempts
         missing? Do not propose a fix."

     Emit failure event with tag: retry-cross-model-diagnosis.
     This is distinct from within-retry investigator use — same
     tool, different model family, diagnostic-only framing.

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

3c. MUTATION GATE — test-discrimination check
    After the new test(s) pass on the real implementation, verify they
    actually discriminate by mutating the target and re-running them.
    A test that passes under every mutation (e.g. `assert True`, weak
    assertions, calls-but-doesn't-check) is non-discriminating and
    wouldn't catch a regression.

    Inspired by the Atomic Skills paper (arXiv:2604.05013): unit tests
    only earn reward when they pass the original AND fail an injected
    bug. This is the same gate applied at workflow time.

    Run:
    ```
    python skills/claude-flow/scripts/mutation_check.py \
        --new-tests <new-or-modified-test-paths> \
        --target-files <modified-production-paths> \
        --json
    ```

    Scope (heuristic C): the script mutates only functions in the
    target files whose names also appear in the new test files.

    Gate rule (per-test, strict — paper's rule):
    - Each new test must kill at least one mutation of its target.
    - Exit 0 + non_discriminating == [] → PASS, proceed to step 4.
    - Exit 1 → FAIL. Strengthen the flagged test(s): add real
      assertions, check return values/side effects, don't just call
      the function and assert True.
    - Max 2 mutation-fix cycles → then escalate to user.
    - Emit failure event with tag: mutation-gate-exceeded.

    Skip conditions (exit 0, skipped=True, do not block):
    - Target code is non-Python (JS/Go/etc. — v1 is Python-only)
    - No target function identifiable from the new tests
    - Pure refactor (no new tests, no --new-tests supplied)
    - pytest unavailable in the current interpreter
    - Target function has no mutable operators

    Wall-clock budget:
    - Per-test mutation run: 30s subprocess timeout.
    - Per step: MAX_MUTATIONS_PER_TARGET=12 × N target functions. Typical
      step: 10-60s. Hard cap: 120s — exceed → partial results + continue.

    Parallel dispatch safety (Phase 5 supports parallel subagents):
    - mutation_check.py mutates target files IN-PLACE with backup/restore,
      protected by an fcntl file-lock on a sidecar .mutlock file.
    - Subagents on DISJOINT target files run concurrently.
    - Subagents on OVERLAPPING target files serialize via the lock.
    - On Windows (no fcntl), the lock is a no-op — orchestrator must
      schedule mutation checks sequentially when targets overlap.

    Why separate from step 3b: 3b catches regressions the FIX itself
    introduced. 3c catches tests that wouldn't catch regressions
    introduced by FUTURE changes. Different failure modes.

3d. VISUAL VERIFICATION — UI layout drift check
    After tests + mutation gate pass, if the task touched UI files AND a
    Phase 4 mockup exists, verify the rendered UI matches the mockup.
    Catches a class of bugs the test suite misses — broken images,
    elements drifted from mockup position, structural layout regressions.

    Inspired by Brian/Notion's /figma verification loop: AI-built UI
    should be verified against the approved visual artifact, not just
    against passing unit tests.

    Trigger conditions (all must be true — otherwise skip):
    - Task modified files matching: *.tsx, *.jsx, *.vue, *.svelte, *.html,
      *.css, *.scss, app/templates/*, views/*, pages/*
    - A dev server is running and reachable on a known URL (from plan
      or from .claude/launch.json)
    - docs/design/<feature>/mockups/*.excalidraw exists from Phase 4

    Run:
    ```
    python skills/claude-flow/scripts/visual_verify.py \
        --url <dev-server-url> \
        --mockup docs/design/<feature>/mockups/<mockup>.excalidraw \
        --threshold 0.15 \
        --json
    ```

    Gate rule:
    - skipped=True → SKIP, proceed to step 4 (Playwright not installed,
      mockup missing, URL unreachable — all graceful, do not block)
    - findings=[] → PASS, proceed to step 4
    - findings with severity=high → FAIL, fix before step 4
    - findings with severity=medium only → WARN, user confirms before step 4

    Max 2 visual-fix cycles → escalate to user.
    Emit failure event with tag: visual-verify-drift.

    Dependency: install Playwright to enable this gate:
        pip install playwright && playwright install chromium
    Without Playwright the gate is a graceful no-op (skip envelope).

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
  No prior step history — the plan is the contract.
```

### Advisor: Mid-Implementation (optional)

Only at genuinely ambiguous decision points. Not routine steps.
Dispatch Opus with: specific decision context from current `$plan` step.
Question: focused on the specific ambiguity.

**When to call:** non-obvious integration patterns, conflicting precedents, step diverging from plan in ways affecting later steps.
**When NOT to call:** routine implementation, standard TDD cycles with clear requirements, unambiguous plan steps.

### Parallel Subagent Dispatch (For Independent Steps)

When the plan has 3+ steps with no dependencies between them:

> **Clarification window:** Implementers dispatched in parallel use the narrow mid-work clarification window — they do not stall on ambiguity. Documented assumptions surface in task output for the Phase 6 reviewer to validate. This is a deliberate trade: batch-level throughput > per-agent precision. See `subagent-driven-development/implementer-prompt.md` for the authoritative rule.

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

**State transition:** If tests+lint pass, transition to phase-5.5. If failed and iteration < 3, increment iteration and retry phase-5. If iteration limit reached, set status to "failed" and surface to user.

**Retry escalation ladder** (applied in order, not all at once):

| Iteration | Action | Model |
|-----------|--------|-------|
| 1 (initial) | Re-read error, fix, re-test | Executor (same) |
| 2 | Same as iteration 1 | Executor (same) |
| 3 (last retry) | **Cross-model diagnosis via /investigator** — see step 3 above for protocol. Fix applied by executor using investigator's evidence. | Investigator on **different** model family; executor unchanged |
| >3 | Surface to user with evidence matrix, cross-model diagnosis output, and all prior retry summaries | — |

**Why cross-model on iteration 3, not earlier:** Iterations 1-2 usually recover from trivial errors (typo, missing import, test-file mismatch). Cross-model dispatch is a real cost; spend it only when the same-model approach has demonstrably exhausted its mental model.
