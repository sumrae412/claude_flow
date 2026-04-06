# Swarm Schemas

> Single source of truth for all swarm data shapes. SKILL.md and registry.py reference this file.
> Design rationale: `docs/plans/2026-04-06-swarm-intelligence-workflow-design.md`

---

## Global Registry

**Path:** `~/.claude/swarm/agent-registry.json` — permanent, shared across all projects.

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

**Agent key format:** `"phase:variant"` — e.g. `"explorer:route-chain"`, `"reviewer:security"`, `"architect:simplicity"`.

| Field | Description |
|-------|-------------|
| `prior.alpha` | Beta distribution successes (initial: 1) |
| `prior.beta` | Beta distribution failures (initial: 1) |
| `dispatches` | Total times dispatched |
| `findings_produced` | Total findings/files returned |
| `findings_used` | Subset actually used by orchestrator |
| `findings_used_rate` | `findings_used / findings_produced` — key explorer metric |
| `missed_context_count` | Times agent missed available context |
| `complexity_calibration.weights` | Multipliers for each static scoring axis |
| `complexity_calibration.history` | Last 50 calibration history entries (see below) |
| `project_fingerprints` | Map of project ID → fingerprint (for similarity matching) |

---

## Project Overlay

**Path:** `.claude/swarm/agent-registry.json` — committed, scoped to project.

Same `agents` and `complexity_calibration` structure as global, plus:

```json
{
  "schema_version": 2,
  "project_fingerprint": {
    "languages": ["python"],
    "frameworks": ["fastapi", "sqlalchemy"],
    "has_migrations": true,
    "has_external_apis": true,
    "layer_count": 4
  },
  "agents": { },
  "complexity_calibration": {
    "weights": { "reasoning_depth": 1.0, "ambiguity": 1.0, "context_dependency": 1.0, "novelty": 1.0 },
    "history": []
  }
}
```

| Field | Description |
|-------|-------------|
| `project_fingerprint.languages` | Primary languages (lowercase) |
| `project_fingerprint.frameworks` | Detected frameworks |
| `project_fingerprint.has_migrations` | Boolean capability flags (used in similarity) |
| `project_fingerprint.has_external_apis` | Boolean capability flag |
| `project_fingerprint.layer_count` | Approximate architectural layers |

**Prior blending:** `< 5` project dispatches → `0.7 * project + 0.3 * global`. At `15+` dispatches → project only.

---

## Exploration Log

**Path:** `.claude/swarm/exploration-log/SESSION_ID.json` — committed, persists for cross-session learning.

```json
{
  "schema_version": 2,
  "session_id": "2026-04-06T14:23:00Z",
  "task_summary": "...",
  "tier": "complex",
  "degradation_probe": {
    "ran": true,
    "succeeded": false,
    "tier_adjustment": "none"
  },
  "explorers": [
    {
      "id": "explorer-a",
      "variant": "explorer:broad",
      "files_found": ["app/services/billing.py"],
      "files_hydrated": ["app/services/billing.py"],
      "gaps_identified": ["no test for refund path"],
      "gaps_filled_by": "explorer-b",
      "duration_ms": 4200
    }
  ],
  "architecture": {
    "proposals": ["..."],
    "gap_fill_ran": true,
    "critiques": ["..."],
    "synthesis": "..."
  },
  "implementation_steps": [
    {
      "step": 3,
      "domain": "services",
      "thinking_budget": "think harder",
      "passed_first_attempt": true,
      "retry_count": 0,
      "signal": "completed",
      "failed_approaches": [],
      "deviations": [],
      "discoveries": []
    }
  ],
  "review": {
    "wave1_findings": [],
    "wave2_findings": [],
    "meta_reviewer_escalations": []
  }
}
```

| Explorer field | Description |
|----------------|-------------|
| `variant` | Registry agent key used |
| `files_found` | All files explorer returned |
| `files_hydrated` | Subset orchestrator loaded into context |
| `gaps_identified` | Gaps explorer flagged |
| `gaps_filled_by` | Which later explorer addressed them (or `null`) |

---

## Missed-Context Log

**Path:** `.claude/swarm/missed-context-log/SESSION_ID.json` — committed (last 30 sessions), then aggregated into registry.

```json
{
  "schema_version": 2,
  "session_id": "2026-04-06T14:23:00Z",
  "misses": [
    {
      "phase": 2,
      "agent": "explorer:broad",
      "miss_type": "available_in_memory",
      "what_was_missed": "MEMORY.md lists nullable refunded_at — agent didn't check",
      "where_it_existed": "MEMORY.md#billing-gotchas",
      "impact": "agent proposed non-null constraint that would break existing rows",
      "severity": "high"
    }
  ],
  "summary": {
    "total_misses": 1,
    "by_type": { "available_in_prompt": 0, "available_in_project": 0, "available_in_memory": 1, "not_available": 0 },
    "by_phase": { "2": 1, "4": 0, "5": 0, "6": 0 },
    "by_severity": { "high": 1, "medium": 0, "low": 0 }
  }
}
```

**Miss types:**

| Type | Meaning |
|------|---------|
| `available_in_prompt` | Info was in the agent's own prompt — agent missed it (prompt quality issue) |
| `available_in_project` | Info exists in project files, wasn't loaded (Phase 0 / exploration gap) |
| `available_in_memory` | Info exists in MEMORY.md, wasn't injected (memory-injection gap) |
| `not_available` | Genuinely missing from all sources — not a miss |

**Severity:** `high` = caused a bug or incorrect proposal; `medium` = caused rework; `low` = redundant work.

---

## Exploration Scratchpad (ephemeral)

**Path:** `.claude/swarm/exploration-scratchpad.json` — gitignored, deleted at session end.

```json
{
  "schema_version": 2,
  "session_id": "...",
  "explorers_completed": ["explorer-a"],
  "key_files": ["app/services/billing.py", "app/models/invoice.py"],
  "patterns_found": ["service-layer with repository pattern"],
  "gaps_identified": ["no test coverage for refund path", "invoice state machine unclear"],
  "gap_fill_findings": [],
  "explorer_disagreements": []
}
```

Written by each explorer on completion. Read by: subsequent explorers, architect prompts, implementation agents.

---

## Build-State (ephemeral)

**Path:** `.claude/swarm/build-state.json` — gitignored, archived to exploration-log on session end.

```json
{
  "schema_version": 2,
  "session_id": "...",
  "steps": [
    {
      "step": 3,
      "files_created": ["app/services/billing.py"],
      "files_modified": ["app/models/invoice.py"],
      "interfaces_exposed": ["BillingService.process_refund(invoice_id, amount)"],
      "patterns_used": ["service-layer with repository pattern, matching client_service.py"],
      "decisions_made": ["Used Decimal for amounts — precision matters"],
      "gotchas_encountered": ["Nullable refunded_at column in existing rows"],
      "failed_approaches": [
        {
          "approach": "Raw SQL batch update",
          "why_failed": "Bypassed ORM event hooks",
          "lesson": "Always use ORM — other systems subscribe to model events"
        }
      ],
      "test_files": ["tests/test_billing_service.py"],
      "signal": "completed"
    }
  ],
  "parallel_conflicts": []
}
```

| Field | Description |
|-------|-------------|
| `interfaces_exposed` | Public interfaces created — downstream agents read this to avoid duplication |
| `patterns_used` | Patterns established — later agents must match these |
| `failed_approaches` | Pheromone trails: paths that don't work so later agents avoid them |
| `parallel_conflicts` | Pattern decisions that conflicted across parallel agents — must resolve before next step |

---

## Review Findings (ephemeral)

**Path:** `.claude/swarm/review-findings.json` — gitignored, archived on session end.

```json
{
  "schema_version": 2,
  "session_id": "...",
  "wave1": [
    {
      "reviewer": "reviewer:security",
      "areas_reviewed": ["app/routes/billing.py"],
      "findings": [
        { "severity": "high", "finding": "...", "file": "...", "line": 42 }
      ],
      "patterns_noticed": ["auth decorator missing on 2 of 3 billing routes"]
    }
  ],
  "wave2": [],
  "meta_reviewer": {
    "escalations": [],
    "deduplicated_findings": [],
    "priority_ranked": [],
    "gaps_detected": [],
    "contradictions_resolved": []
  }
}
```

---

## Registry Events (JSONL)

**Path:** `~/.claude/swarm/registry-events.jsonl` — gitignored, compacted on session start.

One JSON object per line. POSIX atomic append (no locking needed).

```jsonl
{"ts":"2026-04-06T14:23:01Z","event":"dispatched","agent":"explorer:broad","session":"..."}
{"ts":"2026-04-06T14:23:05Z","event":"finding_used","agent":"explorer:broad","session":"...","count":3}
{"ts":"2026-04-06T14:23:30Z","event":"finding_ignored","agent":"explorer:deep","session":"...","count":1}
{"ts":"2026-04-06T14:25:00Z","event":"step_passed","agent":"implementer:services","session":"..."}
{"ts":"2026-04-06T14:25:01Z","event":"step_failed","agent":"implementer:services","session":"...","error_class":"type_error"}
{"ts":"2026-04-06T14:26:00Z","event":"rescue_succeeded","agent":"implementer:specialist","session":"..."}
{"ts":"2026-04-06T14:30:00Z","event":"review_finding_accepted","agent":"reviewer:security","session":"..."}
{"ts":"2026-04-06T14:30:01Z","event":"review_finding_dismissed","agent":"reviewer:security","session":"..."}
{"ts":"2026-04-06T14:31:00Z","event":"meta_escalation_led_to_fix","agent":"reviewer:meta","session":"..."}
{"ts":"2026-04-06T14:31:01Z","event":"meta_escalation_was_noise","agent":"reviewer:meta","session":"..."}
```

**Event type → Bayesian signal mapping:**

| Event | Phase | Bayesian signal |
|-------|-------|----------------|
| `finding_used` | 2 | success (alpha++) |
| `finding_ignored` | 2 | failure (beta++) |
| `architecture_adopted` | 4 | success |
| `architecture_rejected` | 4 | failure |
| `critique_changed_outcome` | 4 | success |
| `critique_ignored` | 4 | failure |
| `step_passed` | 5 | success |
| `step_failed` | 5 | failure |
| `rescue_succeeded` | 5 | success |
| `rescue_failed` | 5 | failure |
| `review_finding_accepted` | 6 | success |
| `review_finding_dismissed` | 6 | failure |
| `meta_escalation_led_to_fix` | 6 | success |
| `meta_escalation_was_noise` | 6 | failure |

**Compaction:** On each session start, read registry + all events → apply Bayesian updates → write new registry → truncate events file.

---

## Complexity Calibration History Entry

One entry per session, stored in `complexity_calibration.history` (max 50, oldest pruned):

```json
{
  "session_id": "...",
  "static_score": 8,
  "probe_result": "confirmed_complex",
  "tier_used": "complex",
  "tier_sufficient": true,
  "phase5_three_strike": false,
  "phase6_critical_issues": false,
  "date": "2026-04-06"
}
```

| `probe_result` value | Meaning |
|---------------------|---------|
| `confirmed_complex` | Probe failed → static score was correct |
| `downgraded` | Probe succeeded → static score over-estimated, tier lowered |
| `skipped` | Moderate tier — no probe run |

---

## Gitignore Guidance

Add to `.gitignore` in any project using swarm:

```gitignore
# Swarm ephemeral state (session-scoped, not project knowledge)
.claude/swarm/build-state.json
.claude/swarm/exploration-scratchpad.json
.claude/swarm/review-findings.json
.claude/swarm/registry-events.jsonl
```

**Committed** (project knowledge worth sharing with collaborators):

- `.claude/swarm/agent-registry.json` — project overlay with learned priors
- `.claude/swarm/exploration-log/` — session records for periodic review
- `.claude/swarm/missed-context-log/` — miss audit history

---

## Schema Versioning Protocol

1. All swarm files include `"schema_version": N` at the top level.
2. On load: check version. If behind current → apply sequential migrations.
3. Migrations defined in `references/registry-migrations.md`.
4. Never delete fields during migration — move deprecated fields to `_deprecated` object.
5. Current version: **2** for all schemas above.
