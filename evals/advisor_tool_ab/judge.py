#!/usr/bin/env python3
"""Apply the LLM judge to results produced by run_ab.py.

Takes a `results.json` (dry-run or live) and, for each row with a
`response_text`, runs the rubric through the Opus judge. Writes out a
`results_judged.json` that merges judge output alongside the original
substring-match score so we can measure judge/substring agreement and
track it over prompt iterations.

Usage:
    # Apply judge to a live run
    python evals/advisor_tool_ab/judge.py \
        --results evals/advisor_tool_ab/results_live.json \
        --cases-dir evals/advisor_tool_ab/cases \
        --out evals/advisor_tool_ab/results_judged.json

    # Dry-run (no API calls, structural sanity check)
    python evals/advisor_tool_ab/judge.py \
        --results evals/advisor_tool_ab/results.json \
        --cases-dir evals/advisor_tool_ab/cases \
        --out /tmp/results_judged.json \
        --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# scripts/ is a sibling of evals/ at the repo root
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT / "scripts"))
from llm_judge import judge_response  # type: ignore[import-not-found]


def _load_cases(cases_dir: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(cases_dir.glob("*.json")):
        case = json.loads(path.read_text())
        out[case["name"]] = case
    return out


# A generic answer-relevancy criterion, appended to every case's rubric when
# `--relevancy-axis` is set. Captured here (not per-case) so the axis is
# truly opt-in and case JSONs stay focused on case-specific criteria.
RELEVANCY_CRITERION = {
    "criterion": "answer substantively addresses the question",
    "keywords": [],  # judge is LLM-scored; keywords exist only for substring fallback
}


def judge_results(
    results: dict[str, Any],
    cases: dict[str, dict[str, Any]],
    *,
    session_id: str,
    dry_run: bool,
    relevancy_axis: bool = False,
) -> dict[str, Any]:
    """Mutate a copy of `results` with per-row judge output + arm-level agg.

    When `relevancy_axis` is True, a generic "answer substantively addresses
    the question" criterion is appended to every case's rubric before the
    judge scores it. Opt-in per-run; case files are never modified.
    """
    per_case_out: list[dict[str, Any]] = []
    for row in results["per_case"]:
        case_name = row.get("case")
        case = cases.get(case_name)
        if case is None:
            per_case_out.append({**row, "judge": {"error": f"no case def for {case_name!r}"}})
            continue

        rubric = list(case.get("rubric", []))
        if relevancy_axis:
            rubric = rubric + [RELEVANCY_CRITERION]

        judged = judge_response(
            response_text=row.get("response_text", "") or "",
            rubric=rubric,
            context=case.get("context"),
            question=case.get("question"),
            session_id=session_id,
            case_name=case_name,
            arm=row.get("arm"),
            dry_run=dry_run,
        )
        # Keep original row intact; attach judge output + agreement flag.
        substring_score = row.get("rubric_score", 0.0)
        judge_score = judged["score"]
        per_case_out.append({
            **row,
            "judge": {
                "score": judge_score,
                "per_criterion": judged["per_criterion"],
                "judge_model": judged["judge_model"],
                "cost_usd": judged["cost_usd"],
                "wall_time_s": judged["wall_time_s"],
            },
            "judge_agrees_with_substring": abs(substring_score - judge_score) < 0.01,
        })

    # Aggregate judge score per arm.
    arms = results.get("arms", [])
    judge_agg: dict[str, dict[str, float]] = {}
    for arm in arms:
        arm_rows = [r for r in per_case_out if r["arm"] == arm and "judge" in r and "score" in r["judge"]]
        n = len(arm_rows) or 1
        judge_agg[arm] = {
            "mean_judge_score": round(sum(r["judge"]["score"] for r in arm_rows) / n, 4),
            "mean_judge_cost_usd": round(sum(r["judge"].get("cost_usd", 0.0) for r in arm_rows) / n, 6),
            "total_judge_cost_usd": round(sum(r["judge"].get("cost_usd", 0.0) for r in arm_rows), 6),
        }

    # Disagreement summary: rows where substring and judge disagree materially.
    disagreements = [
        {
            "case": r["case"], "arm": r["arm"],
            "substring_score": r.get("rubric_score"),
            "judge_score": r["judge"]["score"],
        }
        for r in per_case_out
        if "judge" in r and "score" in r["judge"]
        and abs(r.get("rubric_score", 0.0) - r["judge"]["score"]) >= 0.25
    ]

    return {
        **results,
        "per_case": per_case_out,
        "judge_aggregate": judge_agg,
        "judge_disagreements": disagreements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path,
                        help="results.json produced by run_ab.py")
    parser.add_argument("--cases-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--session-id", default="advisor_ab_judge")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--relevancy-axis", action="store_true",
                        help="Append a generic answer-relevancy criterion "
                             "to every case's rubric before judging.")
    args = parser.parse_args()

    results = json.loads(args.results.read_text())
    cases = _load_cases(args.cases_dir)

    judged = judge_results(
        results, cases,
        session_id=args.session_id,
        dry_run=args.dry_run,
        relevancy_axis=args.relevancy_axis,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(judged, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
