"""Tests for scripts/stat_analysis.py — bootstrap CIs + paired comparisons."""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from stat_analysis import (  # noqa: E402
    analyze,
    bootstrap_ci,
    bootstrap_diff_ci,
)


# --- bootstrap_ci ---

def test_bootstrap_ci_empty_returns_zero():
    assert bootstrap_ci([]) == (0.0, 0.0)


def test_bootstrap_ci_single_sample_is_constant():
    lo, hi = bootstrap_ci([3.14])
    assert lo == 3.14 == hi


def test_bootstrap_ci_contains_mean_of_tight_sample():
    samples = [5.0] * 10 + [5.1, 4.9]
    lo, hi = bootstrap_ci(samples, iters=500, rng=random.Random(1))
    mean = sum(samples) / len(samples)
    assert lo <= mean <= hi
    assert (hi - lo) < 0.2  # tight sample → tight CI


def test_bootstrap_ci_is_wider_on_noisy_sample():
    tight = [5.0] * 20
    noisy = [0.0, 1.0, 5.0, 9.0, 10.0] * 4
    lo_t, hi_t = bootstrap_ci(tight, iters=500, rng=random.Random(1))
    lo_n, hi_n = bootstrap_ci(noisy, iters=500, rng=random.Random(1))
    assert (hi_n - lo_n) > (hi_t - lo_t)


# --- bootstrap_diff_ci ---

def test_bootstrap_diff_ci_no_difference_ci_contains_zero():
    rng = random.Random(0)
    a = [rng.gauss(5, 1) for _ in range(30)]
    b = [rng.gauss(5, 1) for _ in range(30)]
    diff, lo, hi = bootstrap_diff_ci(a, b, iters=500, rng=random.Random(1))
    assert lo <= 0 <= hi  # no real difference → CI straddles zero


def test_bootstrap_diff_ci_large_difference_ci_excludes_zero():
    # Arm A clearly scores higher than arm B on every paired trial.
    a = [0.9] * 20
    b = [0.4] * 20
    diff, lo, hi = bootstrap_diff_ci(a, b, iters=500, rng=random.Random(1))
    assert diff == 0.5
    assert lo > 0, f"expected CI excludes 0, got [{lo}, {hi}]"
    assert hi > 0


def test_bootstrap_diff_ci_paired_requires_equal_lengths():
    import pytest as _pytest
    with _pytest.raises(ValueError, match="equal lengths"):
        bootstrap_diff_ci([1.0, 2.0], [1.0], paired=True)


# --- analyze ---

def _synthetic_results(trials: int = 5, arms=None, score_means=None) -> dict:
    """Synthesize a run_ab.py-shaped results dict for 2 arms × 3 cases × N trials.

    `score_means` is a dict arm -> mean rubric_score; rows get score_means[arm]
    with small gaussian jitter so the bootstrap has something to work with.
    """
    arms = arms or ["arm_a", "arm_b"]
    score_means = score_means or {"arm_a": 0.75, "arm_b": 0.50}
    cases = ["case_1", "case_2", "case_3"]
    rng = random.Random(7)
    per_case = []
    for trial_index in range(trials):
        for case in cases:
            for arm in arms:
                jitter = rng.gauss(0, 0.05)
                per_case.append({
                    "case": case,
                    "arm": arm,
                    "trial_index": trial_index,
                    "rubric_score": max(0.0, min(1.0, score_means[arm] + jitter)),
                    "cost_usd": 0.01 if arm == "arm_a" else 0.10,
                    "latency_s": 1.0,
                })
    return {"arms": arms, "per_case": per_case, "trials": trials}


def test_analyze_emits_per_arm_stats_and_pairwise():
    results = _synthetic_results(trials=10)
    out = analyze(results, bootstrap_iters=300, seed=1)
    assert len(out["per_arm"]) == 2
    arm_a = next(a for a in out["per_arm"] if a["arm"] == "arm_a")
    assert "rubric_score" in arm_a["metrics"]
    # arm_a mean should be close to 0.75 with trials=10, 3 cases → 30 rows.
    assert 0.65 < arm_a["metrics"]["rubric_score"]["mean"] < 0.85
    # Exactly one pairwise entry per metric (2 arms → one pair).
    pair_metrics = [p["metric"] for p in out["pairwise"]]
    assert "rubric_score" in pair_metrics


def test_analyze_flags_significant_difference():
    # arm_a at 0.75, arm_b at 0.50 → 0.25 mean gap over 30 paired trials with
    # stdev 0.05 → CI on the diff should clearly exclude zero.
    results = _synthetic_results(trials=10)
    out = analyze(results, bootstrap_iters=500, seed=1)
    rubric_pair = [p for p in out["pairwise"] if p["metric"] == "rubric_score"][0]
    assert rubric_pair["diff_of_means"] > 0.15
    assert rubric_pair["significant_at_alpha"] is not None


def test_analyze_does_not_flag_noise_as_significant():
    # Same mean for both arms → paired diff CI should contain 0.
    results = _synthetic_results(trials=10, score_means={"arm_a": 0.6, "arm_b": 0.6})
    out = analyze(results, bootstrap_iters=500, seed=1)
    rubric_pair = [p for p in out["pairwise"] if p["metric"] == "rubric_score"][0]
    assert rubric_pair["significant_at_alpha"] is None


# --- CLI ---

def test_stat_analysis_cli_markdown_output(tmp_path):
    results = _synthetic_results(trials=5)
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(results))

    script = Path(__file__).resolve().parents[1] / "scripts" / "stat_analysis.py"
    out_path = tmp_path / "analysis.md"
    subprocess.run(
        [sys.executable, str(script),
         "--results", str(results_path),
         "--format", "markdown",
         "--out", str(out_path),
         "--bootstrap-iters", "200"],
        check=True,
    )
    text = out_path.read_text()
    assert "A/B Eval Statistical Analysis" in text
    assert "arm_a" in text and "arm_b" in text
    assert "Pairwise comparisons" in text


def test_stat_analysis_cli_json_default_to_stdout(tmp_path):
    results = _synthetic_results(trials=3)
    results_path = tmp_path / "results.json"
    results_path.write_text(json.dumps(results))

    script = Path(__file__).resolve().parents[1] / "scripts" / "stat_analysis.py"
    proc = subprocess.run(
        [sys.executable, str(script),
         "--results", str(results_path),
         "--bootstrap-iters", "100"],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(proc.stdout)
    assert "per_arm" in data and "pairwise" in data
