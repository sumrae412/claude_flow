# docs/plans/ — Index

Plans and design docs for claude_flow features. Pairs are listed as **Design → Plan/Implementation** where both exist.

## Archive & deletion policy

Plans whose work has shipped, been superseded, or otherwise wrapped up get moved to [`docs/archive/plans/`](../archive/plans/). Archived plans are **deletion candidates if untouched for 90 days** — checked by `git log --since 90.days.ago -- docs/archive/plans/`. Anything outside that window with no new commits is fair game to delete in the next cleanup pass; git history preserves the contents either way.

If you reach into the archive to revive a plan, edit the file in place — that touch resets the 90-day clock.

---

## Active plans

### Self-debugging & agent intelligence

- [Advanced Agent Intelligence for code-creation-workflow](2026-04-06-advanced-agent-intelligence-design.md) → [Implementation Plan](2026-04-06-advanced-agent-intelligence-plan.md)
- [Session Intelligence — 5 Improvements Design](2026-04-11-session-intelligence-design.md)
- [Self-Modification Engine](2026-04-07-self-modification-design.md)

### Swarm intelligence

- [Swarm Intelligence for code-creation-workflow](2026-04-06-swarm-intelligence-workflow-design.md) → [Implementation Plan](2026-04-06-swarm-intelligence-implementation-plan.md)

### Auto-tuning & adaptive behavior

- [Auto-Tuning Thinking Budgets — Design](2026-04-07-auto-tuning-thinking-budgets-design.md) → [Implementation Plan](2026-04-07-auto-tuning-thinking-budgets.md)
- [Prompt Optimization Engine — Design](2026-04-05-prompt-optimization-design.md)

### Research team

- [Research Team Architecture — Design Doc](2026-04-11-research-team-design.md) → [Implementation Plan](2026-04-11-research-team-plan.md)

### Reviewers & adversarial evaluators

- [Rewrite test-file calibration cases as production-code variants](2026-04-16-adversarial-corpus-test-coverage-rewrite.md)
- [Soften the adversarial-breaker persona scoring band](2026-04-16-adversarial-persona-softening.md)

### Workflow structure

- [Workflow State Machine & Schema Validation Design](2026-04-11-workflow-state-machine-design.md) → [Implementation Plan](2026-04-11-workflow-state-machine-plan.md)
- [Workflow Improvements from External Pattern Mining](2026-04-15-workflow-improvements.md)
- [Quality Gate, Task Taxonomy, and Coverage Mapping](2026-04-11-quality-gate-task-taxonomy-design.md)
- [Mockup State Matrix + Refactor-Path Extract](2026-04-15-mockup-state-matrix-and-extract.md)

### Token efficiency

- [Token Efficiency Phase 2 — Implementation Plan](2026-04-18-token-efficiency-phase-2.md) (handoff: [2026-04-18-token-efficiency-phase-2-handoff.md](2026-04-18-token-efficiency-phase-2-handoff.md))

### Performance

- [Performance Dashboard](2026-04-07-performance-dashboard-design.md)

### Plugins & skills

- [Plugin Conversion + Next-Step Hints Design](2026-04-11-plugin-conversion-design.md)
- [Skills Consolidation Plan](2026-04-16-skills-consolidation.md)
- [Hook Improvements Implementation Plan](2026-04-17-hook-improvements.md)

### Memory operations

- [Memory Operations Gap Plan](2026-04-27-memory-operations-gap-plan.md)

### Session state

- [Session Handoff — 2026-04-24 — Advisor A/B Eval Tuning](2026-04-24-session-handoff.md)

---

## Archived (shipped / superseded — 90-day deletion window)

All archived 2026-05-17. See policy note at top.

| File | Status |
|------|--------|
| [Platform Layer — design](../archive/plans/2026-04-05-platform-layer-design.md) + [implementation](../archive/plans/2026-04-05-platform-layer-implementation.md) | Shipped (PR #2) |
| [Production Readiness Check — design](../archive/plans/2026-04-05-production-readiness-check-design.md) + [implementation](../archive/plans/2026-04-05-production-readiness-check-implementation.md) | Shipped (PR #21) |
| [Self-Debugging Agents — design](../archive/plans/2026-04-05-self-debugging-agents-design.md) + [implementation](../archive/plans/2026-04-05-self-debugging-agents-implementation.md) | Shipped |
| [Token Efficiency Overhaul — design](../archive/plans/2026-04-11-token-efficiency-overhaul-design.md) + [plan](../archive/plans/2026-04-11-token-efficiency-overhaul-plan.md) | Shipped (PR #43) |
| [Requirements Validation / Bug Fix — design](../archive/plans/2026-04-11-requirements-validation-bugfix-design.md) + [plan](../archive/plans/2026-04-11-requirements-validation-bugfix-plan.md) | Shipped (PR #22) |
| [Adversarial Evaluator Plan](../archive/plans/2026-04-15-adversarial-evaluator-plan.md) | Shipped (PR #38) |
| [Excalidraw Canvas + Curmudgeon — design](../archive/plans/2026-04-15-excalidraw-canvas-curmudgeon-design.md) + [plan](../archive/plans/2026-04-15-excalidraw-canvas-curmudgeon-plan.md) | Shipped (PR #40) |
| [Mid-Run Context Extraction — design](../archive/plans/2026-04-15-mid-run-context-extraction-design.md) + [plan](../archive/plans/2026-04-15-mid-run-context-extraction-plan.md) | Shipped |
| [Memory Compilation — design](../archive/plans/2026-04-10-memory-compilation-design.md) + [plan](../archive/plans/2026-04-10-memory-compilation.md) | Shipped (lint-memory + memory-archive) |
| [Advisor A/B Eval Tuning](../archive/plans/2026-04-24-advisor-ab-eval-tuning.md) | Superseded by [advisor-tool-verdict](../decisions/2026-04-24-advisor-tool-verdict.md) |
| [Sonnet-vs-Opus Downgrade Eval](../archive/plans/2026-04-24-sonnet-opus-downgrade-eval.md) | Shipped (PR #51) — see [decision](../decisions/2026-04-24-sonnet-vs-opus-phase-downgrade.md) |
| [Cleanup Report 2026-05-07](../archive/plans/cleanup-report-2026-05-07.md) | Autonomous-cleanup historical report |
| [Cleanup Report 2026-05-08](../archive/plans/cleanup-report-2026-05-08.md) | Autonomous-cleanup historical report |

---

## Cross-link convention

Design ↔ Plan/Implementation pairs should each carry a one-line companion reference at the top of the doc, immediately after the H1 and any `**Created:** / **Status:**` metadata:

```
**Companion:** [<Title>](<path>.md)
```

Audits and decision docs with a parent eval plan should link the plan; eval plans should link their verdict in `docs/decisions/`.
