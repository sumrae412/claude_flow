"""Reusable adversarial-breaker dispatch helper.

Used by:
- ``tests/test_adversarial_breaker_live.py`` — single-fixture live drift test
  that overwrites ``recorded_response.json`` after each successful run.
- ``scripts/calibrate_adversarial_breaker.py`` — multi-case calibration loop
  that scores the reviewer against a labeled corpus.

Both call through this module so any contract drift hits both surfaces
together rather than diverging silently.

The Anthropic API direct call is an approximation of the Phase 6 production
dispatch path (which routes through the Task tool with
``subagent_type=general-purpose``). Behavior is substantially the same — same
model, same system prompt, same user message — but a future hardening pass
could swap this for a shell-out to the real Phase 6 dispatcher once it lives
in importable code.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

DEFAULT_MODEL = "claude-sonnet-4-5-20250929"

# Ledger import is best-effort — adversarial_dispatch must keep working even
# when invoked from a context where scripts/ isn't on sys.path (e.g. a
# subprocess unit test). Missing ledger = silent no-op, not a crash.
_LEDGER_LOG: Any = None
try:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from ledger import log_invocation as _LEDGER_LOG  # type: ignore[import-not-found]
except Exception:
    _LEDGER_LOG = None


def get_model() -> str:
    """Resolve the model identifier, honoring ``ADVERSARIAL_BREAKER_MODEL``."""
    return os.environ.get("ADVERSARIAL_BREAKER_MODEL", DEFAULT_MODEL)


def extract_json(text: str) -> str:
    """Pull the JSON envelope out of a model response.

    The persona instructs ``no prose outside JSON``, but be defensive about
    the rare case where the model wraps the response in markdown fences or
    emits a leading explanatory sentence.
    """
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    first = text.find("{")
    last = text.rfind("}")
    if first != -1 and last != -1 and last > first:
        return text[first : last + 1]
    return text


def dispatch_via_anthropic_api(
    persona: str,
    diff: str,
    *,
    model: str | None = None,
    max_tokens: int = 2000,
    session_id: str | None = None,
    case: str | None = None,
) -> dict[str, Any]:
    """Dispatch the adversarial-breaker persona against a single diff.

    Returns the parsed JSON envelope. Caller is responsible for asserting
    contract bounds (criterion names, score range, etc.) — this helper does
    not validate, only dispatches and parses.

    Every call is logged to the invocation ledger (cost / wall time / tokens)
    so calibration runs show up in ROI summaries alongside other LLM calls.
    `session_id` and `case` are optional correlation fields — calibration
    passes them so per-case rows group together.

    Raises:
        ImportError: ``anthropic`` SDK not installed.
        json.JSONDecodeError: model response could not be parsed as JSON
            even after stripping fenced code blocks.

    The ``ANTHROPIC_API_KEY`` environment variable must be set; the
    Anthropic client picks it up automatically.
    """
    from anthropic import Anthropic  # lazy import so module loads without SDK

    client = Anthropic()
    user_msg = (
        "Review the following unified diff against the criteria in your "
        "instructions. Emit only the JSON envelope, nothing else.\n\n"
        f"```diff\n{diff}\n```"
    )
    resolved_model = model or get_model()

    t0 = time.monotonic()
    success = True
    error: str | None = None
    resp = None
    try:
        resp = client.messages.create(
            model=resolved_model,
            max_tokens=max_tokens,
            system=persona,
            messages=[{"role": "user", "content": user_msg}],
        )
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"
    wall_time_s = time.monotonic() - t0

    # Ledger log — best-effort, never masks the underlying dispatch behavior.
    if _LEDGER_LOG is not None:
        usage = getattr(resp, "usage", None) if resp is not None else None
        try:
            _LEDGER_LOG(
                caller="adversarial_breaker",
                model=resolved_model,
                wall_time_s=wall_time_s,
                input_tokens=getattr(usage, "input_tokens", None) if usage else None,
                output_tokens=getattr(usage, "output_tokens", None) if usage else None,
                success=success,
                error=error,
                session_id=session_id,
                case=case,
            )
        except Exception:
            pass  # ledger failures must not break the dispatch path

    if not success:
        raise RuntimeError(error or "adversarial dispatch failed")

    raw = resp.content[0].text
    return json.loads(extract_json(raw))
