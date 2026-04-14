#!/usr/bin/env python3
"""Smoke test: event recorded → metrics updated → budget escalates."""
import importlib.util
import sys
from pathlib import Path


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
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

    # Build minimal registry shape matching what thinking-budget.py expects
    registry = {
        "agents": {
            "explorer": {
                "retry_rates_by_domain": variant["metrics"]["retry_rates_by_domain"]
            }
        }
    }

    migr_budget = tb.select_thinking_budget("exploration", "simple", domain="migrations", registry=registry)
    routes_budget = tb.select_thinking_budget("exploration", "simple", domain="routes", registry=registry)

    print(f"migrations retry rate: {registry['agents']['explorer']['retry_rates_by_domain']['migrations']['rate']}")
    print(f"routes retry rate: {registry['agents']['explorer']['retry_rates_by_domain']['routes']['rate']}")
    print(f"migrations budget: {migr_budget}")
    print(f"routes budget: {routes_budget}")

    # Migrations is at 2.5/session retry rate → far above 30% → escalate 2 → ultrathink
    assert migr_budget == "ultrathink", f"expected ultrathink, got {migr_budget}"
    # Routes is 0% → base budget for simple exploration = think
    assert routes_budget == "think", f"expected think, got {routes_budget}"

    print("\nintegration test passed")


def test_thinking_budget_integration():
    """Pytest entry point — runs the same assertions under pytest collection."""
    main()


if __name__ == "__main__":
    main()
    sys.exit(0)
