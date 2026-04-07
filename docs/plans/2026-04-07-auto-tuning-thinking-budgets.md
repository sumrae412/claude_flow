# Auto-Tuning Thinking Budgets Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace static phase→thinking-budget mappings with dynamic per-step selection driven by the complexity classifier tier and per-domain retry rates.

**Architecture:** Single pure function `select_thinking_budget(phase, tier, domain, registry)` returns one of `think` / `think harder` / `ultrathink`. SKILL.md calls it at each dispatch site via `{{budget}}` placeholder. Registry gains `retry_rates_by_domain` field populated by existing `record_event` path.

**Tech Stack:** Python 3.11, stdlib only. No new deps.

**Design doc:** `docs/plans/2026-04-07-auto-tuning-thinking-budgets-design.md`

---

## Task 1: Create thinking-budget module with base table

**Files:**
- Create: `scripts/thinking-budget.py`
- Test: `scripts/test_thinking_budget.py`

**Step 1: Write the failing test**

```python
# scripts/test_thinking_budget.py
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "tb", Path(__file__).parent / "thinking-budget.py"
)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)


def test_simple_tier_discovery_is_think():
    assert tb.select_thinking_budget("discovery", "simple") == "think"


def test_complex_tier_architecture_is_ultrathink():
    assert tb.select_thinking_budget("architecture", "complex") == "ultrathink"


def test_moderate_tier_exploration_is_think_harder():
    assert tb.select_thinking_budget("exploration", "moderate") == "think harder"


def test_simple_tier_architecture_has_safety_floor():
    # Architecture never drops below think harder even for simple tier
    assert tb.select_thinking_budget("architecture", "simple") == "think harder"
```

**Step 2: Run test to verify it fails**

Run: `cd ~/claude_code/claude_flow && /opt/homebrew/bin/python3.11 scripts/test_thinking_budget.py`
Expected: `ModuleNotFoundError` or `FileNotFoundError` for thinking-budget.py

**Step 3: Write minimal implementation**

```python
# scripts/thinking-budget.py
"""Auto-tuning thinking budget selector.

Maps (phase, tier) to a base thinking budget, then optionally escalates
based on per-domain historical retry rates from the registry.
"""

BUDGETS = ["think", "think harder", "ultrathink"]

# (phase, tier) → base budget index into BUDGETS
BASE_TABLE = {
    "discovery":      {"simple": 0, "moderate": 0, "complex": 1},
    "exploration":    {"simple": 0, "moderate": 1, "complex": 2},
    "clarification":  {"simple": 0, "moderate": 0, "complex": 1},
    "architecture":   {"simple": 1, "moderate": 2, "complex": 2},  # floor: think harder
    "implementation": {"simple": 0, "moderate": 0, "complex": 1},
    "review":         {"simple": 0, "moderate": 1, "complex": 2},
}

ARCHITECTURE_FLOOR_INDEX = 1  # think harder


def select_thinking_budget(
    phase: str,
    tier: str,
    domain: str | None = None,
    registry: dict | None = None,
) -> str:
    """Return 'think', 'think harder', or 'ultrathink' for (phase, tier).

    Escalates based on historical retry rate for (phase, domain) if registry
    is provided. Architecture phase has a safety floor of 'think harder'.
    """
    if phase not in BASE_TABLE:
        raise ValueError(f"unknown phase: {phase}")
    if tier not in BASE_TABLE[phase]:
        raise ValueError(f"unknown tier: {tier}")

    idx = BASE_TABLE[phase][tier]
    if phase == "architecture" and idx < ARCHITECTURE_FLOOR_INDEX:
        idx = ARCHITECTURE_FLOOR_INDEX

    return BUDGETS[idx]
```

**Step 4: Run tests to verify they pass**

Run: `cd ~/claude_code/claude_flow && /opt/homebrew/bin/python3.11 -c "
import subprocess, sys
result = subprocess.run([sys.executable, '-c', '''
import importlib.util
from pathlib import Path
spec = importlib.util.spec_from_file_location(\"tb\", \"scripts/thinking-budget.py\")
tb = importlib.util.module_from_spec(spec); spec.loader.exec_module(tb)
assert tb.select_thinking_budget(\"discovery\", \"simple\") == \"think\"
assert tb.select_thinking_budget(\"architecture\", \"complex\") == \"ultrathink\"
assert tb.select_thinking_budget(\"exploration\", \"moderate\") == \"think harder\"
assert tb.select_thinking_budget(\"architecture\", \"simple\") == \"think harder\"
print(\"all pass\")
'''])
"`
Expected: `all pass`

**Step 5: Commit**

```bash
cd ~/claude_code/claude_flow
git add scripts/thinking-budget.py scripts/test_thinking_budget.py
git commit -m "feat: add thinking-budget base table with phase/tier lookup"
```

---

## Task 2: Add retry-rate escalation

**Files:**
- Modify: `scripts/thinking-budget.py`
- Modify: `scripts/test_thinking_budget.py`

**Step 1: Write failing tests**

Add to `test_thinking_budget.py`:

```python
def test_low_retry_rate_no_escalation():
    registry = {
        "agents": {
            "explorer": {
                "retry_rates_by_domain": {
                    "routes": {"attempts": 100, "retries": 5, "rate": 0.05}
                }
            }
        }
    }
    # Moderate exploration base = think harder; <10% retry = no change
    assert tb.select_thinking_budget(
        "exploration", "moderate", domain="routes", registry=registry
    ) == "think harder"


def test_medium_retry_rate_escalates_one_level():
    registry = {
        "agents": {
            "explorer": {
                "retry_rates_by_domain": {
                    "migrations": {"attempts": 10, "retries": 2, "rate": 0.20}
                }
            }
        }
    }
    # Simple exploration base = think; 20% retry → escalate to think harder
    assert tb.select_thinking_budget(
        "exploration", "simple", domain="migrations", registry=registry
    ) == "think harder"


def test_high_retry_rate_escalates_two_levels_capped():
    registry = {
        "agents": {
            "explorer": {
                "retry_rates_by_domain": {
                    "auth": {"attempts": 10, "retries": 5, "rate": 0.50}
                }
            }
        }
    }
    # Simple exploration base = think; >30% → escalate 2 → ultrathink
    assert tb.select_thinking_budget(
        "exploration", "simple", domain="auth", registry=registry
    ) == "ultrathink"


def test_escalation_capped_at_ultrathink():
    registry = {
        "agents": {
            "explorer": {
                "retry_rates_by_domain": {
                    "auth": {"attempts": 10, "retries": 9, "rate": 0.90}
                }
            }
        }
    }
    # Complex exploration base = ultrathink; can't go higher
    assert tb.select_thinking_budget(
        "exploration", "complex", domain="auth", registry=registry
    ) == "ultrathink"
```

**Step 2: Run tests to verify they fail**

Expected: assertion failure on medium/high escalation tests (current impl ignores registry).

**Step 3: Add escalation logic**

Replace `select_thinking_budget` in `scripts/thinking-budget.py`:

```python
LOW_RETRY_THRESHOLD = 0.10
HIGH_RETRY_THRESHOLD = 0.30


def _retry_rate(registry: dict | None, domain: str | None) -> float:
    if not registry or not domain:
        return 0.0
    rates = (
        registry.get("agents", {})
        .get("explorer", {})
        .get("retry_rates_by_domain", {})
    )
    entry = rates.get(domain, {})
    return float(entry.get("rate", 0.0))


def select_thinking_budget(
    phase: str,
    tier: str,
    domain: str | None = None,
    registry: dict | None = None,
) -> str:
    if phase not in BASE_TABLE:
        raise ValueError(f"unknown phase: {phase}")
    if tier not in BASE_TABLE[phase]:
        raise ValueError(f"unknown tier: {tier}")

    idx = BASE_TABLE[phase][tier]

    # Retry-rate escalation
    rate = _retry_rate(registry, domain)
    if rate > HIGH_RETRY_THRESHOLD:
        idx += 2
    elif rate >= LOW_RETRY_THRESHOLD:
        idx += 1

    # Cap at ultrathink
    idx = min(idx, len(BUDGETS) - 1)

    # Architecture safety floor
    if phase == "architecture" and idx < ARCHITECTURE_FLOOR_INDEX:
        idx = ARCHITECTURE_FLOOR_INDEX

    return BUDGETS[idx]
```

**Step 4: Run tests to verify all pass**

Run: `cd ~/claude_code/claude_flow && /opt/homebrew/bin/python3.11 scripts/test_thinking_budget.py`
Expected: no assertion errors

**Step 5: Commit**

```bash
git add scripts/thinking-budget.py scripts/test_thinking_budget.py
git commit -m "feat: add retry-rate escalation to thinking-budget selector"
```

---

## Task 3: Populate retry_rates_by_domain from event history

**Files:**
- Modify: `scripts/prompt-tracker.py` — extend `_update_explorer_metrics`
- Test: append to `scripts/test_thinking_budget.py` or add `scripts/test_prompt_tracker_domains.py`

**Step 1: Read existing explorer metric update**

Run: `grep -n "_update_explorer_metrics" ~/claude_code/claude_flow/scripts/prompt-tracker.py`

**Step 2: Write failing test**

Create `scripts/test_prompt_tracker_domains.py`:

```python
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "pt", Path(__file__).parent / "prompt-tracker.py"
)
pt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pt)


def test_retry_rates_by_domain_populated():
    variant = {"metrics": {}}
    events = [
        {"domain": "routes", "phase5_retries": 0, "files_used_in_impl": ["a"], "files_found": ["a"]},
        {"domain": "routes", "phase5_retries": 1, "files_used_in_impl": ["b"], "files_found": ["b"]},
        {"domain": "migrations", "phase5_retries": 2, "files_used_in_impl": ["c"], "files_found": ["c"]},
    ]
    pt._update_explorer_metrics(variant, events)
    rates = variant["metrics"].get("retry_rates_by_domain", {})
    assert rates["routes"]["attempts"] == 2
    assert rates["routes"]["retries"] == 1
    assert rates["routes"]["rate"] == 0.5
    assert rates["migrations"]["attempts"] == 1
    assert rates["migrations"]["retries"] == 2
    assert rates["migrations"]["rate"] == 2.0  # unbounded; caller clamps
```

**Step 3: Run test to verify it fails**

Expected: `KeyError: 'retry_rates_by_domain'`

**Step 4: Extend `_update_explorer_metrics`**

Find the function in `scripts/prompt-tracker.py` and add after the existing assignments:

```python
    # Per-domain retry rates for thinking-budget auto-tuning
    from collections import defaultdict
    domain_stats = defaultdict(lambda: {"attempts": 0, "retries": 0})
    for ev in variant_events:
        dom = ev.get("domain")
        if not dom:
            continue
        domain_stats[dom]["attempts"] += 1
        domain_stats[dom]["retries"] += ev.get("phase5_retries", 0)
    m["retry_rates_by_domain"] = {
        dom: {
            "attempts": s["attempts"],
            "retries": s["retries"],
            "rate": round(s["retries"] / s["attempts"], 3) if s["attempts"] else 0.0,
        }
        for dom, s in domain_stats.items()
    }
```

**Step 5: Run test to verify it passes**

Run: `cd ~/claude_code/claude_flow && /opt/homebrew/bin/python3.11 scripts/test_prompt_tracker_domains.py`
Expected: no assertion errors (note: `rate` for migrations will be `2.0` — that's OK for now; the budget selector clamps via idx cap)

**Step 6: Commit**

```bash
git add scripts/prompt-tracker.py scripts/test_prompt_tracker_domains.py
git commit -m "feat: populate retry_rates_by_domain in explorer metrics"
```

---

## Task 4: Add CLI command to query thinking budget

**Files:**
- Modify: `scripts/thinking-budget.py` — add `if __name__ == "__main__"` dispatch
- Modify: `scripts/test_thinking_budget.py` — CLI smoke test

**Step 1: Write failing CLI test**

Add to `test_thinking_budget.py`:

```python
import subprocess, sys, os

def test_cli_returns_budget():
    result = subprocess.run(
        [sys.executable, "scripts/thinking-budget.py",
         "--phase", "exploration", "--tier", "moderate"],
        cwd=os.path.expanduser("~/claude_code/claude_flow"),
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "think harder"
```

**Step 2: Run test to verify it fails**

Expected: nonzero exit or wrong output.

**Step 3: Add CLI**

Append to `scripts/thinking-budget.py`:

```python
if __name__ == "__main__":
    import argparse
    import json as _json
    from pathlib import Path as _Path

    parser = argparse.ArgumentParser(description="Select thinking budget for a phase")
    parser.add_argument("--phase", required=True)
    parser.add_argument("--tier", required=True)
    parser.add_argument("--domain", default=None)
    parser.add_argument("--registry", default=None, help="Path to registry JSON")
    parser.add_argument("--override", default=None, help="Force a budget, skipping selection")
    args = parser.parse_args()

    if args.override:
        print(args.override)
    else:
        registry = None
        if args.registry and _Path(args.registry).exists():
            registry = _json.loads(_Path(args.registry).read_text())
        print(select_thinking_budget(args.phase, args.tier, args.domain, registry))
```

**Step 4: Run tests to verify pass**

Run: `cd ~/claude_code/claude_flow && /opt/homebrew/bin/python3.11 scripts/test_thinking_budget.py`
Also manual: `/opt/homebrew/bin/python3.11 scripts/thinking-budget.py --phase architecture --tier complex`
Expected: `ultrathink`

**Step 5: Commit**

```bash
git add scripts/thinking-budget.py scripts/test_thinking_budget.py
git commit -m "feat: add thinking-budget CLI with override support"
```

---

## Task 5: Wire SKILL.md dispatch sites to thinking-budget CLI

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md`

**Step 1: Read the thinking budget table section**

Run: `grep -n "Thinking Budget Control" ~/claude_code/claude_flow/skills/code-creation-workflow/SKILL.md`
Read lines around it (~35-80).

**Step 2: Replace the static phase table with auto-tune reference**

Replace the "Phase-to-thinking mapping" table (the markdown table showing default thinking per phase) with a new section:

```markdown
### Auto-Tuned Thinking Budgets

Thinking budgets are selected per dispatch by `scripts/thinking-budget.py` based on the complexity classifier tier (Phase 1) and per-domain historical retry rates.

At each dispatch site, resolve `{{budget}}` via:

```bash
python3 scripts/thinking-budget.py \
  --phase <phase_name> \
  --tier <tier_from_classifier> \
  --domain <task_domain_or_omit> \
  --registry memory/agent-registry.json
```

**Override:** Pass `--override ultrathink` to force a specific budget. Users can also pass `--budget=` at any phase to skip auto-selection.

**Safety floor:** Architecture phase is never below `think harder` regardless of tier or retry rate.

See `docs/plans/2026-04-07-auto-tuning-thinking-budgets-design.md` for the full table and rationale.
```

Then, anywhere in the dispatch templates where SKILL.md has hardcoded `think about...`, `think harder about...`, or `ultrathink about...`, replace with `{{budget}} about...` placeholders.

**Step 3: Verify no static keywords remain in dispatch templates**

Run: `grep -n "ultrathink about\|think harder about\|think about this" ~/claude_code/claude_flow/skills/code-creation-workflow/SKILL.md`

Any remaining hits should be in example/documentation contexts only, not active dispatch templates. Convert any active ones to `{{budget}}`.

**Step 4: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: wire SKILL.md dispatch sites to thinking-budget CLI"
```

---

## Task 6: Update swarm-protocols.md with auto-tune protocol

**Files:**
- Modify: `skills/code-creation-workflow/references/swarm-protocols.md`

**Step 1: Add new section after Section 1 (Complexity Classifier)**

```markdown
---

## 1b. Thinking Budget Auto-Tuning

Runs at every phase dispatch. Replaces the static phase→thinking mapping.

**Inputs:**
- `phase` — discovery | exploration | clarification | architecture | implementation | review
- `tier` — from classifier (simple/moderate/complex)
- `domain` — task type from smart-exploration (routes, migrations, tests, etc.)
- `registry` — `memory/agent-registry.json`

**Resolution:**
```bash
python3 scripts/thinking-budget.py --phase <phase> --tier <tier> --domain <domain> --registry memory/agent-registry.json
```

Returns one of `think` | `think harder` | `ultrathink`.

**Safety floor:** Architecture phase never below `think harder`.

**Override:** `--override <budget>` forces a specific value, skipping auto-selection.

Full table: `docs/plans/2026-04-07-auto-tuning-thinking-budgets-design.md`
```

**Step 2: Commit**

```bash
git add skills/code-creation-workflow/references/swarm-protocols.md
git commit -m "docs: add thinking-budget auto-tuning protocol"
```

---

## Task 7: Add `domain` field to explorer event schema

**Files:**
- Modify: `skills/code-creation-workflow/references/swarm-schemas.md`
- Modify: `skills/code-creation-workflow/SKILL.md` — Phase 2 record example

**Step 1: Find the explorer event schema**

Run: `grep -n "exploration-event\|explorer.*event\|phase5_retries" ~/claude_code/claude_flow/skills/code-creation-workflow/references/swarm-schemas.md`

**Step 2: Add `domain` field**

In the explorer event schema, add:
```
"domain": "<task domain from smart-exploration, e.g. routes|migrations|tests|ui|auth>"
```

Also update SKILL.md Phase 2 `record` JSON example to include `"domain": "<domain>"`.

**Step 3: Commit**

```bash
git add skills/code-creation-workflow/references/swarm-schemas.md skills/code-creation-workflow/SKILL.md
git commit -m "feat: add domain field to explorer event schema"
```

---

## Task 8: Full integration smoke test

**Files:**
- Create: `scripts/test_thinking_budget_integration.py`

**Step 1: Write end-to-end test**

```python
# scripts/test_thinking_budget_integration.py
"""Smoke test: event recorded → metrics updated → budget escalates."""
import importlib.util, json, tempfile, os
from pathlib import Path

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

here = Path(__file__).parent
pt = _load("pt", here / "prompt-tracker.py")
tb = _load("tb", here / "thinking-budget.py")

# Simulate a high-retry migration domain history
events = [
    {"domain": "migrations", "phase5_retries": 2, "files_found": ["a"], "files_used_in_impl": ["a"]},
    {"domain": "migrations", "phase5_retries": 3, "files_found": ["b"], "files_used_in_impl": ["b"]},
    {"domain": "routes", "phase5_retries": 0, "files_found": ["c"], "files_used_in_impl": ["c"]},
]
variant = {"metrics": {}}
pt._update_explorer_metrics(variant, events)

# Build minimal registry shape
registry = {
    "agents": {
        "explorer": {
            "retry_rates_by_domain": variant["metrics"]["retry_rates_by_domain"]
        }
    }
}

# Migrations has high retry rate → should escalate from base
migr_budget = tb.select_thinking_budget("exploration", "simple", domain="migrations", registry=registry)
routes_budget = tb.select_thinking_budget("exploration", "simple", domain="routes", registry=registry)

print(f"migrations: {migr_budget}")
print(f"routes: {routes_budget}")

# Migrations is at 2.5/session retry rate → far above 30% → ultrathink
assert migr_budget == "ultrathink", f"expected ultrathink, got {migr_budget}"
# Routes is 0% → base budget (think for simple exploration)
assert routes_budget == "think", f"expected think, got {routes_budget}"
print("integration test passed")
```

**Step 2: Run and verify**

Run: `cd ~/claude_code/claude_flow && /opt/homebrew/bin/python3.11 scripts/test_thinking_budget_integration.py`
Expected: `integration test passed`

**Step 3: Commit**

```bash
git add scripts/test_thinking_budget_integration.py
git commit -m "test: add integration smoke test for thinking-budget + prompt-tracker"
```

---

## Task 9: Push and verify

**Step 1: Run all new tests**

```bash
cd ~/claude_code/claude_flow
/opt/homebrew/bin/python3.11 scripts/test_thinking_budget.py
/opt/homebrew/bin/python3.11 scripts/test_prompt_tracker_domains.py
/opt/homebrew/bin/python3.11 scripts/test_thinking_budget_integration.py
```
Expected: all print success / no assertion errors.

**Step 2: Push to main**

```bash
git push
```

**Step 3: Verify on GitHub**

Check `github.com/sumrae412/claude_flow` — commits visible on main.
