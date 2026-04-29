#!/usr/bin/env python3
"""LLM-as-a-judge — structured rubric scoring with a high-reasoning model.

Replaces coarse substring-match rubric scoring (and implicit human inspection
of `response_text`) with an Opus-graded per-criterion pass/fail plus rationale.
Every judge call is logged to the invocation ledger for cost/ROI tracking.

Usage from Python:

    from llm_judge import judge_response

    result = judge_response(
        response_text=model_output,
        rubric=case["rubric"],
        context=case.get("context"),
        question=case.get("question"),
        session_id="advisor-ab-2026-04-22",
        case_name=case["name"],
        arm="opus_solo",
    )
    # result = {
    #   "score": 0.75,
    #   "per_criterion": [{"criterion": ..., "passed": bool, "rationale": ...}, ...],
    #   "judge_model": "claude-opus-4-7",
    #   "cost_usd": float,
    #   "wall_time_s": float,
    # }

Dry-run mode (no API key, no network) produces a deterministic synthetic
result so downstream wiring can be tested without burning money.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

# ledger + pricing live next to this file
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger import log_invocation  # type: ignore[import-not-found]
from pricing import compute_cost as _compute_cost  # type: ignore[import-not-found]


class CriterionResult(BaseModel):
    """One row of the judge's per-criterion verdict.

    `passed` is strict: we only accept a real bool. Truthy strings like "yes"
    or "true" are rejected so the judge can't slip a soft verdict past us.
    """
    criterion: str
    passed: bool
    rationale: str = ""

    @field_validator("passed", mode="before")
    @classmethod
    def _strict_bool(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        raise ValueError(f"passed must be a bool, got {type(v).__name__}: {v!r}")


class JudgeResult(BaseModel):
    """Strict schema for the judge's reply.

    The model is instructed to emit exactly this shape. Extra keys are
    ignored (forward-compatible); missing `per_criterion` fails validation
    with a clear path.
    """
    per_criterion: list[CriterionResult] = Field(default_factory=list)

DEFAULT_JUDGE_MODEL = "claude-opus-4-7"
DEFAULT_MAX_TOKENS = 2048


JUDGE_SYSTEM_PROMPT = """You are a strict, calibrated grader.

You will be given:
  1. A set of RUBRIC CRITERIA (each a short human-readable statement).
  2. Optional CONTEXT and QUESTION the responder was answering.
  3. The RESPONSE under review.

For each criterion, decide whether the response satisfies it. Judge on
substance, not surface form — a criterion that says "names durability" is
satisfied whether the response uses the word "durable", "persistent", or
describes the concept in other words.

EVALUATION PRIORITIES (in order):
1. Correctness and completeness against the rubric, context, and question.
   The response must solve the actual problem, not merely resemble an ideal
   answer. Mentally trace whether the recommendation or fix would work.
2. Regression and risk coverage. Prefer answers that handle realistic edge
   cases and failure modes, even when they are longer or less polished.
3. Style, brevity, minimality, clarity, formatting, and "gold answer" likeness
   are tiebreakers only after substantive correctness is established.

BIAS GUARDRAILS:
- Do not reward an answer because it is concise, clean, elegant, or familiar.
- Do not penalize an answer merely for extra detail, redundant explanation,
  helper structure, tests, docs, or a messier presentation if it satisfies the
  criterion.
- A clean-looking partial answer fails a criterion that a verbose but complete
  answer satisfies.
- Ignore wording, variable names, section headings, and prose polish unless the
  rubric explicitly asks for them.

Return valid JSON with this exact shape:
{
  "per_criterion": [
    {"criterion": "<verbatim criterion text>", "passed": true|false, "rationale": "<one sentence>"},
    ...
  ]
}

No prose outside the JSON. No markdown fences. Be strict: if a response only
gestures at a criterion without substantively addressing it, mark it failed
and explain why in the rationale."""


def _build_user_prompt(
    response_text: str,
    rubric: list[dict[str, Any]],
    context: str | None,
    question: str | None,
) -> str:
    criteria_block = "\n".join(
        f"{i+1}. {item['criterion']}" for i, item in enumerate(rubric)
    )
    parts = [f"RUBRIC CRITERIA:\n{criteria_block}"]
    if context:
        parts.append(f"CONTEXT:\n{context}")
    if question:
        parts.append(f"QUESTION:\n{question}")
    parts.append(f"RESPONSE UNDER REVIEW:\n{response_text}")
    parts.append("Return the JSON object now.")
    return "\n\n".join(parts)


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def _strip_fence(text: str) -> str:
    """Remove a leading/trailing ```json ... ``` block if present."""
    stripped = text.strip()
    m = _FENCE_RE.search(stripped)
    return m.group(1) if m else stripped


def _parse_judge_json(text: str, rubric: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Parse the judge's reply into per-criterion dicts via Pydantic.

    The model emits a JudgeResult shape. We validate strictly (typed bools,
    string rationales), then fill in any missing rubric criteria with
    passed=False so downstream score math never silently drops items.

    Raises ValueError on malformed JSON or Pydantic validation failure — the
    caller records it as a judge failure and falls back to all-failed.
    """
    stripped = _strip_fence(text)
    try:
        result = JudgeResult.model_validate_json(stripped)
    except ValidationError as e:
        raise ValueError(f"judge output failed schema validation: {e}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"judge returned non-JSON: {e}; got: {text[:200]!r}") from e

    by_criterion = {c.criterion: c for c in result.per_criterion}

    normalized: list[dict[str, Any]] = []
    for item in rubric:
        crit_text = item["criterion"]
        match = by_criterion.get(crit_text)
        if match is None:
            normalized.append({
                "criterion": crit_text,
                "passed": False,
                "rationale": "judge did not address this criterion",
            })
        else:
            normalized.append({
                "criterion": match.criterion,
                "passed": match.passed,
                "rationale": match.rationale,
            })
    return normalized


def judge_response(
    *,
    response_text: str,
    rubric: list[dict[str, Any]],
    context: str | None = None,
    question: str | None = None,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    session_id: str | None = None,
    case_name: str | None = None,
    arm: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Run one rubric through the judge model. Logs to ledger on return.

    Dry-run: every criterion is marked passed=False with a synthetic rationale,
    no API call, no ledger write. Useful for structural tests.
    """
    if not rubric:
        return {
            "score": 0.0,
            "per_criterion": [],
            "judge_model": judge_model,
            "cost_usd": 0.0,
            "wall_time_s": 0.0,
        }

    if dry_run:
        per_crit = [
            {"criterion": item["criterion"], "passed": False, "rationale": "dry-run"}
            for item in rubric
        ]
        return {
            "score": 0.0,
            "per_criterion": per_crit,
            "judge_model": judge_model,
            "cost_usd": 0.0,
            "wall_time_s": 0.0,
            "dry_run": True,
        }

    # Lazy import so dry-run paths don't require the SDK
    from anthropic import Anthropic  # noqa: F401

    client = Anthropic()
    user_prompt = _build_user_prompt(response_text, rubric, context, question)

    t0 = time.monotonic()
    success = True
    error: str | None = None
    response_content = ""
    usage_in: int | None = None
    usage_out: int | None = None
    cache_read: int | None = None
    cache_create: int | None = None
    try:
        # Prompt caching NOT wired here. Attempted in 2026-04-24 Step 3 but the
        # judge's cacheable prefix (JUDGE_SYSTEM_PROMPT + rubric + context +
        # question ≈ 400-650 tokens) sat under Anthropic's 1024-token minimum,
        # so cache_control silently no-ops. Cache-field extraction and
        # compute_cost() cache-token support are kept intact so the wiring
        # flips on cleanly when prompts grow past that threshold.
        resp = client.messages.create(
            model=judge_model,
            max_tokens=max_tokens,
            system=JUDGE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        for block in getattr(resp, "content", []):
            if getattr(block, "type", None) == "text":
                response_content += getattr(block, "text", "")
        usage = getattr(resp, "usage", None)
        usage_in = getattr(usage, "input_tokens", None) if usage else None
        usage_out = getattr(usage, "output_tokens", None) if usage else None
        cache_read = getattr(usage, "cache_read_input_tokens", None) if usage else None
        cache_create = getattr(usage, "cache_creation_input_tokens", None) if usage else None
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"

    wall = time.monotonic() - t0

    per_crit: list[dict[str, Any]]
    if success:
        try:
            per_crit = _parse_judge_json(response_content, rubric)
        except ValueError as e:
            success = False
            error = str(e)
            per_crit = [
                {"criterion": item["criterion"], "passed": False, "rationale": error}
                for item in rubric
            ]
    else:
        per_crit = [
            {"criterion": item["criterion"], "passed": False, "rationale": error or "call failed"}
            for item in rubric
        ]

    score = sum(1 for c in per_crit if c["passed"]) / len(rubric)

    cost_usd = _compute_cost(
        judge_model, usage_in, usage_out,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_create,
    )

    logged = log_invocation(
        caller="llm_judge",
        model=judge_model,
        wall_time_s=wall,
        input_tokens=usage_in,
        output_tokens=usage_out,
        success=success,
        error=error,
        session_id=session_id,
        arm=arm,
        case=case_name,
        score=score,
        extras={
            "rubric_n": len(rubric),
            "cache_read_input_tokens": cache_read,
            "cache_creation_input_tokens": cache_create,
        },
        cost_usd=cost_usd,
    )

    return {
        "score": round(score, 4),
        "per_criterion": per_crit,
        "judge_model": judge_model,
        "cost_usd": logged["cost_usd"],
        "wall_time_s": logged["wall_time_s"],
        "success": success,
        "error": error,
    }
