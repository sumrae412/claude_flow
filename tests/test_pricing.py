"""Tests for scripts/pricing.py — cost attribution + pricing table integrity."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pricing import PRICING, compute_cost, is_priced  # noqa: E402


def test_compute_cost_known_model():
    # Opus 4.7: 1M input @ $5 + 1M output @ $25 = $30
    cost = compute_cost("claude-opus-4-7", 1_000_000, 1_000_000)
    assert cost == 30.0


def test_compute_cost_proportional():
    # Half the tokens → half the cost.
    full = compute_cost("claude-sonnet-4-6", 1_000_000, 1_000_000)
    half = compute_cost("claude-sonnet-4-6", 500_000, 500_000)
    assert abs(half * 2 - full) < 1e-9


def test_compute_cost_unknown_model_returns_zero():
    assert compute_cost("definitely-not-a-model", 10_000, 10_000) == 0.0


def test_compute_cost_none_tokens_returns_zero():
    assert compute_cost("claude-opus-4-7", None, None) == 0.0
    assert compute_cost("claude-opus-4-7", 1000, None) > 0.0


def test_is_priced_reflects_table():
    assert is_priced("claude-opus-4-7") is True
    assert is_priced("definitely-not-a-model") is False


def test_pricing_table_shape():
    # Every entry must expose both input and output rates as floats.
    for model, rates in PRICING.items():
        assert "input" in rates, f"{model} missing input rate"
        assert "output" in rates, f"{model} missing output rate"
        assert isinstance(rates["input"], (int, float))
        assert isinstance(rates["output"], (int, float))
