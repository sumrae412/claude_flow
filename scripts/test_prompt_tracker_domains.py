#!/usr/bin/env python3
"""Tests for prompt-tracker retry_rates_by_domain population."""
import importlib.util
import sys
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
    rates = variant["metrics"]["retry_rates_by_domain"]
    assert rates["routes"]["attempts"] == 2
    assert rates["routes"]["retries"] == 1
    assert rates["routes"]["rate"] == 0.5
    assert rates["migrations"]["attempts"] == 1
    assert rates["migrations"]["retries"] == 2


def test_events_without_domain_ignored():
    variant = {"metrics": {}}
    events = [
        {"phase5_retries": 5, "files_used_in_impl": ["a"], "files_found": ["a"]},
        {"domain": "routes", "phase5_retries": 0, "files_used_in_impl": ["b"], "files_found": ["b"]},
    ]
    pt._update_explorer_metrics(variant, events)
    rates = variant["metrics"]["retry_rates_by_domain"]
    assert "routes" in rates
    assert len(rates) == 1


if __name__ == "__main__":
    import inspect
    tests = [fn for name, fn in globals().items()
             if name.startswith("test_") and inspect.isfunction(fn)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
