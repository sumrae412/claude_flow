#!/usr/bin/env python3
"""Statistical analysis for multi-trial A/B eval results.

Input: a results.json produced by `run_ab.py --trials N [--judge]` — where
each (case, arm) pair has N rows tagged with `trial_index`.

Output: per-arm mean + 95% bootstrap CI on each metric, plus pairwise
comparisons between arms. A pairwise difference is "significant at 0.05"
when its 95% bootstrap CI excludes 0.

Why bootstrap CIs instead of t-tests:
  - No distributional assumption (scores can be bimodal or heavy-tailed).
  - Works identically for rubric_score, judge_score, cost_usd, latency_s.
  - Robust at small N (our trial target is 20).
  - Stdlib-only — no scipy dependency.

If we later need more power (ANOVA, mixed-effects models), CLAUDE.md's
external-library exception permits scipy. Bootstrap covers the 80% case.

CLI:
    python scripts/stat_analysis.py --results evals/advisor_tool_ab/results.json
    python scripts/stat_analysis.py --results ... --bootstrap-iters 5000 --seed 7
    python scripts/stat_analysis.py --results ... --format markdown
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Metrics we compute CIs on. Each entry is (display_name, row_key_path).
# Nested paths are dotted: "judge.score" reads row["judge"]["score"].
_METRICS: list[tuple[str, str]] = [
    ("rubric_score", "rubric_score"),
    ("judge_score", "judge.score"),
    ("cost_usd", "cost_usd"),
    ("latency_s", "latency_s"),
]


def _get(row: dict[str, Any], path: str) -> float | None:
    cur: Any = row
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    if cur is None:
        return None
    try:
        return float(cur)
    except (TypeError, ValueError):
        return None


def _samples(rows: list[dict[str, Any]], path: str) -> list[float]:
    """Extract a numeric sample list, dropping missing values."""
    return [v for v in (_get(r, path) for r in rows) if v is not None]


# ---------- Bootstrap ----------

def bootstrap_ci(
    samples: list[float],
    *,
    confidence: float = 0.95,
    iters: int = 2000,
    rng: random.Random | None = None,
) -> tuple[float, float]:
    """Percentile bootstrap CI for the mean of `samples`.

    Draws `iters` resamples (with replacement), takes the mean of each,
    returns the (lower, upper) quantile bounds.

    Returns (mean, mean) when the sample is empty or single-element — caller
    is responsible for suppressing the CI display in degenerate cases.
    """
    if len(samples) == 0:
        return (0.0, 0.0)
    if len(samples) == 1:
        return (samples[0], samples[0])
    rng = rng or random.Random(42)
    n = len(samples)
    means: list[float] = []
    for _ in range(iters):
        resample = [samples[rng.randrange(n)] for _ in range(n)]
        means.append(sum(resample) / n)
    means.sort()
    alpha = (1 - confidence) / 2
    lo_idx = max(0, int(alpha * iters))
    hi_idx = min(iters - 1, int((1 - alpha) * iters))
    return (means[lo_idx], means[hi_idx])


def bootstrap_diff_ci(
    a: list[float],
    b: list[float],
    *,
    paired: bool = True,
    confidence: float = 0.95,
    iters: int = 2000,
    rng: random.Random | None = None,
) -> tuple[float, float, float]:
    """Bootstrap CI on the difference of means (a - b).

    Paired mode (default) requires len(a) == len(b) — the i-th element of
    each list is a matched pair (same case + trial). Resamples indices so
    pairs stay together. Unpaired mode resamples independently.

    Returns (diff_of_means, lower, upper). If [lower, upper] excludes 0, the
    difference is significant at (1 - confidence).
    """
    if paired and len(a) != len(b):
        raise ValueError(f"paired bootstrap requires equal lengths, got {len(a)} vs {len(b)}")
    if not a or not b:
        return (0.0, 0.0, 0.0)

    rng = rng or random.Random(42)
    diff_means: list[float] = []

    if paired:
        n = len(a)
        for _ in range(iters):
            idxs = [rng.randrange(n) for _ in range(n)]
            diff_means.append(
                sum(a[i] - b[i] for i in idxs) / n
            )
    else:
        na, nb = len(a), len(b)
        for _ in range(iters):
            a_sample = [a[rng.randrange(na)] for _ in range(na)]
            b_sample = [b[rng.randrange(nb)] for _ in range(nb)]
            diff_means.append(
                sum(a_sample) / na - sum(b_sample) / nb
            )

    diff_means.sort()
    alpha = (1 - confidence) / 2
    lo_idx = max(0, int(alpha * iters))
    hi_idx = min(iters - 1, int((1 - alpha) * iters))
    observed_diff = sum(a) / len(a) - sum(b) / len(b)
    return (observed_diff, diff_means[lo_idx], diff_means[hi_idx])


# ---------- Analysis driver ----------

@dataclass
class ArmStats:
    arm: str
    n: int
    metrics: dict[str, dict[str, float]]  # metric -> {mean, ci_low, ci_high}


@dataclass
class PairwiseComparison:
    metric: str
    arm_a: str
    arm_b: str
    diff_of_means: float
    ci_low: float
    ci_high: float
    significant: bool  # CI excludes 0


def _paired_rows(
    per_case: list[dict[str, Any]], arm_a: str, arm_b: str, path: str,
) -> tuple[list[float], list[float]]:
    """Build paired samples for (arm_a, arm_b) keyed by (case, trial_index).

    Filters to rows where both arms have a non-null value for the metric.
    Missing pairs are dropped — a trial where one arm errored shouldn't
    bias the paired comparison.
    """
    by_key_a: dict[tuple[str, Any], float] = {}
    by_key_b: dict[tuple[str, Any], float] = {}
    for row in per_case:
        val = _get(row, path)
        if val is None:
            continue
        key = (row.get("case"), row.get("trial_index", 0))
        if row.get("arm") == arm_a:
            by_key_a[key] = val
        elif row.get("arm") == arm_b:
            by_key_b[key] = val
    keys = sorted(set(by_key_a) & set(by_key_b))
    return [by_key_a[k] for k in keys], [by_key_b[k] for k in keys]


def analyze(
    results: dict[str, Any],
    *,
    bootstrap_iters: int = 2000,
    seed: int = 42,
    confidence: float = 0.95,
) -> dict[str, Any]:
    """Compute per-arm stats + pairwise comparisons for every arm pair."""
    rng = random.Random(seed)
    arms: list[str] = results.get("arms", [])
    per_case: list[dict[str, Any]] = results.get("per_case", [])

    per_arm_stats: list[ArmStats] = []
    for arm in arms:
        arm_rows = [r for r in per_case if r.get("arm") == arm]
        metrics: dict[str, dict[str, float]] = {}
        for display, path in _METRICS:
            samples = _samples(arm_rows, path)
            if not samples:
                continue
            mean = sum(samples) / len(samples)
            lo, hi = bootstrap_ci(
                samples, confidence=confidence, iters=bootstrap_iters, rng=rng,
            )
            metrics[display] = {
                "n": len(samples),
                "mean": round(mean, 4),
                "ci_low": round(lo, 4),
                "ci_high": round(hi, 4),
            }
        per_arm_stats.append(ArmStats(arm=arm, n=len(arm_rows), metrics=metrics))

    pairwise: list[PairwiseComparison] = []
    for i, arm_a in enumerate(arms):
        for arm_b in arms[i+1:]:
            for display, path in _METRICS:
                a_samples, b_samples = _paired_rows(per_case, arm_a, arm_b, path)
                if not a_samples or not b_samples:
                    continue
                diff, lo, hi = bootstrap_diff_ci(
                    a_samples, b_samples,
                    paired=True, confidence=confidence,
                    iters=bootstrap_iters, rng=rng,
                )
                pairwise.append(PairwiseComparison(
                    metric=display,
                    arm_a=arm_a, arm_b=arm_b,
                    diff_of_means=round(diff, 4),
                    ci_low=round(lo, 4),
                    ci_high=round(hi, 4),
                    significant=(lo > 0 or hi < 0),
                ))

    return {
        "trials": results.get("trials", 1),
        "bootstrap_iters": bootstrap_iters,
        "confidence": confidence,
        "per_arm": [
            {"arm": s.arm, "n_rows": s.n, "metrics": s.metrics}
            for s in per_arm_stats
        ],
        "pairwise": [
            {
                "metric": p.metric, "arm_a": p.arm_a, "arm_b": p.arm_b,
                "diff_of_means": p.diff_of_means,
                "ci_low": p.ci_low, "ci_high": p.ci_high,
                "significant_at_alpha": round(1 - confidence, 3) if p.significant else None,
            }
            for p in pairwise
        ],
    }


# ---------- Output formatters ----------

def _format_markdown(analysis: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# A/B Eval Statistical Analysis")
    lines.append("")
    lines.append(
        f"Trials: **{analysis['trials']}** · "
        f"Bootstrap iters: **{analysis['bootstrap_iters']}** · "
        f"Confidence: **{int(analysis['confidence']*100)}%**"
    )
    lines.append("")

    lines.append("## Per-arm metrics (mean [CI])")
    lines.append("")
    lines.append("| arm | n_rows | rubric_score | judge_score | cost_usd | latency_s |")
    lines.append("|-----|--------|--------------|-------------|----------|-----------|")
    for arm in analysis["per_arm"]:
        m = arm["metrics"]
        cells = []
        for name in ("rubric_score", "judge_score", "cost_usd", "latency_s"):
            s = m.get(name)
            if s is None:
                cells.append("—")
            else:
                cells.append(f"{s['mean']:.3f} [{s['ci_low']:.3f}, {s['ci_high']:.3f}]")
        lines.append(f"| {arm['arm']} | {arm['n_rows']} | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## Pairwise comparisons (paired bootstrap on arm_a − arm_b)")
    lines.append("")
    lines.append("| metric | arm_a | arm_b | Δ mean | 95% CI | significant |")
    lines.append("|--------|-------|-------|--------|--------|-------------|")
    for p in analysis["pairwise"]:
        sig_mark = "**yes**" if p["significant_at_alpha"] is not None else "no"
        lines.append(
            f"| {p['metric']} | {p['arm_a']} | {p['arm_b']} | "
            f"{p['diff_of_means']:+.4f} | "
            f"[{p['ci_low']:+.4f}, {p['ci_high']:+.4f}] | {sig_mark} |"
        )
    lines.append("")
    return "\n".join(lines)


# ---------- CLI ----------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", required=True, type=Path,
                        help="results.json produced by run_ab.py --trials N")
    parser.add_argument("--bootstrap-iters", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--confidence", type=float, default=0.95)
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write analysis to this file instead of stdout.")
    args = parser.parse_args()

    results = json.loads(args.results.read_text())
    analysis = analyze(
        results,
        bootstrap_iters=args.bootstrap_iters,
        seed=args.seed,
        confidence=args.confidence,
    )

    out_text = (
        _format_markdown(analysis)
        if args.format == "markdown"
        else json.dumps(analysis, indent=2)
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(out_text + ("\n" if not out_text.endswith("\n") else ""))
    else:
        sys.stdout.write(out_text)
        if not out_text.endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
