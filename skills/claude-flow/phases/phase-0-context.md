# Phase 0: Context Loading + Phase 0.5: Hooks Bootstrap

<!-- Loaded: on workflow start | Dropped: after transition to Phase 1 -->

---

## Workflow State Machine

<SKIP-CONDITION>
Skip state machine initialization for **fast** and **lite** paths. These are single-session, linear flows that don't benefit from cross-session resume. Only initialize for **full**, **clone**, and **plan** paths (determined in Phase 1 — defer initialization until after path selection).
</SKIP-CONDITION>

The workflow tracks its state in `.claude/workflow-state.json` for phase governance and cross-session resume.

### State File: Initialize

Replace `SESSION_TIMESTAMP` with actual ISO timestamp, `TASK_SUMMARY` with the user's request.

```json
{
  "schema_version": 1,
  "workflow_id": "claude-flow",
  "session_id": "SESSION_TIMESTAMP",
  "status": "running",
  "started_at": "SESSION_TIMESTAMP",
  "current_phase": {
    "id": "phase-0",
    "name": "Context Loading",
    "path": null,
    "status": "running",
    "started_at": "SESSION_TIMESTAMP",
    "step": 1,
    "step_label": "Load project identity",
    "agents_spawned": 0,
    "agents_completed": 0,
    "agents_failed": 0,
    "iteration": 1,
    "max_iterations": 1
  },
  "phase_history": [],
  "iterations": { "phase-0": 1 },
  "task_summary": "TASK_SUMMARY",
  "artifacts": {
    "exploration_summary": null,
    "architecture_doc": null,
    "implementation_plan": null,
    "review_findings": null
  }
}
```

### State File: Transition

At each phase boundary — move current phase to history and set new phase:

```bash
jq '
  .phase_history += [{
    id: .current_phase.id,
    name: .current_phase.name,
    status: "completed",
    started_at: .current_phase.started_at,
    completed_at: (now | todate),
    iteration: .current_phase.iteration,
    results: {}
  }] |
  .current_phase = {
    id: "NEXT_PHASE_ID",
    name: "NEXT_PHASE_NAME",
    path: .current_phase.path,
    status: "running",
    started_at: (now | todate),
    step: 1,
    step_label: "FIRST_STEP_LABEL",
    agents_spawned: 0,
    agents_completed: 0,
    agents_failed: 0,
    iteration: 1,
    max_iterations: MAX_ITERATIONS
  } |
  .iterations["NEXT_PHASE_ID"] = ((.iterations["NEXT_PHASE_ID"] // 0) + 1)
' .claude/workflow-state.json > .claude/workflow-state.tmp && mv .claude/workflow-state.tmp .claude/workflow-state.json
```

Step update: `jq '.current_phase.step = N | .current_phase.step_label = "LABEL"'`. Workflow done: `jq '.status = "completed"'`.

### Cross-Session Resume

At the very start of Phase 0 (before Step 1), check for existing state:

1. `status == "running"`: check age — if >48h, ask "Resume or start fresh?". Resume: skip to in-progress phase. Fresh: archive to `.claude/workflow-state.archived.json`.
2. `status == "completed"`: archive and start fresh.
3. File not found: proceed normally, initialize state after Phase 0 context loading.

Resume message: `Resuming workflow: "<task_summary>" / <phase.name> Step <step> (<step_label>) / Path: <path> / Completed: [...] / Artifacts: [null vs populated]`

### Transition Map

| From | To | Condition |
|------|----|-----------|
| phase-0 → phase-0.5 | No hooks.json exists |
| phase-0 → phase-1 | hooks.json exists |
| phase-0.5 → phase-1 | Always |
| phase-1 → EXIT | Fast path |
| phase-1 → phase-2 | Full or lite path |
| phase-1 → phase-5 | Clone or plan path |
| phase-2 → phase-3 | Always |
| phase-3 → phase-4 | Always |
| phase-4 (includes plan stress-test) → phase-4d | Full path only |
| phase-4 (includes plan stress-test) → phase-5 | Lite path |
| phase-4d → phase-5 | Always |
| phase-5 → phase-5 | Retry: tests/lint failed, iteration < 3 |
| phase-5 → phase-6 | Tests + lint pass |
| phase-6 → phase-5 | High/critical findings, iteration < 2 |
| phase-6 → COMPLETE | No high/critical findings |

### Iteration Limits

| Phase | Max | On Exceeded |
|-------|-----|-------------|
| phase-5 | 3 | Surface to user |
| phase-6 | 2 | Ship with known issues |
| All others | 1 | Forward only |

---

## Phase 0: Context Loading

<HARD-GATE>
Load project context before any exploration or coding.
</HARD-GATE>

### Step 0: Check for Existing Workflow State

Read `.claude/workflow-state.json`. If `running` → resume or archive (see Cross-Session Resume). If `completed` → archive. If missing → proceed (initialize after Step 6).

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

- **coding-best-practices** — always loaded
- UI work → `defensive-ui-flows` | Backend → `defensive-backend-flows` | Both → load both

### Step 5: Conditional Tools

| Condition | Action |
|-----------|--------|
| Feature uses external API | **REQUIRED:** Invoke `/fetch-api-docs` skill to get current API docs from Context Hub before any implementation. Do NOT code against external APIs from memory — formats change. |
| Codebase >500 files or unfamiliar | Run `python scripts/generate_repo_outline.py app/` for signatures + `repomix --compress` for full compressed context |
| Need symbol-level precision | Activate Serena project, read relevant memories |
| MCP-heavy exploration (DB queries, Figma imports) | Set `MAX_MCP_OUTPUT_TOKENS=50000` to prevent truncated MCP responses that degrade exploration quality |
| Small familiar codebase | Skip all |

**Token-saving tools:** `generate_repo_outline.py` (signatures without bodies), `semgrep` (static analysis), `ast-grep` (AST search), `pyright` (type checking).

### Step 6: Git Check

Verify you're on a feature branch. If on main, create one before proceeding.

### Step 7: Bootstrap MEMORY.md (One-Time)

<SKIP-CONDITION>
Skip if a project-scoped `MEMORY.md` already exists. Check these locations in order:
1. `$PROJECT/.claude/memory/MEMORY.md` (Claude Code auto-memory)
2. `$PROJECT/MEMORY.md` (project root)
</SKIP-CONDITION>

If no MEMORY.md exists, create one to enable cross-session context persistence:

1. **Determine the memory directory.** Use `$PROJECT/.claude/memory/` if `.claude/` exists; otherwise use `$PROJECT/`.
2. **Create MEMORY.md** with this starter template:

```markdown
# Project Memory

<!-- Index of memory files. Each entry: - [Title](file.md) — one-line description -->
<!-- Keep entries under 150 chars. Content goes in individual files, not here. -->
```

3. **Announce:** "Created MEMORY.md for cross-session context — I'll populate it as I learn about the project."

**Why this matters:** The memory-injection system maps domain-specific gotchas from MEMORY.md into subagent prompts. Without it, gotchas discovered during sessions are lost.

**State transition:** Move current phase to `phase_history`, set `current_phase` to phase-0.5 or phase-1 based on hooks.json existence. Set `path` to null.

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

- **Tier 1 (always):** session context, pre-compaction transcript backup, post-commit memory, worktree guard, credential leak scanner
- **Tier 2 (conditional):** where stack tags match (e.g., `has-env` → .env blocker, `ruff` → linter-on-save)
- Write to `$PROJECT/.claude/hooks.json`

**Credential Leak Scanner (Tier 1 — always include):**
Before any subagent dispatch or subprocess spawn, scan for unallowlisted environment variables that could leak credentials into AI context:
```
SUBPROCESS_ENV_ALLOWLIST:
  - PATH, HOME, USER, SHELL, TERM, LANG, LC_*
  - BUILD_ENV, NODE_ENV, PYTHON_VERSION
  - CI, GITHUB_ACTIONS (CI detection only)

Block from AI context:
  - *_TOKEN, *_SECRET, *_KEY, *_PASSWORD, *_CREDENTIAL
  - AWS_*, STRIPE_*, OPENAI_*, ANTHROPIC_*
  - DATABASE_URL, REDIS_URL (connection strings with credentials)
```
Implementation: Pre-tool hook that scrubs process environment before spawning Claude subprocesses. Log `[REDACTED]` for any blocked var.

### Step 3: Generate Hook Scripts + Config

1. Copy parameterized scripts from `~/claude-config/scripts/hooks/` into `$PROJECT/scripts/hooks/`
2. Generate `scripts/hooks/hook-config.sh` with detected file categories, skill suggestions, linter command + glob
3. `chmod +x` all scripts

### Step 4: Confirm

Output summary table of generated hooks (trigger → what it does). Ask user to review `hooks.json` before continuing to Phase 1.
