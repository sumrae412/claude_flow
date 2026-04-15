# Phase 3: Clarification + Requirements (Hard Gate)

<!-- Loaded: after Phase 2 | Dropped: after user approves requirements -->
<!-- Output: $requirements contract -->

<HARD-GATE>
All ambiguities must be resolved and requirements formalized before architecture work begins.
</HARD-GATE>

---

## Step 1: Resolve Ambiguities

Review exploration findings against the original request. Identify **every** underspecified aspect:

- **Edge cases** — What happens when input is empty, duplicated, or malformed?
- **Error handling** — What should the user see when things fail?
- **Integration points** — Which existing systems does this touch?
- **Scope boundaries** — What is explicitly NOT included?
- **Performance** — Will this hit large datasets or high concurrency?
- **Backward compatibility** — Does this change existing behavior?

Present an organized question list to the user. Group questions by category. Wait for answers before proceeding.

**If no ambiguities exist** (rare — usually means the request is very well-specified), state that explicitly and proceed to Step 2.

---

## Step 1.5: Self-Answer Audit (Teach AI to Answer Its Own Questions)

**Before** presenting the question list to the user, run the audit:

```
echo '["<question 1>", "<question 2>", ...]' | \
    python skills/claude-flow/scripts/audit_phase3_questions.py --json
```

For each question flagged `self_answerable: true`:
- Execute the `suggested_lookup` yourself (grep, ls, `alembic heads`, `inject_lookups.py`, etc.)
- Record the result as a resolved ambiguity in `$requirements`
- **Remove the question from the user-facing list**

**Principle** (Brian Lovin, Notion): *"Anytime the AI asks you to do something,
before responding, try your best to see if you could teach the AI to answer
that question for itself."*

Only present genuinely ambiguous (user-intent, preference, policy) questions
to the user. This reduces Phase 3 friction and accelerates the hard gate.

**Signal:** if the audit flags >50% of questions as self-answerable, that's a
signal Phase 2 exploration was shallow — consider running an additional
explorer rather than pestering the user.

The audit is conservative: questions containing intent markers ("should", "do
you want", "how should we handle") are NEVER flagged self-answerable, even if
they mention files or schemas.

---

## Step 2: Quality Gate

<SKIP-CONDITION>
If the Phase 2 advisor already scored all 4 quality axes as PASS (carried forward in $exploration.quality_gate), skip this step — proceed directly to Step 3.
</SKIP-CONDITION>

**Only runs when Phase 2 advisor flagged failures or was skipped.** Re-score the 4 axes after ambiguity resolution:

1. **Objective Clarity** — Deliverable stateable as one-sentence outcome? FAIL: vague, unmeasurable, or activity-not-outcome.
2. **Service Scope** — Affected files/modules identifiable from exploration? FAIL: no specific locations.
3. **Testability** — All behaviors expressible as WHEN/THEN? FAIL: "should work well", "be fast", etc.
4. **Completeness** — All edge cases have resolutions (including those self-answered by the Step 1.5 audit)? FAIL: unresolved edges, unspecified error handling.

**Gate:** All pass → Step 3. Any fail → present failures with questions, loop until all pass.

---

## Step 3: Synthesize Structured Requirements

After all ambiguities are resolved and the quality gate passes, populate the `$requirements` contract (see `contracts/requirements.schema.md`).

This contract flows downstream to Phase 4 (architecture references it), Phase 4c (validates plan coverage against it), and Phase 6 (reviewers check adherence).

**Present to user for approval.** The structured requirements are the contract for everything downstream. If the user provides feedback, revise and re-present.

```
◆ USER APPROVES structured requirements before architecture ◆
```

---

## Optional: Export Context Packet (PRP)

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
(Reference or inline the structured $requirements from Step 3)

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

**State transition:** Transition to phase-4.

---

**Output:** Populate `$requirements` contract (see `contracts/requirements.schema.md`). User must approve before Phase 4.
