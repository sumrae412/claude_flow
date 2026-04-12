# Workflow State Machine & Schema Validation Design

> **Date:** 2026-04-11
> **Status:** Approved
> **Inspiration:** claude-workflow's `WorkflowStateManager`, `SchemaValidator`, and `phase-tracker` patterns (adapted, not imported)

## Problem

Claude-flow's code-creation-workflow has two gaps:

1. **No phase transition governance.** The SKILL.md describes phases (0 → 1 → 2 → ... → 6) but nothing enforces the order. An executor can skip exploration or jump to implementation without completing architecture. Phase outputs aren't validated.

2. **No cross-session resume.** If a session dies mid-Phase 5, the next session starts from scratch. The `session-handoff` skill captures state manually, but it's best-effort and loses structured context.

## Solution: Approach 1 — JSON State File + Hook Enforcement

No runtime dependencies. State lives in a JSON file. A hook enforces phase gates. Schemas validate phase outputs. Cross-session resume reads the state file.

---

## Component 1: State File

**Path:** `.claude/workflow-state.json` — gitignored (ephemeral to workflow session, not project knowledge).

```json
{
  "schema_version": 1,
  "workflow_id": "code-creation-workflow",
  "session_id": "2026-04-11T10:30:00Z",
  "status": "running",
  "started_at": "2026-04-11T10:30:00Z",
  "current_phase": {
    "id": "phase-2",
    "name": "Exploration",
    "path": "full",
    "status": "running",
    "started_at": "2026-04-11T10:32:00Z",
    "step": 3,
    "step_label": "Pattern mapping",
    "agents_spawned": 0,
    "agents_completed": 0,
    "agents_failed": 0,
    "iteration": 1,
    "max_iterations": 3
  },
  "phase_history": [
    {
      "id": "phase-0",
      "name": "Context Loading",
      "status": "completed",
      "started_at": "2026-04-11T10:30:00Z",
      "completed_at": "2026-04-11T10:31:00Z",
      "iteration": 1,
      "results": { "skills_loaded": 4, "hooks_generated": false }
    }
  ],
  "iterations": {
    "phase-0": 1,
    "phase-1": 1,
    "phase-2": 1
  },
  "task_summary": "Add bulk import endpoint for tenants",
  "artifacts": {
    "exploration_summary": null,
    "architecture_doc": null,
    "implementation_plan": null,
    "review_findings": null
  }
}
```

**Key fields:**
- `current_phase.path` — workflow path (fast/clone/lite/full/plan) selected in Phase 1
- `current_phase.step` + `step_label` — sub-phase granularity for resume
- `artifacts` — tracks which phase outputs exist, enables schema validation
- `task_summary` — human-readable for resume messages

---

## Component 2: Phase Transition Rules

### Transition Map

```
Phase 0  (Context Loading)     → Phase 0.5 or Phase 1
Phase 0.5 (Bootstrap Hooks)    → Phase 1
Phase 1  (Discovery)           → Fast Path EXIT
                               → Phase 2 (full/lite)
                               → Phase 5 (clone/plan path)
Phase 2  (Exploration)         → Phase 3
Phase 3  (Clarification)       → Phase 4
Phase 4  (Architecture)        → Phase 4b
Phase 4b (Plan Stress-Test)    → Phase 4d or Phase 5
Phase 4d (Test Skeletons)      → Phase 5
Phase 5  (Implementation)      → Phase 5 (retry, max 3)
                               → Phase 6
Phase 6  (Review)              → Phase 5 (fix loop, max 2)
                               → COMPLETE
```

### Transition Conditions

| From → To | Condition |
|-----------|-----------|
| Phase 5 → Phase 5 (retry) | `any_failed` — tests or lint failed, iteration < max |
| Phase 5 → Phase 6 | `all_passed` — tests + lint green |
| Phase 6 → Phase 5 (fix) | Review findings with severity `high` or `critical` |
| Phase 6 → COMPLETE | No high/critical findings remaining |

### Iteration Limits

| Phase | Max | On Limit Exceeded |
|-------|-----|-------------------|
| Phase 5 | 3 | Surface to user: "3 failed attempts, need guidance" |
| Phase 6 | 2 | Ship with known issues documented |
| All others | 1 | Forward only |

### Path-Specific Skip Rules

| Path | Phases Skipped |
|------|---------------|
| `fast` | 2, 3, 4, 4b, 4d, 6 |
| `clone` | 2, 3, 4, 4b, 4d |
| `lite` | 4d |
| `plan` | 2, 3, 4, 4b |

---

## Component 3: Hook Enforcement — `phase-gate`

Single Tier 1 hook. Read-only — gates actions, never mutates state.

**Registration:**
- Trigger: `PreToolUse`
- Matcher: `["Edit", "Write", "Bash"]`
- Script: `hooks/tier1/phase-gate.sh`

### Gate Rules

| Current Phase | Edit/Write Source Files | Edit/Write Docs/Plans | Edit/Write .claude/* |
|---------------|----------------------|---------------------|-------------------|
| 0, 0.5, 1, 2, 3 | BLOCK | ALLOW | ALLOW |
| 4, 4b, 4d | BLOCK | ALLOW | ALLOW |
| 5 | ALLOW | ALLOW | ALLOW |
| 6 | BLOCK (unless status=fixing) | ALLOW | ALLOW |
| No state file | ALLOW all | ALLOW all | ALLOW all |

"Source files" = files matching `app/*`, `src/*`, `lib/*`, `tests/*` (configurable).

### Block Message Format

```
⚠ Phase gate: You're in Phase 2 (Exploration). Source file edits
are blocked until Phase 5 (Implementation).

Current state: Phase 2, Step 3 (Pattern mapping)
To advance: Complete exploration, then transition to Phase 3.
```

---

## Component 4: Cross-Session Resume

Phase 0, Step 1 checks for `.claude/workflow-state.json` before anything else.

### Resume Rules

| State Found | Action |
|-------------|--------|
| Phase 0-1 in progress | Restart Phase 0 (fast, idempotent) |
| Phase 2-4 in progress | Re-read produced artifacts, resume at current step |
| Phase 5 in progress | Read `build-state.json` for completed steps, resume |
| Phase 5 with `any_failed` | Resume failed step, increment iteration |
| Phase 6 in progress | Re-read review findings, resume |
| Status `completed` | Clear state file, start fresh |
| Status `failed` | Show context, ask user |

### Stale Session Detection

If `started_at` > 48 hours ago:

```
⚠ Found workflow state from 3 days ago. Codebase may have changed.

Options:
1. Resume anyway (re-verify artifacts)
2. Start fresh (archive to .claude/workflow-state.archived.json)
```

### Session-Handoff Integration

`session-handoff` skill reads `workflow-state.json` as canonical source instead of manual state capture. `handoff.md` becomes a human-readable view.

---

## Component 5: Schema Validation

JSON schemas in `.claude/schemas/` validated by a PostToolUse hook. Fail-open: missing schema = warning.

### Schemas

| File | Validates | Required Fields |
|------|-----------|----------------|
| `exploration-output.json` | `artifacts.exploration_summary` | `key_files` (1+), `patterns`, `integration_points` |
| `architecture-output.json` | `artifacts.architecture_doc` | `approach`, `files_to_create`, `files_to_modify`, `trade_offs` |
| `plan-output.json` | `artifacts.implementation_plan` | `steps` (1+), each with `description`, `files`, `dependencies` |
| `review-output.json` | `artifacts.review_findings` | `findings` array, each with `severity`, `finding`, `file` |

### Validation Hook

- Script: `hooks/tier1/validate-phase-output.sh`
- Trigger: `PostToolUse` on `Write` to `.claude/workflow-state.json`
- Mechanism: `jq` checks required fields and types
- On failure: warn + block phase transition (artifact incomplete)
- On missing schema/jq: warn, allow (fail-open)

---

## Files to Create/Modify

| File | Action | Purpose |
|------|--------|---------|
| `.claude/schemas/exploration-output.json` | Create | Phase 2 output schema |
| `.claude/schemas/architecture-output.json` | Create | Phase 4 output schema |
| `.claude/schemas/plan-output.json` | Create | Phase 4b output schema |
| `.claude/schemas/review-output.json` | Create | Phase 6 output schema |
| `hooks/tier1/phase-gate.sh` | Create | Phase enforcement hook |
| `hooks/tier1/validate-phase-output.sh` | Create | Schema validation hook |
| `hooks/hook-registry.json` | Modify | Register 2 new hooks |
| `skills/code-creation-workflow/SKILL.md` | Modify | Add state file read/write at phase boundaries |
| `skills/session-handoff/SKILL.md` | Modify | Read state file as canonical source |

---

## What We Took From claude-workflow

| Their Pattern | Our Adaptation |
|--------------|----------------|
| `MultiPhaseWorkflowState` type | `.claude/workflow-state.json` schema |
| `transitionToPhase()` with validation | Skill instructions + hook gate |
| `PhaseHistory` with timestamps | Same — enables cross-session resume |
| `max_iterations` per phase | Same — prevents infinite retry loops |
| `SchemaValidator` with fail-open | jq validation in hooks, same fail-open principle |
| `ConditionType` enum | Mapped to Phase 5 retry / Phase 6 review outcomes |
| `calculateNextPhase()` conditions | Transition rules in skill, enforced by hook |

**What we didn't take:** YAML workflow definitions (we have one workflow), dynamic agent spawn counts, agent type resolution by assignee, Ajv/Node.js runtime dependency, singleton class pattern.
