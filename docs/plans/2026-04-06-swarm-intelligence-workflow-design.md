# Swarm Intelligence for code-creation-workflow

**Date:** 2026-04-06
**Branch:** feat/self-improvement-engine
**Status:** Design approved, ready for implementation planning

## Problem

The code-creation-workflow dispatches many subagents across 6 phases, but they operate in isolation. Explorers don't know what other explorers found. Architects don't debate. Implementation agents repeat each other's mistakes. Reviewers can't see systemic patterns across findings. No agent learns from past sessions.

## Design Principles

- **Swarm intelligence:** Complex behaviors emerge from simple agent interactions and shared state
- **Collective problem solving:** Agents build on each other's findings rather than working in isolation
- **Adaptive specialization:** Agents develop expertise based on demonstrated competence (Bayesian priors)
- **Distributed cognition:** Knowledge distributed across agents with smart aggregation and persistent memory

## Approach: Layered Emergence

Simple tasks get smart routing (registry-informed dispatch). Complex tasks get full swarm treatment (inter-agent communication, adversarial debate, collaborative review). A complexity classifier decides the tier.

| Tier | Trigger | Agent behavior |
|------|---------|---------------|
| simple | Fast-path (existing) | Single agent, no swarm |
| moderate | Classifier score 4-6 | Registry-informed dispatch, agents independent |
| complex | Classifier score 7+ | Shared scratchpad, adversarial debate, staged review, build-state |

---

## Section 1: Complexity Classifier

Runs in Phase 1 Discovery after the existing fast-path check.

### Two-step classification

**Step 1 — Static scoring** (fast, runs immediately):

| Axis | Score 1 (low) | Score 2 (moderate) | Score 3 (high) |
|------|--------------|-------------------|----------------|
| Reasoning depth | Single concern, no interactions | 2-3 interacting constraints | 4+ constraints that affect each other |
| Ambiguity | One obvious approach | 2-3 viable approaches | Open-ended, architecture matters |
| Context dependency | Local/self-contained | Touches 2-3 existing systems | Must understand cross-cutting invariants |
| Novelty | Existing pattern to follow | Partial patterns exist | Genuinely new territory for this codebase |

Sum: 4-6 = `moderate`, 7-9 = `complex`, 10-12 = `complex+` (reserved for future)

Based on cognitive complexity (inspired by HardEval framework, arxiv 2407.21227), not surface-level signals like file count. A single-file concurrency fix can be deeply complex; touching 10 files for a rename is trivially simple.

**Step 2 — Degradation probe** (dynamic, runs at Phase 2 boundary):

1. Dispatch a single fast explorer (sonnet, minimal prompt) with reduced context
2. Evaluate: did it find the right files? Identify key integration points? Miss obvious patterns?
3. If reduced-context probe succeeds → static score over-estimated, downgrade tier
4. If probe produces poor results → confirmed complex, maintain or upgrade tier

Cost: one extra sonnet call. Catches cases where static scoring gets it wrong.

**Registry feedback loop:** After session, record static score + probe result + tier used + whether tier was sufficient (did Phase 5 hit 3-strike? did Phase 6 find critical issues?). Over time, static scoring weights calibrate via complexity_calibration in the registry.

**User override:** User can force any tier at any time.

---

## Section 2: Phase 2 — Tiered Exploration

### Moderate tier: Registry-informed dispatch

1. Classify task via smart-exploration (as today)
2. Query registry: "For [task_category] in [project_type], which explorer prompt variants have highest findings-used rate?"
3. Rank prompts by prior effectiveness
4. Dispatch top 2 variants (registry-selected, not hardcoded)
5. Record: files found per explorer, files hydrated by orchestrator

Key metric: **findings-used rate** — not "did explorer find files" but "did orchestrator actually hydrate those files."

### Complex tier: Collaborative exploration with scratchpad

Explorers share findings via staggered dispatch:

1. Explorer A dispatches immediately (broadest prompt)
2. Explorer A writes to `.claude/swarm/exploration-scratchpad.json`:
   - key_files, patterns_found, gaps identified
3. Explorer B dispatches WITH scratchpad in prompt:
   "Explorer A found [files] and identified [patterns]. They couldn't determine: [gaps]. Fill those gaps and explore adjacent areas they missed."
4. Explorer B writes its findings to scratchpad
5. Optional Explorer C dispatches targeting remaining gaps

Staggered (not parallel) because later explorers build on earlier ones. Adds ~30s per explorer but eliminates redundant exploration.

### Scratchpad lifecycle

Created at Phase 2 start. Read during context hydration. Carried into Phase 4 architect prompts. Archived into exploration-log on session end. Ephemeral working file deleted.

### Persistence

All exploration data persists to `.claude/swarm/exploration-log/SESSION_ID.json` for periodic review and cross-session learning. Includes: files found/hydrated per explorer, gaps identified/filled, prompt variants used, duration.

### Missed-context audit

After each explorer completes, audit runs:

1. Extract claims/searches the agent made (files it couldn't find, patterns it said don't exist)
2. Cross-reference against CLAUDE.md, MEMORY.md, docs/, README, and the agent's own prompt
3. Classify each miss:
   - `available_in_prompt` — info was in agent's prompt, agent missed it (prompt quality issue)
   - `available_in_project` — info exists in project files, wasn't loaded (Phase 0 gap)
   - `available_in_memory` — info exists in MEMORY.md, wasn't injected (memory-injection gap)
   - `not_available` — genuinely missing (not a miss)
4. Log to `.claude/swarm/missed-context-log/SESSION_ID.json`

---

## Section 3: Phase 4 — Tiered Architecture

### Moderate tier: Registry-weighted architects with exploration context

1. Query registry for user's historical architecture preferences
2. ALL architect prompts receive:
   - Full exploration scratchpad (not just orchestrator's summary)
   - Gap chain: what gaps were found, which were resolved, which remain
   - Explorer disagreements: areas where explorers characterized patterns differently
3. Dispatch 3 architects with registry-weighted optimization targets
4. Weight synthesis toward historically preferred style
5. Sharpen contrarian based on registry data

### Complex tier: Adversarial debate + gap detection

**Round 1** (parallel):
- Architect A: simplicity (receives full scratchpad)
- Architect B: separation (receives full scratchpad)
- Architect C: contrarian (receives full scratchpad)

**Gap detection** (between Round 1 and Round 2):
- Scan all 3 proposals for references to files/patterns not in scratchpad
- Detect assumptions architects made that explorers didn't verify
- Detect questions architects raised
- If gaps found: dispatch targeted gap-fill explorer (single sonnet agent, narrow scope)
- Gap-fill results injected into Round 2 and synthesis judge
- Gap-fill results appended to persistent scratchpad
- If no gaps: proceed directly to Round 2

**Round 2** (parallel):
- Critic A: rebuts B and C from simplicity lens (+ gap-fill findings)
- Critic B: rebuts A and C from separation lens (+ gap-fill findings)
- Critic C: rebuts A and B from contrarian lens (+ gap-fill findings)

**Round 3** (single opus agent):
- Synthesis judge reads all proposals + all rebuttals + gap-fill findings
- Produces recommendation with explicit reasoning:
  "Adopted X from Architect A because Critic B's objection was addressed by..."
  "Rejected Y from Architect B because Critic A showed it violates..."

Cost: 3 extra sonnet calls (critics) + 1 opus call (synthesis) + optional 1 sonnet (gap-fill). Complex tier only.

### Feedback to Phase 2

Gap detections logged as exploration misses. Teaches future exploration: "For tasks in this area, exploration consistently misses [X] — add to default scope."

### Missed-context audit for architects

Did any architect propose something violating CLAUDE.md or MEMORY.md constraints? Did a critic catch it? Did it survive to the user? Logged per session.

---

## Section 4: Phase 5 — Tiered Implementation

### Moderate tier: Registry-informed execution

Per plan step:
1. Query registry for historical failure rate and thinking budget by domain
2. Set thinking budget: <10% failure → "think about", 10-30% → "think harder", >30% → "ultrathink"
3. Skip specialist reviewers with zero findings across 5+ dispatches (re-enable every 10th session)
4. Execute with TDD as today
5. Record: domain, thinking budget, pass/fail, retry count, specialist findings

### Complex tier: Shared build-state awareness

**Build-state** (`.claude/swarm/build-state.json`):

Before first step, create empty build-state. After each step, agent writes:

```json
{
  "step": 3,
  "files_created": ["app/services/billing.py"],
  "files_modified": ["app/models/invoice.py"],
  "interfaces_exposed": ["BillingService.process_refund(invoice_id, amount)"],
  "patterns_used": ["service-layer with repository pattern, matching client_service.py"],
  "decisions_made": ["Used Decimal for amounts — precision matters"],
  "gotchas_encountered": ["Nullable refunded_at column in existing rows"],
  "failed_approaches": [
    { "approach": "Raw SQL batch update", "why_failed": "Bypassed ORM event hooks", "lesson": "Always use ORM — other systems subscribe to model events" }
  ],
  "test_files": ["tests/test_billing_service.py"]
}
```

Next agent reads build-state and knows: what interfaces exist, what patterns were established, what was tried and didn't work.

Failed-approach propagation is the swarm equivalent of pheromone trails — marking paths that don't work so later agents avoid them.

### Full context chain per implementation agent

Each agent receives:
1. Plan step (specific task)
2. Architecture decision (why this approach, what trade-offs)
3. Exploration scratchpad (what explorers found about this area)
4. Build-state (what previous agents built, patterns, decisions)
5. Failed-approach log (what was tried and didn't work)
6. Gap-fill findings (if Phase 4 filled gaps in this area)
7. Registry priors (historical failure rate, recommended thinking budget)
8. Missed-context from prior steps (flagged if previous agents missed available info)

### Agent-initiated signals

Implementation agents return structured signals beyond pass/fail:

- `completed` — normal success
- `completed_with_deviation` — succeeded but deviated from plan. Includes: what changed, which downstream steps affected
- `completed_with_discovery` — succeeded and found something plan didn't anticipate. Includes: what was found, recommendation for plan adaptation
- `blocked` — can't proceed, design problem not code problem. Includes: blocker description, suggestion for upstream change

Orchestrator processes signals before dispatching next step. `completed_with_deviation` triggers architecture deviation check immediately.

### Architecture deviation detection

After every 3 completed steps (or immediately on any deviation signal):

- Compare build-state against architecture decision
- Pattern deviations: "Plan prescribed X, but steps used Y"
- Interface deviations: "Planned interface was A, implemented as B"
- Assumption violations: "Architecture assumed X, step discovered not-X"

If >50% of steps deviated → PAUSE, surface to user
If single critical assumption violated → PAUSE immediately

### Collaborative rescue on failure

Before entering retry loop:

1. Package failure context: error output + build-state + what was attempted
2. Query registry: "Which agent types have highest success rate for [error_class] in [domain]?"
3. If different agent type has significantly higher success rate → dispatch that type with full failure context
4. If no better type exists → fall back to existing retry loop

### Parallel dispatch (complex tier)

Independent steps can run in parallel with build-state:

1. All parallel agents receive same build-state snapshot
2. All write to build-state on completion
3. Orchestrator merges entries before dispatching next sequential step
4. Conflicting pattern decisions flagged: "Agent A chose X, Agent B chose Y" — resolved before proceeding

### Persistence

Build-state archived into exploration-log on session end. Per-step metrics, failed approaches, deviations, discoveries, rescue outcomes all recorded. Pattern decisions feed future sessions. Gotchas feed MEMORY.md via session-learnings.

---

## Section 5: Phase 6 — Tiered Review

### Moderate tier: Registry-selective dispatch

Classify reviewers by registry data:

| Tier | Criteria | Action |
|------|----------|--------|
| HIGH VALUE | >20% finding rate AND >50% accepted | Full thinking budget |
| MODERATE VALUE | Findings exist, mixed acceptance | Reduced thinking budget |
| LOW VALUE | <5% finding rate across 5+ dispatches | Skip (re-enable every 10th session) |
| UNKNOWN | <5 dispatches | Run with default budget (building priors) |

Dispatch in priority order: HIGH → MODERATE + UNKNOWN → skip LOW.

### Complex tier: Collaborative review with staged findings

**Wave 1** (parallel — highest-value reviewers):
- Code Reviewer A, Security Reviewer, Silent Failure Hunter
- Write findings to `.claude/swarm/review-findings.json` with areas_reviewed and patterns_noticed

**Wave 2** (parallel — receives Wave 1 findings):
- Code Reviewer B: "Wave 1 found [patterns]. Check if these extend to areas they didn't review."
- QA Edge-Case Reviewer: "Wave 1 found these bugs. Are there tests covering the fixed behavior?"
- Production Readiness: "Security reviewer found [issues]. Verify fixes are production-safe."

**Wave 3** (single agent — meta-reviewer):
Receives ALL findings + build-state. Tasks:

1. **Pattern escalation:** "Reviewers A and C both found error handling issues in different files → SYSTEMIC, not isolated"
2. **Finding deduplication:** Merge overlapping findings from different reviewers
3. **Priority synthesis:** Rank findings by actual impact, not reviewer-assigned severity
4. **Gap detection:** "No reviewer examined [area]. Build-state shows complexity there."
5. **Contradiction resolution:** If Reviewer A says "fine" and Reviewer B says "dangerous" → investigate, pick side with reasoning

Pattern escalation is the key swarm behavior — systemic issues only become visible when you see findings from multiple reviewers side by side.

### Missed-context audit for reviewers

For each genuine bug found in review:
1. Was this catchable by the implementation agent? (info in build-state, scratchpad, or architecture?)
2. Was this catchable by Phase 5 fresh-eyes self-review?
3. Was this documented in CLAUDE.md or MEMORY.md?

Each "yes" = missed-context event, logged to improve earlier phases.

### Review → Exploration feedback

After fixes: log which areas review found issues that exploration didn't flag. Teaches future Phase 2: "When working in [area], always explore [concern] — review historically finds issues here."

---

## Section 6: Agent Registry + Infrastructure

### Data model

**Global registry** (`~/.claude/swarm/agent-registry.json`):

```json
{
  "schema_version": 2,
  "agents": {
    "agent-type:prompt-variant": {
      "prior": { "alpha": 1, "beta": 1 },
      "dispatches": 0,
      "findings_produced": 0,
      "findings_used": 0,
      "findings_used_rate": 0.0,
      "missed_context_count": 0,
      "last_dispatched": null,
      "last_updated": null
    }
  },
  "complexity_calibration": {
    "weights": {
      "reasoning_depth": 1.0,
      "ambiguity": 1.0,
      "context_dependency": 1.0,
      "novelty": 1.0
    },
    "history": []
  },
  "global_patterns": {
    "architecture_preferences": {
      "simplicity": 0.33,
      "separation": 0.33,
      "contrarian": 0.33
    }
  },
  "project_fingerprints": {}
}
```

**Project overlay** (`.claude/swarm/agent-registry.json`):

Same agents and complexity_calibration structure, scoped to project. Plus project_fingerprint:

```json
{
  "project_fingerprint": {
    "languages": ["python"],
    "frameworks": ["fastapi", "sqlalchemy"],
    "has_migrations": true,
    "has_external_apis": true,
    "layer_count": 4
  }
}
```

**Exploration log** (`.claude/swarm/exploration-log/SESSION_ID.json`):

Full session record: task, tier, degradation probe results, per-explorer data (prompt variant, files found/hydrated, gaps, duration), architecture proposals/critiques/synthesis, per-implementation-step data (domain, thinking budget, pass/fail, retries, failed approaches, deviations, discoveries, signals), review waves/meta-reviewer/escalations.

**Missed-context log** (`.claude/swarm/missed-context-log/SESSION_ID.json`):

Per-miss entries: phase, agent, miss_type (available_in_prompt | available_in_project | available_in_memory | not_available), what was missed, where it existed, impact, severity. Plus summary aggregates.

### Bayesian update mechanics

Beta distribution per agent: alpha (successes), beta (failures). Initial: alpha=1, beta=1 (uniform).

Success/failure signals by phase:

| Phase | Success | Failure |
|-------|---------|---------|
| 2 Exploration | File found AND hydrated | File found but not hydrated |
| 4 Architecture | Ideas adopted in final plan | Ideas fully rejected |
| 4 Critics | Critique changed synthesis outcome | Critique ignored |
| 5 Implementation | Step passed first attempt | Step entered retry loop |
| 5 Rescue | Resolved failure another agent couldn't | Failed to resolve |
| 6 Review | Finding accepted and fixed | Finding dismissed |
| 6 Meta-review | Pattern escalation led to systemic fix | Escalation was noise |

**Decay:** Every 30 days: alpha = max(1, alpha * 0.85), beta = max(1, beta * 0.85). Prevents stale priors.

**Blending:** Project overlay < 5 dispatches: effective = 0.7 * project + 0.3 * global. At 15+ dispatches: project only.

### Dispatch protocol

- effectiveness > 0.3 → DISPATCH
- effectiveness 0.1-0.3 AND confidence < 10 → DISPATCH (insufficient data)
- effectiveness < 0.1 AND confidence > 15 → SKIP
- effectiveness 0.1-0.3 AND confidence > 15 → DISPATCH with reduced budget
- Re-enable skipped agents every 10th session

### Retention policy

| Store | Full detail | Summary | Delete |
|-------|------------|---------|--------|
| Exploration logs | Last 30 sessions | 30-90 sessions (counts only) | After 90 sessions |
| Missed-context logs | Last 30 sessions | Aggregated into registry | After 30 sessions |
| `available_in_prompt` misses | Permanent | — | Never (prompt quality signals) |
| Systemic pattern escalations | Permanent | — | Never (exploration scope signals) |
| Registry | Permanent | — | Decay handles staleness |
| Complexity calibration history | Last 50 entries | — | Oldest pruned |

### Concurrency handling

Append-only event log + periodic compaction:

- During session: append events to `~/.claude/swarm/registry-events.jsonl` (POSIX atomic append)
- On session start: compact — read registry + all events, apply Bayesian updates, write new registry, truncate events
- No data loss from concurrent sessions

### Inter-project learning (project fingerprints)

Projects get fingerprints (languages, frameworks, capabilities). When computing global priors for new project:

1. Compute fingerprint
2. Find similar projects: similarity = |tag intersection| / |tag union|
3. Weight priors by similarity: 0.8 similar project contributes 80%, 0.2 similar contributes 20%

New Python/FastAPI projects inherit strong priors from other Python/FastAPI projects, weak priors from React projects.

### Schema versioning

All files include `schema_version`. On load: check version, apply sequential migrations if behind. Migrations defined in `references/registry-migrations.md`. Never delete during migration — deprecated fields move to `_deprecated`.

### Gitignore guidance

**Gitignored** (ephemeral working state):
- `.claude/swarm/build-state.json`
- `.claude/swarm/exploration-scratchpad.json`
- `.claude/swarm/review-findings.json`
- `.claude/swarm/registry-events.jsonl`

**Committed** (project knowledge worth sharing):
- `.claude/swarm/agent-registry.json` (project overlay)
- `.claude/swarm/exploration-log/`
- `.claude/swarm/missed-context-log/`

### Acting on periodic review outputs

| Output | Mechanism | Approval |
|--------|-----------|----------|
| Registry weight adjustment | Update complexity_calibration.weights directly | Automatic (data-driven) |
| Agent prompt improvement | session-learnings proposes skill revision | Human approves |
| CLAUDE.md update | claude-md-management:revise-claude-md invoked | Human approves |
| MEMORY.md gotcha entry | Standard memory write | Automatic |
| Explorer scope expansion | smart-exploration prompt library update | Human approves |
| Workflow skill revision | session-learnings proposes SKILL.md diff | Human approves |

Pattern: data-driven adjustments (weights) are automatic. Prompt and skill changes require human approval.

### Periodic review analysis dimensions

1. **Agent effectiveness:** Rank by score, identify retirements and investments, compare prompt variants
2. **Missed-context trends:** Phase miss rates, source type miss rates, improvement over time, recurring misses as MEMORY.md candidates
3. **Complexity calibration:** Static score vs actual outcome, signal weight adjustments, under/over-tiering analysis
4. **Cross-phase feedback health:** Exploration → implementation flow, review → exploration feedback, failed-approach prevention, deviation detection accuracy
5. **Swarm effectiveness (complex tier):** Staggered vs parallel exploration quality, debate round impact on outcomes, collaborative review systemic pattern detection, build-state consistency gains
