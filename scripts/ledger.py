#!/usr/bin/env python3
"""Lightweight invocation ledger — one JSONL row per LLM call.

Append-only. No daemon, no DB. Every row carries enough to compute cost,
wall-time, and ROI after the fact. Readers group by (caller, model, arm,
case, session_id) to answer the usual questions:

  - Which arm is cheapest per unit of rubric/judge score?  (ROI)
  - Is Sonnet+advisor actually faster than Opus-solo?       (latency)
  - How much did we burn on this week's eval re-runs?       (cost)

Schema (per row):
  ts            ISO-8601 UTC timestamp
  session_id    caller-chosen correlation id (eval run id, claude-flow phase id, ...)
  caller        free-form label, e.g. "advisor_ab", "llm_judge", "plancraft_review"
  model         model id used for cost attribution (must match pricing.PRICING)
  arm           optional: eval-arm label (sonnet_solo, opus_solo, ...)
  case          optional: eval-case name
  input_tokens  prompt / input tokens, or null
  output_tokens output / completion tokens, or null
  wall_time_s   monotonic seconds from request to response
  cost_usd      computed from pricing.PRICING (0.0 if model not priced)
  success       True if the call returned normally
  error         short error string on failure, else null
  score         optional: caller-attached quality score for ROI math
  extras        optional: dict for caller-specific fields

CLI usage (for ad-hoc inspection; primary API is Python import):
  python scripts/ledger.py summarize
  python scripts/ledger.py summarize --caller advisor_ab
  python scripts/ledger.py tail -n 20
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from pricing import compute_cost  # type: ignore[import-not-found]

CLAUDE_FLOW_DIR = Path(os.environ.get(
    "CLAUDE_FLOW_DIR",
    Path(__file__).resolve().parent.parent,
))
DEFAULT_LEDGER_PATH = CLAUDE_FLOW_DIR / "memory" / "episodic" / "invocations.jsonl"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log_invocation(
    *,
    caller: str,
    model: str,
    wall_time_s: float,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    success: bool = True,
    error: str | None = None,
    session_id: str | None = None,
    arm: str | None = None,
    case: str | None = None,
    score: float | None = None,
    extras: dict[str, Any] | None = None,
    cost_usd: float | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Append one row and return it.

    If `cost_usd` is None we compute it from `pricing.compute_cost`.
    """
    if cost_usd is None:
        cost_usd = compute_cost(model, input_tokens, output_tokens)

    row: dict[str, Any] = {
        "ts": _utcnow_iso(),
        "session_id": session_id,
        "caller": caller,
        "model": model,
        "arm": arm,
        "case": case,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "wall_time_s": round(wall_time_s, 4),
        "cost_usd": round(cost_usd, 6),
        "success": success,
        "error": error,
        "score": score,
        "extras": extras or {},
    }

    path = ledger_path or DEFAULT_LEDGER_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def read_rows(ledger_path: Path | None = None) -> list[dict[str, Any]]:
    path = ledger_path or DEFAULT_LEDGER_PATH
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _filter(rows: Iterable[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
    """Keep rows where every provided key equals its value (None = no filter)."""
    keep: list[dict[str, Any]] = []
    for r in rows:
        if all(v is None or r.get(k) == v for k, v in kwargs.items()):
            keep.append(r)
    return keep


def summarize(
    *,
    caller: str | None = None,
    session_id: str | None = None,
    ledger_path: Path | None = None,
) -> dict[str, Any]:
    """Group by (caller, model, arm) and report totals + ROI."""
    rows = _filter(read_rows(ledger_path), caller=caller, session_id=session_id)
    if not rows:
        return {"count": 0, "groups": []}

    groups: dict[tuple[str, str, str | None], dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0, "successes": 0, "failures": 0,
            "total_cost_usd": 0.0, "total_wall_time_s": 0.0,
            "total_input_tokens": 0, "total_output_tokens": 0,
            "scores": [],
        }
    )
    for r in rows:
        key = (r.get("caller", "?"), r.get("model", "?"), r.get("arm"))
        g = groups[key]
        g["count"] += 1
        g["successes"] += 1 if r.get("success") else 0
        g["failures"] += 0 if r.get("success") else 1
        g["total_cost_usd"] += r.get("cost_usd") or 0.0
        g["total_wall_time_s"] += r.get("wall_time_s") or 0.0
        g["total_input_tokens"] += r.get("input_tokens") or 0
        g["total_output_tokens"] += r.get("output_tokens") or 0
        if r.get("score") is not None:
            g["scores"].append(r["score"])

    out_groups = []
    for (caller_, model, arm), g in sorted(groups.items()):
        n = g["count"] or 1
        mean_cost = g["total_cost_usd"] / n
        mean_score = sum(g["scores"]) / len(g["scores"]) if g["scores"] else None
        # ROI: mean score per USD. Guard zero cost (pricing unset or free tier).
        if mean_score is not None and g["total_cost_usd"] > 0:
            roi = mean_score / mean_cost
        else:
            roi = None
        out_groups.append({
            "caller": caller_,
            "model": model,
            "arm": arm,
            "count": g["count"],
            "successes": g["successes"],
            "failures": g["failures"],
            "total_cost_usd": round(g["total_cost_usd"], 6),
            "mean_cost_usd": round(mean_cost, 6),
            "total_wall_time_s": round(g["total_wall_time_s"], 3),
            "mean_wall_time_s": round(g["total_wall_time_s"] / n, 3),
            "total_input_tokens": g["total_input_tokens"],
            "total_output_tokens": g["total_output_tokens"],
            "mean_score": round(mean_score, 4) if mean_score is not None else None,
            "roi_score_per_usd": round(roi, 4) if roi is not None else None,
        })

    return {"count": len(rows), "groups": out_groups}


def _tail(n: int, ledger_path: Path | None = None) -> list[dict[str, Any]]:
    rows = read_rows(ledger_path)
    return rows[-n:]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("summarize")
    s.add_argument("--caller")
    s.add_argument("--session-id")
    s.add_argument("--ledger", type=Path, default=None)

    t = sub.add_parser("tail")
    t.add_argument("-n", type=int, default=10)
    t.add_argument("--ledger", type=Path, default=None)

    args = parser.parse_args()

    if args.cmd == "summarize":
        result = summarize(
            caller=args.caller,
            session_id=args.session_id,
            ledger_path=args.ledger,
        )
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    elif args.cmd == "tail":
        for row in _tail(args.n, args.ledger):
            sys.stdout.write(json.dumps(row) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
