# Swarm Protocols

> Operational instructions for all swarm behaviors. "How" only — for "why," see design doc.
> Design doc: `docs/plans/2026-04-06-swarm-intelligence-workflow-design.md`
> Schemas: `references/swarm-schemas.md`

---

## 1. Complexity Classifier

Runs in Phase 1 after fast-path check. Produces tier: `simple` | `moderate` | `complex`.

**Step 1 — Static scoring** (run immediately):

| Axis | Score 1 — low | Score 2 — moderate | Score 3 — high |
|------|--------------|-------------------|----------------|
| Reasoning depth | Single concern | 2-3 interacting constraints | 4+ constraints affecting each other |
| Ambiguity | One obvious approach | 2-3 viable approaches | Open-ended, architecture matters |
| Context dependency | Local / self-contained | Touches 2-3 systems | Must understand cross-cutting invariants |
| Novelty | Existing pattern to follow | Partial patterns exist | Genuinely new territory |

Sum → `4-6 = moderate`, `7-9 = complex`, `10-12 = complex+` (reserved).

**Step 2 — Degradation probe** (run at Phase 2 boundary, complex/moderate only):
1. Dispatch one Sonnet explorer with minimal context and reduced prompt.
2. Evaluate: did it find the right files? Identify integration points? Miss obvious patterns?
3. If probe succeeds → downgrade tier by one level.
4. If probe fails → confirm tier, proceed.

Record result to `complexity_calibration.history` (see `swarm-schemas.md#complexity-calibration-history-entry`).

**Registry feedback:** After session, record `static_score`, `probe_result`, `tier_used`, `tier_sufficient` to history. Weights in `complexity_calibration.weights` auto-adjust when data accumulates.

**User override:** Accept `--tier=simple|moderate|complex` at any point. Skip classifier, use stated tier.

---

## 1b. Thinking Budget Auto-Tuning

Runs at every phase dispatch. Replaces the static phase→thinking mapping.

**Inputs:**
- `phase` — discovery | exploration | clarification | architecture | implementation | review
- `tier` — from classifier (simple/moderate/complex)
- `domain` — task type from smart-exploration (routes, migrations, tests, auth, ui, etc.)
- `registry` — `memory/agent-registry.json`

**Resolution:**
```bash
python3 scripts/thinking-budget.py --phase <phase> --tier <tier> --domain <domain> --registry memory/agent-registry.json
```

Returns one of `think` | `think harder` | `ultrathink`.

**Escalation rules:**
- `< 10%` retry rate for (phase, domain) → use base budget
- `10-30%` → escalate one level
- `> 30%` → escalate two levels (capped at ultrathink)

**Safety floor:** Architecture phase never below `think harder`.

**Override:** `--override <budget>` forces a specific value, skipping auto-selection.

Full table: `docs/plans/2026-04-07-auto-tuning-thinking-budgets-design.md`

---

## 2. Exploration Scratchpad

Complex tier only. Staggered (not parallel) dispatch — each explorer builds on the previous.

**Dispatch sequence:**
1. Create empty `exploration-scratchpad.json` (see schema).
2. Dispatch Explorer A (broadest prompt, no scratchpad yet).
3. Explorer A writes findings to scratchpad: `key_files`, `patterns_found`, `gaps_identified`.
4. Dispatch Explorer B with scratchpad injected (template below).
5. Explorer B appends its findings, fills gaps where possible.
6. If unresolved gaps remain, dispatch Explorer C (targeted).

**Explorer B prompt template:**
```
Explorer A found these files: [key_files from scratchpad]
They identified these patterns: [patterns_found]
They could not determine: [gaps_identified]

Your job: fill those gaps and explore adjacent areas they missed.
Do NOT re-explore areas already covered. Focus on:
- [gap 1]
- [gap 2]
Report what you found and identify any new gaps you couldn't resolve.
```

**Explorer C prompt template:**
```
Explorers A and B have covered: [key_files, patterns_found]
Remaining unresolved gaps: [gaps still in scratchpad]

Explore ONLY the following — do not re-examine covered areas:
- [remaining gap 1]
- [remaining gap 2]
```

**Scratchpad lifecycle:**
- Created: Phase 2 start
- Read by: subsequent explorers, architect prompts, all implementation agents
- Archived: session end → `exploration-log/SESSION_ID.json`
- Deleted: ephemeral file removed after archival

Run missed-context audit after each explorer completes (see Section 7).

---

## 3. Adversarial Architecture

Complex tier only. Three rounds + optional gap-fill between Round 1 and Round 2.

**Round 1** (parallel, all receive full scratchpad):
- Architect A: optimize for simplicity
- Architect B: optimize for separation of concerns
- Architect C: reuse — challenge assumptions, propose alternative framing

**Gap detection** (between Round 1 and Round 2):
1. Collect all 3 proposals.
2. Scan for references to files/patterns NOT in scratchpad.
3. Identify assumptions explorers didn't verify and questions architects raised.
4. If gaps found: dispatch one Sonnet gap-fill explorer with narrow scope:
   ```
   Architects proposed [X] but exploration didn't verify [assumption].
   Check ONLY: [specific files/patterns to check].
   Return findings as key_files + what each reveals about the assumption.
   ```
5. Append gap-fill findings to scratchpad. Pass to Round 2 and synthesis judge.
6. Log gap detections as exploration misses in `missed-context-log`.
7. If no gaps: skip to Round 2 immediately.

**Round 2** (parallel, each critic receives gap-fill findings + all Round 1 proposals):

Critic A rebuttal prompt template:
```
You are Critic A (simplicity lens). Read these architecture proposals:
[Architect A proposal]
[Architect B proposal]
[Architect C proposal]
Gap-fill findings: [gap-fill results or "none"]

Rebut proposals B and C. For each objection: cite the specific simplicity
violation, reference supporting evidence from exploration or gap-fill.
Format: OBJECTION | EVIDENCE | SEVERITY (blocking/major/minor)
```

Repeat for Critic B (separation lens) and Critic C (reuse lens), adjusting lens description.

**Round 3 — Synthesis judge** (single Opus agent):
```
You are the synthesis judge. Read all proposals and critiques.

Architecture proposals: [A, B, C]
Critiques: [Critic A, B, C rebuttals]
Gap-fill findings: [results or "none"]
Historical preference (from registry): simplicity=[weight] separation=[weight] reuse=[weight]

Produce a final recommendation. For each major decision:
- State which proposal you adopted and why
- State which objection you rejected and why (cite critic + counterevidence)
Format: DECISION | ADOPTED FROM | REJECTED OBJECTION | REASONING
```

---

## 4. Build-State

Complex tier only. Written by each implementation agent; read by all subsequent agents.

**Per-step write protocol:**
1. Before starting: read current `build-state.json` — know what exists.
2. Execute step.
3. On completion (pass or fail): write step entry to `build-state.steps[]` (see schema).
4. For each failed approach attempted: append to `failed_approaches[]`.
5. For parallel dispatch: all agents receive same build-state snapshot. After all complete, orchestrator merges entries. Flag any `parallel_conflicts` before dispatching next sequential step.

**Failed approach format** (within step entry):
```json
{
  "approach": "description of what was tried",
  "why_failed": "specific reason — not 'it didn't work'",
  "lesson": "actionable rule for future agents in this codebase"
}
```

**Parallel merge conflict detection:**
- After parallel agents complete, compare `patterns_used` across all parallel steps.
- If two agents established conflicting patterns: flag as `parallel_conflict`, surface to user before continuing.
- Example: "Agent A used dict responses, Agent B used Pydantic models — resolve before Step 7."

**Full context chain per implementation agent** (8 items, inject all):
1. Plan step — specific task for this step
2. Architecture decision — chosen approach and trade-offs
3. Exploration scratchpad — what explorers found in this area
4. Build-state — interfaces created, patterns established, decisions made so far
5. Failed-approach log — extracted from build-state, what was tried and didn't work
6. Gap-fill findings — if Phase 4 gap-fill covered this area
7. Registry priors — historical failure rate and recommended thinking budget for this domain
8. Missed-context flags — if prior steps had `available_in_*` misses in this area, highlight them

---

## 5. Agent Signals

All implementation agents return a structured signal (not just pass/fail).

**Signal schemas:**

| Signal | Required fields |
|--------|----------------|
| `completed` | `signal`, `step` |
| `completed_with_deviation` | `signal`, `step`, `what_changed`, `downstream_steps_affected[]` |
| `completed_with_discovery` | `signal`, `step`, `what_found`, `plan_adaptation_recommendation` |
| `blocked` | `signal`, `step`, `blocker_description`, `upstream_change_suggestion` |

**Orchestrator processing rules:**
1. `completed` → dispatch next step normally.
2. `completed_with_deviation` → run architecture deviation check immediately (don't wait for every-3-steps cadence).
3. `completed_with_discovery` → update build-state with discovery, re-evaluate plan steps `downstream_steps_affected`.
4. `blocked` → PAUSE. Surface to user with `upstream_change_suggestion`. Do not retry.

**Architecture deviation detection** (run after every 3 steps, or immediately on any deviation signal):
1. Compare `build-state.steps[].patterns_used` against architecture decision.
2. Compare `build-state.steps[].interfaces_exposed` against planned interfaces.
3. Identify violated architecture assumptions.

| Condition | Action |
|-----------|--------|
| >50% of completed steps deviated from architecture | PAUSE — surface deviation summary to user |
| Single critical architecture assumption violated | PAUSE immediately |
| Minor deviations, <50% of steps | Log in build-state, continue |

**Collaborative rescue decision tree** (before entering retry loop):
1. Package: error output + build-state + failed-approach log.
2. Query registry: "Which agent types have highest success rate for [error_class] in [domain]?"
3. Does a different agent type have >20% higher success rate AND >5 dispatches?
   - Yes → dispatch that agent type with full failure context. Record `rescue_succeeded` or `rescue_failed`.
   - No → fall back to existing retry loop with diagnosis subagent.

---

## 6. Staged Review

Complex tier only. Three waves; each wave builds on previous findings.

**Wave 1** (parallel — highest-value reviewers from registry):
- Code Reviewer A, Security Reviewer, Silent Failure Hunter
- Each writes to `review-findings.json`: `areas_reviewed`, `findings[]`, `patterns_noticed`

**Wave 2** (parallel — receives Wave 1 findings):

Code Reviewer B prompt template:
```
Wave 1 reviewers found these patterns: [patterns_noticed from Wave 1]
They reviewed: [areas_reviewed from Wave 1]
They did NOT review: [files in build-state not covered by Wave 1]

Check whether the patterns they found extend to uncovered areas.
Focus on: [uncovered files]. Do not re-examine already-reviewed areas.
```

QA Edge-Case Reviewer prompt template:
```
Wave 1 found these bugs: [findings from Wave 1]
Check: are there tests covering the corrected behavior for each?
Also check: edge cases adjacent to the bugs found.
```

Production Readiness prompt template:
```
Security reviewer found: [security findings from Wave 1]
Verify: are the proposed fixes production-safe? Check for:
- Fix introduces new vulnerability
- Fix breaks existing auth flow
- Fix works in dev but not prod (env-specific issue)
```

**Wave 3 — Meta-reviewer** (single agent, receives ALL findings + build-state):

Five tasks (execute all five, do not skip):
1. **Pattern escalation:** Find findings across different files/reviewers that share a root cause. Mark as SYSTEMIC.
2. **Deduplication:** Merge findings that describe the same issue. Keep highest-severity version.
3. **Priority synthesis:** Re-rank all findings by actual production impact, not reviewer-assigned severity.
4. **Gap detection:** List areas in build-state with high complexity that no reviewer examined.
5. **Contradiction resolution:** If Reviewer A says "fine" and Reviewer B says "dangerous" on same code → investigate, pick one side, show reasoning.

---

## 7. Missed-Context Audit

Run after: each explorer completes (Phase 2), each architect round (Phase 4), each implementation step (Phase 5), each review wave (Phase 6).

**4 audit steps:**
1. Extract claims the agent made about missing information (files it couldn't find, patterns it said don't exist, questions it raised).
2. Cross-reference each claim against: agent's own prompt, CLAUDE.md, MEMORY.md, docs/, README.
3. Classify each miss (see `swarm-schemas.md#missed-context-log` for type definitions).
4. Log to `missed-context-log/SESSION_ID.json`.

**Sources to check by miss type:**

| Miss type | Check these sources |
|-----------|-------------------|
| `available_in_prompt` | Agent's own prompt verbatim — was the answer there? |
| `available_in_project` | CLAUDE.md, README, docs/, config files |
| `available_in_memory` | MEMORY.md, memory/semantic/failure-catalog.md |
| `not_available` | All sources checked, nothing found — record as gap |

**Severity criteria:**

| Severity | Condition |
|----------|-----------|
| `high` | Miss caused incorrect output (wrong proposal, introduced bug, violated constraint) |
| `medium` | Miss caused rework (correct output but wasted effort to get there) |
| `low` | Miss caused minor redundancy (explored something already covered) |

**Feedback paths per miss type:**

| Miss type | Feedback action |
|-----------|----------------|
| `available_in_prompt` | Flag for prompt quality review — candidate for `common-mistakes.md` |
| `available_in_project` | Flag for Phase 0 scope expansion — candidate for CLAUDE.md or smart-exploration scope |
| `available_in_memory` | Flag for memory-injection domain mapping — check if gotcha key needs new domain |
| `not_available` | If recurring across sessions: candidate for MEMORY.md new entry |

---

## 8. Periodic Review

**Trigger conditions** (run any time one is met):
- 10+ sessions completed since last review
- `available_in_prompt` miss rate >20% over last 10 sessions
- Any single agent with effectiveness <0.1 AND >15 dispatches
- Complexity calibration history has 20+ new entries since last weight adjustment
- User explicitly requests review

**5 analysis dimensions:**

| Dimension | What to measure |
|-----------|----------------|
| Agent effectiveness | Rank all agents by score; identify candidates for retirement (effectiveness <0.1, confidence >15) and investment (effectiveness >0.7) |
| Missed-context trends | Miss rate by type and phase over time; recurring misses in same area = MEMORY.md candidate |
| Complexity calibration | Static score vs actual tier sufficiency; adjust `complexity_calibration.weights` where signal is clear |
| Cross-phase feedback health | Exploration → implementation flow quality; review → exploration feedback acting; failed-approach reuse rate |
| Swarm effectiveness | Staggered exploration gap-fill rate; adversarial debate impact on synthesis quality; meta-reviewer systemic escalation rate |

**Output → action table:**

| Output | Mechanism | Approval required |
|--------|-----------|------------------|
| Registry weight adjustment | Update `complexity_calibration.weights` directly | Automatic |
| Agent skipped (effectiveness <0.1, confidence >15) | Update dispatch table | Automatic |
| Prompt improvement identified | `session-learnings` proposes skill revision | Human |
| CLAUDE.md update needed | `claude-md-management:revise-claude-md` | Human |
| MEMORY.md new gotcha | Standard memory write | Automatic |
| Explorer scope expansion | smart-exploration prompt library update | Human |
| Workflow skill revision | `session-learnings` proposes SKILL.md diff | Human |

**Retention policy:**

| Store | Full detail | Summary only | Delete |
|-------|------------|-------------|--------|
| Exploration logs | Last 30 sessions | Sessions 31-90 (counts only) | After 90 sessions |
| Missed-context logs | Last 30 sessions | Aggregated into registry | After 30 sessions |
| `available_in_prompt` misses | Permanent | — | Never |
| Systemic pattern escalations | Permanent | — | Never |
| Registry | Permanent | — | Decay handles staleness |
| Calibration history | Last 50 entries | — | Oldest pruned at 50 |

**Decay schedule:** Every 30 days, apply to all agent priors: `alpha = max(1, alpha * 0.85)`, `beta = max(1, beta * 0.85)`. Prevents stale priors from dominating.
