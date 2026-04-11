#!/usr/bin/env python3
from __future__ import annotations
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
    """Return 'think', 'think harder', or 'ultrathink' for (phase, tier).

    Escalates based on historical retry rate for (phase, domain) if registry
    is provided. Architecture phase has a safety floor of 'think harder'.
    """
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
