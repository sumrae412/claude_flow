"""Tests for evals/advisor_tool_ab/judge.py — A/B judge runner wrapper."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_judge_dry_run_over_synthetic_results(tmp_path):
    """End-to-end dry run: generate results via run_ab.py --dry-run,
    then apply judge.py --dry-run. The output must contain judge fields
    on every row plus arm-level aggregates."""
    eval_dir = Path(__file__).parent

    # 1. Generate dry-run results.
    results_path = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(eval_dir / "run_ab.py"),
         "--cases-dir", str(eval_dir / "cases"),
         "--out", str(results_path),
         "--dry-run"],
        check=True,
    )

    # 2. Apply the judge (dry-run — no API call).
    judged_path = tmp_path / "results_judged.json"
    subprocess.run(
        [sys.executable, str(eval_dir / "judge.py"),
         "--results", str(results_path),
         "--cases-dir", str(eval_dir / "cases"),
         "--out", str(judged_path),
         "--dry-run"],
        check=True,
    )

    data = json.loads(judged_path.read_text())

    # Every row gets a judge block.
    for row in data["per_case"]:
        assert "judge" in row, f"row {row['case']}/{row['arm']} missing judge"
        assert "score" in row["judge"]
        assert "per_criterion" in row["judge"]
        # Dry-run judge: all criteria failed → score 0.0.
        assert row["judge"]["score"] == 0.0

    # Arm-level aggregate present for each arm.
    assert set(data["judge_aggregate"].keys()) == set(data["arms"])
    for arm, agg in data["judge_aggregate"].items():
        assert "mean_judge_score" in agg
        assert "mean_judge_cost_usd" in agg

    # Disagreements list: exists, may be empty (dry-run → substring=0, judge=0).
    assert isinstance(data["judge_disagreements"], list)


def test_relevancy_axis_appends_criterion_to_every_rubric(tmp_path):
    """--relevancy-axis adds an extra per_criterion entry to every row's
    judge output. Case JSONs stay unchanged on disk."""
    eval_dir = Path(__file__).parent
    results_path = tmp_path / "results.json"
    subprocess.run(
        [sys.executable, str(eval_dir / "run_ab.py"),
         "--cases-dir", str(eval_dir / "cases"),
         "--out", str(results_path),
         "--dry-run"],
        check=True,
    )

    judged_path = tmp_path / "results_judged.json"
    subprocess.run(
        [sys.executable, str(eval_dir / "judge.py"),
         "--results", str(results_path),
         "--cases-dir", str(eval_dir / "cases"),
         "--out", str(judged_path),
         "--dry-run", "--relevancy-axis"],
        check=True,
    )

    data = json.loads(judged_path.read_text())
    for row in data["per_case"]:
        assert "judge" in row
        criteria = [c["criterion"] for c in row["judge"]["per_criterion"]]
        assert any("substantively addresses" in c for c in criteria), (
            f"relevancy axis missing from row {row['case']}/{row['arm']}: {criteria}"
        )
