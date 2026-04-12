# Agent & Skill Registry

Reference documentation for all agents, skills, and tools used within the code-creation-workflow. This file is for documentation — not loaded at runtime.

## Agents Used Within This Workflow

### Advisor (Opus, On-Demand)

| Checkpoint | Phase | Question Focus | Required? |
|------------|-------|----------------|-----------|
| Exploration Review | 2 | "What am I missing?" | Yes |
| Architecture Critique | 4 | "What are the blind spots?" | Yes |
| Plan Stress-Test | 4b | "Find logic errors, scope creep" | Yes |
| Mid-Implementation | 5 | "Which pattern at this decision point?" | Optional |
| Strategic Pre-Review | 6 | "Does this fulfill requirements?" | Optional |

All advisor calls use `model: "opus"`, `subagent_type: "general-purpose"`.

### Review Agents (Phase 5-6)

| Agent | `subagent_type` | Phase | Trigger | Model |
|-------|-----------------|-------|---------|-------|
| Migration Reviewer | `migration-reviewer` | 5, 6 | Alembic files | sonnet |
| Google API Reviewer | `google-api-reviewer` | 5, 6 | Google API code | sonnet |
| Async Reviewer | `async-reviewer` | 5, 6 | async I/O code | sonnet |
| CodeRabbit | `coderabbit:code-reviewer` | 6 (T1) | Always | sonnet |
| Safety Reviewer (merged) | `safety-reviewer` | 6 (T2) | Always — silent failures + security (combined) | sonnet |
| Test Coverage Analyzer | `pr-review-toolkit:pr-test-analyzer` | 6 (T2) | Always — test gaps | sonnet |
| Type Design Analyzer | `pr-review-toolkit:type-design-analyzer` | 6 (T3) | New types/models | haiku |
| API Doc Auditor | `api-doc-auditor` | 6 (T3) | New/modified routes | haiku |
| Invariant Checker | `courierflow-invariant-checker` | 6 (T4) | Always (CF projects) | haiku |
| Defensive Verifier | `defensive-pattern-verifier` | 6 (T4) | Always | haiku |
| Design Reviewer | `general-purpose` | 6 (T5) | UI files modified | sonnet |
| Cross-Cutting Synthesizer | `general-purpose` | 6 (post-tiers) | If any HIGH+ findings | sonnet |
| Code Simplifier | `code-simplifier:code-simplifier` | 6 | After review fixes | opus |

## Skills Invoked Within This Workflow

| Skill | Where Used |
|-------|-----------|
| fetch-api-docs | Phase 5 (pre-implementation gate for external APIs) |
| coding-best-practices | Phase 0 (loaded), Phase 5 (applied) |
| defensive-ui-flows | Phase 0 (loaded), Phase 5 (applied) |
| defensive-backend-flows | Phase 0 (loaded), Phase 5 (applied) |
| writing-plans | Phase 4 (plan creation) |
| investigator | Phase 5 (on unexpected TDD failures — evidence-first before retrying) |
| executing-plans | Phase 5 (plan execution) |
| test-driven-development | Phase 5 (TDD per step) |
| subagent-driven-development | Phase 5 (parallel independent steps) |
| **coderabbit:review** | **Phase 6 Tier 1 (consolidated first-pass code review)** |
| verification-before-completion | Phase 6 (pre-finish check) |
| finishing-a-development-branch | Phase 6 (branch completion) |
| session-learnings | Phase 6 (capture discoveries) |

## Static Analysis & Context Tools (Automatic)

| Tool | Where Used | Purpose |
|------|------------|---------|
| `generate_repo_outline.py` | Phase 2 (pre-exploration) | Token-efficient signatures (targeted areas) |
| `repomix --compress` | Phase 2 (pre-exploration) | Full codebase compressed context (broad awareness) |
| `semgrep` | Phase 5 (per-step), Phase 6 (gate) | Semantic analysis, security checks |
| `ast-grep` | Phase 5 (per-step), Phase 6 (gate) | Structural anti-pattern detection |
| `pyright` | Phase 6 (gate) | Fast type checking |

## Skills Eliminated (Absorbed)

| Former Skill/Pattern | Absorbed Into |
|---------------------|---------------|
| Parallel Opus explorer subagents (x2-3) | **Executor explores directly** — Sonnet reads files firsthand, Opus advisor reviews at the end |
| Parallel Opus architect subagents (x2) | **Executor drafts architectures** — Sonnet proposes options, Opus advisor critiques them |
| Context hydration gate | **Eliminated** — executor already has firsthand context from doing the exploration |
| debate-team (Phase 4b) | **Replaced by Opus advisor plan stress-test** — same rigor, fewer moving parts |
| plancraft brainstorming | Phases 1-3 (discovery + exploration + clarification) |
| brainstorming skill | Phases 1-3 (interactive exploration replaces separate brainstorm) |
| Dual code-reviewer agents | Replaced by **CodeRabbit** (Phase 6 Tier 1) — single consolidated pass |
