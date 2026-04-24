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

# Pricing + ledger live in scripts/ (sibling of evals/). Import lazily via
# path insertion so dry-run tests still work without installing the package.
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from pricing import compute_cost as _compute_cost  # noqa: E402
from ledger import log_invocation as _log_invocation  # noqa: E402


def attribute_cost(usage: dict, model: str) -> float:
    """Compute USD cost from token usage. Delegates to shared pricing table."""
    return _compute_cost(
        model,
        usage.get("input_tokens"),
        usage.get("output_tokens"),
    )


def attribute_cost_with_iterations(
    usage_obj: Any, executor_model: str,
) -> tuple[float, dict[str, Any]]:
    """Cost including advisor sub-inference.

    Per Anthropic's advisor-tool docs: top-level input_tokens/output_tokens
    reflect executor tokens only. Advisor tokens appear in
    `usage.iterations[i]` with `type == "advisor_message"` and their own
    `model` field, billed at that model's rates.

    Returns (total_cost_usd, extras_dict). `extras_dict` carries per-role
    token counts so the ledger row preserves the breakdown.
    """
    if usage_obj is None:
        return 0.0, {}

    top_in = getattr(usage_obj, "input_tokens", None)
    top_out = getattr(usage_obj, "output_tokens", None)
    cache_read = getattr(usage_obj, "cache_read_input_tokens", None)
    cache_create = getattr(usage_obj, "cache_creation_input_tokens", None)
    executor_cost = _compute_cost(
        executor_model, top_in, top_out,
        cache_read_input_tokens=cache_read,
        cache_creation_input_tokens=cache_create,
    )

    advisor_cost = 0.0
    advisor_in = 0
    advisor_out = 0
    advisor_model = None
    iterations = getattr(usage_obj, "iterations", None) or []
    for it in iterations:
        it_type = getattr(it, "type", None) if not isinstance(it, dict) else it.get("type")
        if it_type != "advisor_message":
            continue
        it_model = getattr(it, "model", None) if not isinstance(it, dict) else it.get("model")
        it_in = getattr(it, "input_tokens", None) if not isinstance(it, dict) else it.get("input_tokens")
        it_out = getattr(it, "output_tokens", None) if not isinstance(it, dict) else it.get("output_tokens")
        advisor_model = it_model or advisor_model
        advisor_in += it_in or 0
        advisor_out += it_out or 0
        advisor_cost += _compute_cost(it_model, it_in, it_out)

    extras = {
        "executor_input_tokens": top_in,
        "executor_output_tokens": top_out,
        "executor_cache_read_input_tokens": cache_read,
        "executor_cache_creation_input_tokens": cache_create,
        "executor_cost_usd": round(executor_cost, 6),
        "advisor_input_tokens": advisor_in or None,
        "advisor_output_tokens": advisor_out or None,
        "advisor_cost_usd": round(advisor_cost, 6),
        "advisor_model": advisor_model,
    }
    return round(executor_cost + advisor_cost, 6), extras


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


def run_dry(
    cases: list[dict[str, Any]],
    trials: int = 1,
    arms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Dry-run path: emit structurally-valid synthetic results with zeroed metrics.

    Dry-run rows include `usage`, `response_text`, and `invoked_advisor` keys so
    downstream analysis written against dry-run output generalizes to live output.
    When `trials > 1`, each (case, arm) pair produces `trials` rows tagged with
    `trial_index` so stat_analysis.py can treat them as independent samples.
    """
    arms_used = arms if arms is not None else ARMS
    per_case: list[dict[str, Any]] = []
    for trial_index in range(trials):
        for case in cases:
            for arm in arms_used:
                per_case.append({
                    "case": case["name"],
                    "arm": arm,
                    "trial_index": trial_index,
                    "rubric_score": 0.0,
                    "cost_usd": 0.0,
                    "latency_s": 0.0,
                    "usage": None,
                    "response_text": "",
                    "invoked_advisor": False,
                    "dry_run": True,
                })
    return per_case


def run_live_case(
    case: dict[str, Any],
    arm: str,
    prompts_dir: Path,
    session_id: str = "advisor_ab",
) -> dict[str, Any]:
    """Live-eval path — DEFERRED scaffolding, not exercised in CI.

    This function is intentionally not imported at module scope. The
    `anthropic` SDK is lazily imported inside so that `--dry-run` works
    without the SDK installed.
    """
    # Live eval deferred — scaffolding only, see README.md
    from anthropic import Anthropic  # noqa: F401  (lazy import)

    client = Anthropic()
    prompt_template = load_prompt(prompts_dir, arm)
    prompt = prompt_template.format(context=case["context"], question=case["question"])

    model = MODEL_OPUS if arm == "opus_solo" else MODEL_SONNET
    tools: list[dict[str, Any]] = []
    betas: list[str] = []
    if arm == "sonnet_advisor_tool":
        # Server-side advisor tool — shape per
        # https://docs.anthropic.com/en/docs/build-with-claude/tool-use/advisor-tool
        tools = [{
            "type": ADVISOR_TOOL_NAME,
            "name": "advisor",
            "model": MODEL_OPUS,
            "max_uses": 2,
        }]
        betas = ["advisor-tool-2026-03-01"]

    # Prompt caching NOT wired here. Attempted in 2026-04-24 Step 2 but every
    # arm's cacheable prefix (system preamble ± tool schema) sat under
    # Anthropic's 1024-token minimum, so cache_control silently no-ops. Kept
    # the cache field extraction + pricing math intact so the wiring flips on
    # cleanly once prompts grow past that threshold — just add cache_control
    # breakpoints back to `system` / `messages`.
    create_kwargs: dict[str, Any] = {
        "model": model,
        "max_tokens": 2048,
        "messages": [{"role": "user", "content": prompt}],
    }
    if tools:
        create_kwargs["tools"] = tools
    if betas:
        create_kwargs["betas"] = betas

    t0 = time.monotonic()
    success = True
    error: str | None = None
    resp = None
    try:
        # Advisor tool requires the beta endpoint (docs: client.beta.messages.create
        # with betas=[...]). Other arms also go through beta.messages.create for
        # a single code path — it's a no-op superset of messages.create.
        resp = client.beta.messages.create(**create_kwargs)
    except Exception as e:
        success = False
        error = f"{type(e).__name__}: {e}"
    latency_s = time.monotonic() - t0

    # Extract text content + detect advisor invocation.
    # Per advisor-tool docs, a successful advisor call produces:
    #   { type: "server_tool_use", name: "advisor", input: {} }
    # followed by:
    #   { type: "advisor_tool_result", tool_use_id: ..., content: ... }
    # Both signals are checked — matching either confirms the tool fired.
    response_text = ""
    invoked_advisor = False
    usage_dict = {
        "input_tokens": None, "output_tokens": None,
        "cache_read_input_tokens": None, "cache_creation_input_tokens": None,
    }
    advisor_cost_breakdown: dict[str, Any] = {}
    if resp is not None:
        for block in getattr(resp, "content", []):
            btype = getattr(block, "type", None)
            if btype == "text":
                response_text += getattr(block, "text", "")
            elif btype == "server_tool_use" and getattr(block, "name", None) == "advisor":
                invoked_advisor = True
            elif btype == "advisor_tool_result":
                invoked_advisor = True
        usage = getattr(resp, "usage", None)
        usage_dict = {
            "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
            "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", None) if usage else None,
            "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", None) if usage else None,
        }
        # Cost attribution that correctly separates executor + advisor tokens.
        cost_usd, advisor_cost_breakdown = attribute_cost_with_iterations(usage, model)
    else:
        cost_usd = 0.0

    rubric_score = score_rubric(response_text, case.get("rubric", [])) if success else 0.0

    # Log to the shared invocation ledger — one row per API call, including
    # failures. Downstream ROI math groups on (caller, arm, model).
    _log_invocation(
        caller="advisor_ab",
        model=model,
        wall_time_s=latency_s,
        input_tokens=usage_dict["input_tokens"],
        output_tokens=usage_dict["output_tokens"],
        success=success,
        error=error,
        session_id=session_id,
        arm=arm,
        case=case["name"],
        score=rubric_score if success else None,
        extras={"invoked_advisor": invoked_advisor, **advisor_cost_breakdown},
        cost_usd=cost_usd,
    )

    return {
        "case": case["name"],
        "arm": arm,
        "rubric_score": rubric_score,
        "cost_usd": cost_usd,
        "latency_s": latency_s,
        "usage": usage_dict,
        "response_text": response_text,
        "invoked_advisor": invoked_advisor,
        "success": success,
        "error": error,
        "dry_run": False,
    }


def run_live(
    cases: list[dict[str, Any]],
    prompts_dir: Path,
    session_id: str = "advisor_ab",
    trials: int = 1,
    arms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Live-eval driver — DEFERRED.

    `trials > 1` runs each (case, arm) pair `trials` times. Each row is
    tagged with `trial_index` so stat_analysis.py can compute bootstrap CIs
    and paired comparisons across trials.
    """
    arms_used = arms if arms is not None else ARMS
    per_case: list[dict[str, Any]] = []
    for trial_index in range(trials):
        for case in cases:
            for arm in arms_used:
                row = run_live_case(case, arm, prompts_dir, session_id=session_id)
                row["trial_index"] = trial_index
                per_case.append(row)
    return per_case


def aggregate(
    per_case: list[dict[str, Any]],
    arms: list[str] | None = None,
) -> dict[str, dict[str, float]]:
    arms_used = arms if arms is not None else ARMS
    agg: dict[str, dict[str, float]] = {}
    for arm in arms_used:
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
    parser.add_argument("--session-id", default="advisor_ab",
                        help="Correlation id written into ledger rows.")
    parser.add_argument("--judge", action="store_true",
                        help="Run the LLM-as-judge pass inline after A/B; "
                             "writes results enriched with per-row judge "
                             "verdicts + agreement aggregates.")
    parser.add_argument("--trials", type=int, default=1,
                        help="Run each (case, arm) this many times. Each row "
                             "gets a trial_index for downstream stat_analysis.py.")
    parser.add_argument("--relevancy-axis", action="store_true",
                        help="When --judge is set, append a generic "
                             "answer-relevancy criterion to every rubric.")
    parser.add_argument("--arms", default=None,
                        help="Comma-separated subset of arms to run "
                             "(default: all three). Must be a subset of ARMS.")
    args = parser.parse_args()

    if args.trials < 1:
        raise SystemExit("--trials must be >= 1")

    if args.arms:
        arms_used = [a.strip() for a in args.arms.split(",") if a.strip()]
        unknown = [a for a in arms_used if a not in ARMS]
        if unknown:
            raise SystemExit(f"Unknown arm(s): {unknown}. Known: {ARMS}")
    else:
        arms_used = list(ARMS)

    cases = load_cases(args.cases_dir)
    if not cases:
        raise SystemExit(f"No cases found under {args.cases_dir}")

    prompts_dir = Path(__file__).parent / "prompts"

    if args.dry_run:
        per_case = run_dry(cases, trials=args.trials, arms=arms_used)
    else:
        # Live eval deferred — scaffolding only, see README.md
        per_case = run_live(cases, prompts_dir, session_id=args.session_id, trials=args.trials, arms=arms_used)

    result: dict[str, Any] = {
        "arms": arms_used,
        "per_case": per_case,
        "aggregate": aggregate(per_case, arms=arms_used),
        "trials": args.trials,
        "dry_run": args.dry_run,
    }

    # Inline judge pass — replaces the separate `python judge.py` invocation
    # when --judge is set. Keeps a single command for the common case while
    # leaving judge.py importable for ad-hoc re-grading of a saved results.json.
    if args.judge:
        from judge import judge_results  # type: ignore[import-not-found]
        cases_by_name = {c["name"]: c for c in cases}
        result = judge_results(
            result,
            cases_by_name,
            session_id=args.session_id,
            dry_run=args.dry_run,
            relevancy_axis=args.relevancy_axis,
        )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
