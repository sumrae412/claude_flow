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
    # Anthropic — verified 2026-04-24 against claude.com/pricing +
    # platform.claude.com/docs/en/about-claude/pricing (triangulated).
    # Opus 4.7 dropped 66% from the prior $15/$75 snapshot.
    "claude-opus-4-7":     {"input": 5.00,  "output": 25.00},
    "claude-sonnet-4-6":   {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":    {"input": 1.00,  "output": 5.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    # OpenAI — verify before live run.
    # gpt-5 family added 2026-04-27 alongside the plancraft_review default
    # flip from gpt-4o to gpt-5.5. Rates below are placeholders — OpenAI's
    # pricing page is JS-rendered (WebFetch unreliable). Update from
    # https://openai.com/api/pricing before any live eval that depends on
    # exact $/run accounting.
    "gpt-4o":              {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},   # TODO: verify
    "gpt-4.1":             {"input": 2.00,  "output": 8.00},   # TODO: verify
    "gpt-4.1-mini":        {"input": 0.40,  "output": 1.60},   # TODO: verify
    "gpt-4.1-nano":        {"input": 0.10,  "output": 0.40},   # TODO: verify
    "gpt-5":               {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-5-mini":          {"input": 0.25,  "output": 2.00},   # TODO: verify
    "gpt-5-nano":          {"input": 0.05,  "output": 0.40},   # TODO: verify
    "gpt-5-pro":           {"input": 5.00,  "output": 20.00},  # TODO: verify
    "gpt-5-codex":         {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-5.1":             {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-5.2":             {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-5.4":             {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-5.5":             {"input": 2.50,  "output": 10.00},  # TODO: verify
    "gpt-5.5-pro":         {"input": 5.00,  "output": 20.00},  # TODO: verify
    "gpt-5.5-2026-04-23":  {"input": 2.50,  "output": 10.00},  # dated alias
    # DeepSeek — verify before live run
    "deepseek-chat":       {"input": 0.27,  "output": 1.10},   # TODO: verify
    "deepseek-v4-flash":   {"input": 0.27,  "output": 1.10},   # TODO: verify
}


def compute_cost(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_read_input_tokens: int | None = None,
    cache_creation_input_tokens: int | None = None,
) -> float:
    """USD cost for one invocation.

    Returns 0.0 for an unknown model or when token counts are missing, so the
    caller can still log the row without blowing up. Unknown models are the
    caller's signal to add a row to PRICING.

    Cache accounting follows Anthropic's published multipliers:
        cache_read:  0.1x base input rate (cache hit)
        cache_write: 1.25x base input rate (ephemeral 5-minute write)
    Anthropic's `input_tokens` excludes cache tokens; they're separate fields.
    """
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    in_tok = input_tokens or 0
    out_tok = output_tokens or 0
    cache_read = cache_read_input_tokens or 0
    cache_write = cache_creation_input_tokens or 0
    base_in = rates["input"]
    cost = (
        in_tok * base_in
        + cache_read * base_in * 0.1
        + cache_write * base_in * 1.25
        + out_tok * rates["output"]
    )
    return cost / 1_000_000


def is_priced(model: str) -> bool:
    """True if PRICING has a non-zero entry for this model."""
    rates = PRICING.get(model)
    if rates is None:
        return False
    return rates["input"] > 0.0 or rates["output"] > 0.0
