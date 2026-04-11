#!/usr/bin/env python3
"""Tests for thinking-budget selector."""
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "tb", Path(__file__).parent / "thinking-budget.py"
)
tb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tb)


# --- Base table ---

def test_simple_tier_discovery_is_think():
    assert tb.select_thinking_budget("discovery", "simple") == "think"


def test_complex_tier_architecture_is_ultrathink():
    assert tb.select_thinking_budget("architecture", "complex") == "ultrathink"


def test_moderate_tier_exploration_is_think_harder():
    assert tb.select_thinking_budget("exploration", "moderate") == "think harder"


def test_simple_tier_architecture_has_safety_floor():
    # Architecture never drops below think harder even for simple tier
    assert tb.select_thinking_budget("architecture", "simple") == "think harder"


# --- Retry escalation ---

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


def test_high_retry_rate_escalates_two_levels():
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


# --- CLI ---

def test_cli_returns_budget():
    result = subprocess.run(
        [sys.executable, "scripts/thinking-budget.py",
         "--phase", "exploration", "--tier", "moderate"],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "think harder"


def test_cli_override():
    result = subprocess.run(
        [sys.executable, "scripts/thinking-budget.py",
         "--phase", "implementation", "--tier", "simple",
         "--override", "ultrathink"],
        cwd=str(Path(__file__).parent.parent),
        capture_output=True, text=True,
    )
    assert result.stdout.strip() == "ultrathink"


if __name__ == "__main__":
    # Simple runner — call all test_* functions
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
