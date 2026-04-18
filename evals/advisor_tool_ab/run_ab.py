"""
Advisor-Tool A/B eval runner — 3-arm.

Arms:
  * sonnet_solo            — Sonnet with no extra tools.
  * sonnet_advisor_tool    — Sonnet with Anthropic's server-side
                             `advisor_20260301` tool available.
  * opus_solo              — Opus with no extra tools (control: "does the
                             advisor tool close the gap to Opus?").

Status: DRY-RUN SCAFFOLDING ONLY. The live path below is untested scaffolding;
the live eval is deferred. See README.md for how to run it when ready.

Usage:
  # Dry run — no network, no anthropic import, deterministic synthetic output.
  python run_ab.py --cases-dir cases/ --out results.json --dry-run

  # Live run — DEFERRED. Requires ANTHROPIC_API_KEY and `pip install anthropic`.
  python run_ab.py --cases-dir cases/ --out results.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ARMS = ["sonnet_solo", "sonnet_advisor_tool", "opus_solo"]

# Model IDs used by the live path. Kept as module-level constants so the
# dry-run output documents intent even when no API call is made.
# Source of truth: https://docs.anthropic.com/en/docs/about-claude/models — refresh before live run
MODEL_SONNET = "claude-sonnet-4-6"
MODEL_OPUS = "claude-opus-4-7"
ADVISOR_TOOL_NAME = "advisor_20260301"

# Pricing snapshot as of 2026-04-17 — refresh before live run.
# Values are USD per million tokens; source: Anthropic pricing page.
PRICING: dict[str, dict[str, float]] = {
    MODEL_SONNET: {"input": 0.0, "output": 0.0},  # TODO: populate
    MODEL_OPUS: {"input": 0.0, "output": 0.0},    # TODO: populate
}


def attribute_cost(usage: dict, model: str) -> float:
    """Compute USD cost from token usage. TODO: populate PRICING."""
    rates = PRICING.get(model, {"input": 0.0, "output": 0.0})
    if rates["input"] == 0.0 and rates["output"] == 0.0:
        return 0.0  # Pricing not yet populated — returns 0 to avoid misleading totals
    in_tokens = usage.get("input_tokens", 0) or 0
    out_tokens = usage.get("output_tokens", 0) or 0
    return (in_tokens * rates["input"] + out_tokens * rates["output"]) / 1_000_000


# Module-level flag so the advisor-arm warning only prints once per run.
_ADVISOR_WARNED = False


def load_cases(cases_dir: Path) -> list[dict[str, Any]]:
    cases = []
    for case_path in sorted(cases_dir.glob("*.json")):
        cases.append(json.loads(case_path.read_text()))
    return cases


def load_prompt(prompts_dir: Path, arm: str) -> str:
    # opus_solo reuses the sonnet_solo prompt template (control arm — same
    # prompt, different model).
    filename_map = {
        "sonnet_solo": "sonnet_solo.txt",
        "opus_solo": "sonnet_solo.txt",
        "sonnet_advisor_tool": "sonnet_with_advisor_tool.txt",
    }
    return (prompts_dir / filename_map[arm]).read_text()


def score_rubric(response_text: str, rubric: list[dict[str, Any]]) -> float:
    """Substring-match scorer.

    Each rubric item must be a dict `{"criterion": str, "keywords": list[str]}`;
    a criterion passes if any keyword appears in the response (case-insensitive).
    Score is the fraction of criteria that pass.

    Raises ValueError on malformed (e.g. string-shaped) rubric items so a future
    session doesn't get silent zeros.
    """
    if not rubric:
        return 0.0
    lowered = response_text.lower()
    hits = 0
    for item in rubric:
        if not isinstance(item, dict) or "keywords" not in item:
            raise ValueError(
                f"Rubric item must be a dict with 'keywords' key, got: {item!r}"
            )
        keywords = [kw.lower() for kw in item["keywords"]]
        if any(kw in lowered for kw in keywords):
            hits += 1
    return hits / len(rubric)


def run_dry(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dry-run path: emit structurally-valid synthetic results with zeroed metrics.

    Dry-run rows include `usage`, `response_text`, and `invoked_advisor` keys so
    downstream analysis written against dry-run output generalizes to live output.
    """
    per_case: list[dict[str, Any]] = []
    for case in cases:
        for arm in ARMS:
            per_case.append({
                "case": case["name"],
                "arm": arm,
                "rubric_score": 0.0,
                "cost_usd": 0.0,
                "latency_s": 0.0,
                "usage": None,
                "response_text": "",
                "invoked_advisor": False,
                "dry_run": True,
            })
    return per_case


def run_live_case(case: dict[str, Any], arm: str, prompts_dir: Path) -> dict[str, Any]:
    """Live-eval path — DEFERRED scaffolding, not exercised in CI.

    This function is intentionally not imported at module scope. The
    `anthropic` SDK is lazily imported inside so that `--dry-run` works
    without the SDK installed.
    """
    # Live eval deferred — scaffolding only, see README.md
    from anthropic import Anthropic  # noqa: F401  (lazy import)

    global _ADVISOR_WARNED

    client = Anthropic()
    prompt_template = load_prompt(prompts_dir, arm)
    prompt = prompt_template.format(context=case["context"], question=case["question"])

    model = MODEL_OPUS if arm == "opus_solo" else MODEL_SONNET
    tools: list[dict[str, Any]] = []
    extra_headers: dict[str, str] = {}
    if arm == "sonnet_advisor_tool":
        # Server-side advisor tool — shape is a best-effort placeholder;
        # verify against current Anthropic docs before interpreting results.
        tools = [{
            "type": ADVISOR_TOOL_NAME,
            "name": "advisor",
            "model": MODEL_OPUS,
            "max_uses": 2,
        }]
        extra_headers = {"anthropic-beta": "advisor-tool-2026-03-01"}
        if not _ADVISOR_WARNED:
            print(
                "WARN: advisor_20260301 tool shape is a best-effort placeholder — "
                "verify against current Anthropic docs before interpreting results",
                file=sys.stderr,
            )
            _ADVISOR_WARNED = True

    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if tools:
        create_kwargs["tools"] = tools
    if extra_headers:
        create_kwargs["extra_headers"] = extra_headers

    t0 = time.monotonic()
    resp = client.messages.create(**create_kwargs)
    latency_s = time.monotonic() - t0

    # Extract text content from the response. The Anthropic SDK returns a list
    # of content blocks; we concatenate any text blocks. Also scan for advisor
    # tool invocations so we can record whether the tool actually fired.
    response_text = ""
    invoked_advisor = False
    for block in getattr(resp, "content", []):
        btype = getattr(block, "type", None)
        if btype == "text":
            response_text += getattr(block, "text", "")
        elif btype == ADVISOR_TOOL_NAME:
            invoked_advisor = True
        elif btype == "tool_use" and getattr(block, "name", None) == "advisor":
            invoked_advisor = True

    # Cost attribution: the live path records usage and computes a USD cost
    # via the PRICING table (returns 0.0 until populated).
    usage = getattr(resp, "usage", None)
    usage_dict = {
        "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
        "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
    }
    cost_usd = attribute_cost(usage_dict, model)

    return {
        "case": case["name"],
        "arm": arm,
        "rubric_score": score_rubric(response_text, case.get("rubric", [])),
        "cost_usd": cost_usd,
        "latency_s": latency_s,
        "usage": usage_dict,
        "response_text": response_text,
        "invoked_advisor": invoked_advisor,
        "dry_run": False,
    }


def run_live(cases: list[dict[str, Any]], prompts_dir: Path) -> list[dict[str, Any]]:
    """Live-eval driver — DEFERRED."""
    per_case: list[dict[str, Any]] = []
    for case in cases:
        for arm in ARMS:
            per_case.append(run_live_case(case, arm, prompts_dir))
    return per_case


def aggregate(per_case: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    agg: dict[str, dict[str, float]] = {}
    for arm in ARMS:
        arm_rows = [r for r in per_case if r["arm"] == arm]
        n = len(arm_rows) or 1
        agg[arm] = {
            "mean_rubric": sum(r["rubric_score"] for r in arm_rows) / n,
            "mean_cost_usd": sum(r["cost_usd"] for r in arm_rows) / n,
            "mean_latency_s": sum(r["latency_s"] for r in arm_rows) / n,
        }
    return agg


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true",
                        help="Emit synthetic zeroed results; no API calls.")
    args = parser.parse_args()

    cases = load_cases(args.cases_dir)
    if not cases:
        raise SystemExit(f"No cases found under {args.cases_dir}")

    prompts_dir = Path(__file__).parent / "prompts"

    if args.dry_run:
        per_case = run_dry(cases)
    else:
        # Live eval deferred — scaffolding only, see README.md
        per_case = run_live(cases, prompts_dir)

    result = {
        "arms": ARMS,
        "per_case": per_case,
        "aggregate": aggregate(per_case),
        "dry_run": args.dry_run,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
