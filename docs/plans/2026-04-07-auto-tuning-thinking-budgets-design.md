# Auto-Tuning Thinking Budgets

**Date:** 2026-04-07
**Status:** Approved

## Problem

Thinking budgets are currently hardcoded per phase in `code-creation-workflow/SKILL.md` with manual "escalate when" heuristics. Simple tasks over-think; complex tasks under-think. The complexity classifier already produces a tier (`simple`/`moderate`/`complex`) in Phase 1 but does not drive thinking budget selection.

## Goal

Replace static phase→thinking mappings with dynamic per-step selection based on (a) the existing complexity classifier tier and (b) per-domain historical retry rates.

## Design

### 1. Tier → base budget table

Replaces the static phase mapping in SKILL.md lines 47-55.

| Tier | Discovery | Exploration | Clarification | Architecture | Implementation | Review |
|------|-----------|-------------|---------------|--------------|----------------|--------|
| `simple` | think | think | think | think harder | think | think |
| `moderate` | think | think harder | think | ultrathink | think | think harder |
| `complex` | think harder | ultrathink | think harder | ultrathink | think harder | ultrathink |

**Safety floor:** Architecture phase never drops below `think harder` regardless of escalation direction.

### 2. Retry-based escalation

Per `(phase, domain)` key, track retry rate from session history. At dispatch:

- `< 10%` retry rate → use base budget from table
- `10-30%` → escalate one level (think → think harder → ultrathink)
- `> 30%` → escalate two levels (cap at ultrathink)

Domain = task type from smart-exploration (`routes`, `migrations`, `tests`, `ui`, etc.).

### 3. Single entry point

```python
# scripts/thinking-budget.py
def select_thinking_budget(
    phase: str,              # "discovery" | "exploration" | ... | "review"
    tier: str,               # "simple" | "moderate" | "complex"
    domain: str | None = None,
    registry: dict | None = None,
) -> str:
    """Return 'think', 'think harder', or 'ultrathink'."""
```

SKILL.md replaces hardcoded `ultrathink about...` / `think harder about...` with `{{budget}} about...` placeholders filled in by the workflow at dispatch time.

### 4. Registry additions

Extend existing per-agent history in registry:

```json
{
  "agents": {
    "explorer": {
      "retry_rates_by_domain": {
        "routes": {"attempts": 12, "retries": 2, "rate": 0.17},
        "migrations": {"attempts": 4, "retries": 3, "rate": 0.75}
      }
    }
  }
}
```

Updated by existing `record_event` path — no new hooks needed.

### 5. User override

`--budget=think|think-harder|ultrathink` flag accepted at any phase, mirroring existing `--tier=` override. Skips auto-selection.

## Non-goals

- New structural metrics (file count, LOC) — MEMORY.md says prefer cognitive complexity
- Changing the classifier itself — already works
- Changing tier propagation — already works
- New model selection (Opus vs Sonnet) — separate concern

## Implementation sketch

1. `scripts/thinking-budget.py` — new, ~80 lines: tier table, escalation logic, single `select_thinking_budget` function
2. `scripts/prompt-tracker.py` — extend `_update_explorer_metrics` and friends to populate `retry_rates_by_domain`
3. `skills/code-creation-workflow/SKILL.md` — replace hardcoded thinking keywords with `{{budget}}` placeholders (Phases 1-6 dispatch sections)
4. `skills/code-creation-workflow/references/swarm-protocols.md` — document the auto-tuning step in dispatch pipeline
5. Tests: `scripts/test_thinking_budget.py` — table lookups, retry escalation, override behavior, safety floor

## Trade-offs considered

| Option | Pro | Con | Verdict |
|--------|-----|-----|---------|
| Classifier tier + retry rates | Reuses existing infra, two signals | Needs retry history to be useful | **Chosen** |
| Structural metrics only | Easy to compute | File count ≠ cognitive complexity | Rejected |
| Classifier tier only | Simplest | Misses per-domain patterns (e.g., migrations always retry) | Rejected |
| Full ML model | Maximally adaptive | Overkill, opaque, hard to debug | Rejected |
