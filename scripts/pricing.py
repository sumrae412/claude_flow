#!/usr/bin/env python3
"""Shared LLM pricing table + cost attribution.

Single source of truth for per-model USD rates. Consumed by the invocation
ledger and any eval runner that needs to compute cost from token counts.

Rates are USD per million tokens. Verify against the provider's current
pricing page before running live evals — model pricing changes silently.

Sources to re-check before a live run:
- Anthropic:  https://www.anthropic.com/pricing
- OpenAI:     https://openai.com/api/pricing
- DeepSeek:   https://api-docs.deepseek.com/quick_start/pricing
"""
from __future__ import annotations

# USD per million tokens. Keep model IDs stable with those used at the call site
# (e.g. evals/advisor_tool_ab/run_ab.py MODEL_SONNET / MODEL_OPUS).
#
# Values below are snapshots; TODO flags mark rates that must be verified.
PRICING: dict[str, dict[str, float]] = {
    # Anthropic — verify before live run
    "claude-opus-4-7":     {"input": 15.00, "output": 75.00},  # TODO: verify
    "claude-sonnet-4-6":   {"input": 3.00,  "output": 15.00},  # TODO: verify
    "claude-haiku-4-5":    {"input": 1.00,  "output": 5.00},   # TODO: verify
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},  # TODO: verify
    # OpenAI — verify before live run
    "gpt-4o":              {"input": 2.50,  "output": 10.00},  # TODO: verify
    # DeepSeek — verify before live run
    "deepseek-chat":       {"input": 0.27,  "output": 1.10},   # TODO: verify
}


def compute_cost(model: str, input_tokens: int | None, output_tokens: int | None) -> float:
    """USD cost for one invocation.

    Returns 0.0 for an unknown model or when token counts are missing, so the
    caller can still log the row without blowing up. Unknown models are the
    caller's signal to add a row to PRICING.
    """
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    return (in_tok * rates["input"] + out_tok * rates["output"]) / 1_000_000


def is_priced(model: str) -> bool:
    """True if PRICING has a non-zero entry for this model."""
    rates = PRICING.get(model)
    if rates is None:
        return False
    return rates["input"] > 0.0 or rates["output"] > 0.0
