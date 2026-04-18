# Spike: Single-Markdown Coordination Protocol for Phase 5

**Date:** 2026-04-17
**Branch:** `feat/blog-insights-20260417`
**Source plan:** `docs/plans/2026-04-17-blog-insights-integration.md` (Task 3)
**Verdict (TL;DR):** **PARTIAL ADOPT** — consolidate executor-facing *instructions* into a single `references/phase-5-executor-protocol.md`; keep the retry-ladder state machine in orchestrator code.

---

## Context

Cursor's multi-agent kernel-optimization harness reportedly used *one markdown file* as the entire coordination protocol — output format, rules, tests, acceptance criteria. The attraction: single source of truth, easy to diff, trivially auditable, cheap to propagate to every subagent (prepend the file, done).

The question this spike answers: can claude-flow's Phase 5 (implementation with TDD + retry ladder) collapse similarly, or does Phase 5 carry behaviors that a static protocol file cannot express?

## Sources reviewed

- `claude-skills/claude-flow/phases/phase-5-implementation.md` (entire file, 353 lines)
- `claude-skills/claude-flow/references/failure-taxonomy.md`
- MEMORY: `cross_model_retry_ladder.md`, `explain_before_fix_gate.md`, `retry_loop_policy.md`, `autonomous_retry.md`

## Step 1: Enumerated Phase 5 retry & control-flow behaviors

Pulled from phase-5-implementation.md via `grep -nE 'iter|retry|escalat|cross.model'` and surrounding context reads. 14 load-bearing behaviors:

1. `/investigator` auto-dispatch when iter-1 error is not self-explanatory
2. Explain-before-fix gate between iter-1 and iter-2 (no-code-written prompt; MEMORY `explain_before_fix_gate.md`)
3. Iter-2 escalates thinking budget on same executor
4. Iter-3 cross-model handoff — Sonnet → Opus or Opus → Sonnet (MEMORY `cross_model_retry_ladder.md`)
5. Iteration cap at 3 → set status "failed", surface to user
6. GUARD (Step 3b) — scoped regression check with 3-level scope selection (module → package → full suite)
7. GUARD max 2 fix cycles → escalate to user; failure tagged `guard-regression`
8. Context extraction (Step 3e) — inline Sonnet YAML synthesis appended to `$diff.context_facts`
9. Context-fact injection into next task's subagent prompt as "Known context from earlier tasks: ..."
10. Mutation gate (Step 3c, referenced) — 2 strengthen cycles then tag `mutation-gate-exceeded`
11. Adversarial-blocker injection from Phase 6 sub-threshold scores into iter-N+1 prompt under "Break cases to address"
12. Conditional specialist review dispatch (migration-reviewer, google-api-reviewer, async-reviewer) gated on file-pattern match
13. Dependency-aware dispatch — `data`/`build` sequential, `knowledge` parallel, `shared_prerequisite` before `value_unit`
14. Failure-taxonomy tagging on every event (13 tags in `failure-taxonomy.md`)

## Step 2: Feasibility table — markdown protocol vs orchestrator code

**Partial vs No rule:** *Partial* = executor-facing text is declarative AND the orchestrator trigger is a simple one-line conditional. *No* = executor-facing text may be declarative, but the orchestrator needs multi-step state (iteration counter, artifact from a prior step, failure-type dispatch) to decide whether to include it.

| # | Behavior | Can live in a markdown protocol file? | If not, why? |
|---|----------|--------------------------------------|--------------|
| 1 | `/investigator` dispatch on non-self-explanatory iter-1 error | **No** | Conditional routing on the error string — requires caller logic to classify and dispatch a sibling skill |
| 2 | Explain-before-fix gate between iter-1 and iter-2 | **No** | Control flow — requires a separate model call with a specific prompt whose input is the iter-1 failure artifact |
| 3 | Iter-2 escalated thinking budget on same executor | **No** | Runtime API-level parameter (`thinking.budget_tokens`) — the caller sets it, not the prompt |
| 4 | Iter-3 cross-model switch (Sonnet ↔ Opus) | **No** | Runtime dispatch choice — the caller selects the model, not the prompt |
| 5 | Iteration cap at 3 → surface to user | **No** | State counter held by orchestrator; static markdown has no notion of "iteration N" |
| 6 | GUARD scoped regression check, 3-level scope selection | **Partial** | The *rule* ("default to module scope; widen if multi-file change") is declarative and can live in the protocol. The *execution* (pytest with the right path) is caller-side |
| 7 | GUARD max 2 fix cycles | **No** | Counter/state machine |
| 8 | Context-facts YAML extraction prompt (Step 3e) | **Yes** | The prompt template and output schema are purely declarative; orchestrator only needs to fire the prompt |
| 9 | Context-facts injection into next subagent | **Partial** | The injection *format* ("Known context from earlier tasks: ...") is declarative. The injection *trigger* (before each non-first task) is caller logic |
| 10 | Mutation gate, 2 strengthen cycles | **No** | Counter + test-runner-dependent loop |
| 11 | Adversarial-blocker formatting into iter-N+1 prompt | **Partial** | The render template ("Break cases to address:") is declarative. Whether to include the section (conditioned on `{adversarial_blockers}` non-empty) is caller logic |
| 12 | Conditional specialist review dispatch by file pattern | **No** | File-glob → agent routing requires runtime evaluation |
| 13 | Dependency-aware parallel vs sequential dispatch | **No** | DAG traversal over `$plan` — orchestrator responsibility |
| 14 | Failure-taxonomy tagging on events | **Yes** | The tag list + definitions are a pure declarative checklist |
| — | TDD cycle (write failing test → implement → green → guard → extract → static analysis → mark complete) | **Yes** | The cycle description is a checklist the executor follows; no conditional routing |
| — | Defensive-pattern guidance (UI/backend tables from "Best Practices Applied Throughout") | **Yes** | Static tables — the existing table already IS the protocol |
| — | External-API docs-fetch gate | **Partial** | The rule ("if step touches external API, invoke `/fetch-api-docs` first") is declarative. The *invocation* is a sibling skill call — caller logic |

**Summary:** 4 rows "Yes", 4 rows "Partial", 9 rows "No" (17 total). The No-rows are all variants of the same root cause: control flow, state counters, conditional dispatch, and runtime API-level parameters. A static markdown file cannot gate, count, or choose a model.

## Step 3: Verdict

### PARTIAL ADOPT

The data in Step 2 disagrees with both the FULL-ADOPT framing (Cursor-style single-file everything) and the ABANDON framing (keep Phase 5 as-is). The correct cut line is between *declarative instructions to the executor* and *orchestrator state machine*.

**What to adopt from the Cursor pattern:**

Consolidate the executor-facing instruction text — currently scattered across Phase 5 and its references — into a single `references/phase-5-executor-protocol.md` that the orchestrator prepends to every implementer dispatch. Candidates for consolidation (all Yes/Partial rows):

- TDD cycle checklist (test-first → implement → verify → guard → extract → static analysis)
- Defensive-pattern tables (UI + backend)
- Context-facts extraction prompt + YAML schema
- Context-facts injection format ("Known context from earlier tasks: ...")
- Break-case render template (iter-N+1 adversarial block)
- Failure-taxonomy tag table
- GUARD scope-selection rule (module → package → full)
- External-API docs-fetch rule

Benefit: implementers receive one coherent contract instead of cherry-picked excerpts; easier to audit prompt drift; single place to edit when a rule changes.

**What must stay in orchestrator code:**

Everything in the "No" rows — the retry ladder (iter 1/2/3 state), cross-model dispatch, iteration caps, guard cycles, mutation cycles, conditional specialist routing, dependency-aware parallel dispatch, `/investigator` gating. These are irreducibly stateful or conditional and cannot be expressed as a static prompt file.

### Why Cursor's pattern worked and ours only partially ports

Cursor's harness had:
- **Single objective** — benchmark speedup; one scalar to maximize
- **Fixed tool** — one benchmark harness; no conditional routing over tool choice
- **Stateless retry** — each candidate is independent; no memory of prior attempts shapes the next prompt

claude-flow Phase 5 has:
- **Multi-objective** — tests pass, lint pass, guard pass, mutation gate pass, adversarial-blocker breakcases addressed
- **Conditional tool/model routing** — `/investigator` on classified errors, specialist reviewers on file patterns, cross-model switch at iter-3
- **Stateful retry** — iter-N+1 prompt changes based on iter-N artifacts (explain-before-fix, adversarial blockers, context facts accumulated across tasks)

The three "No" categories (control flow, state counters, conditional dispatch) are structural differences, not incidental complexity. No amount of protocol-file engineering collapses them.

## Backlog action

Added to `docs/backlog/2026-q2.md`:

> - [ ] Extract executor-facing instructions from phase-5-implementation.md into references/phase-5-executor-protocol.md — see docs/spikes/2026-04-17-single-markdown-coordination.md

The extraction itself is a follow-up task, not this spike. Estimated effort: a few hours, not days; mostly mechanical, guided by the "Yes"/"Partial" rows above.

## Ruled Out

- **Full adopt (everything in one protocol file)** — rejected. 9/17 rows are orchestrator-only. Forcing them into markdown would either require a new templating/conditional-rendering language (reinventing the orchestrator in prompt form) or silently drop behaviors (regression).
- **Abandon (keep scatter)** — rejected. The executor-facing instruction text genuinely IS scattered — phase-5 doc + references/test-driven-development.md + references/defensive-*.md + MEMORY entries + inline prompt fragments. Consolidation has independent value beyond the Cursor-pattern framing.
- **Collapse the retry ladder into a single "try harder" prompt** — rejected. The ladder's design (iter-1 investigator dispatch, iter-2 explain-before-fix, iter-3 cross-model) is explicitly calibrated against the confirmation-bias failure mode documented in MEMORY `cross_model_retry_ladder.md`. A flat retry prompt would regress that calibration.
- **Treat the spike as a coding task** — rejected. The plan specifies "design spike that produces a decision doc, not a rewrite" (plan line 23). The extraction work belongs in a separate shippable task with its own TDD/review cycle.
