#!/usr/bin/env python3
"""Statistical evaluation framework for prompt variants and reviewer calibration.

Adds confidence intervals, behavioral consistency, and regression detection
to the prompt-optimization pipeline. Inspired by agent-evaluation patterns
(antigravity-awesome-skills, Apache 2.0).

Usage:
  stat-eval.py confidence <agent_type> [category]   # CI for variant scores
  stat-eval.py consistency <agent_type> [category]   # Behavioral consistency
  stat-eval.py regression <agent_type> <variant_id>  # Regression vs baseline
  stat-eval.py calibrate <reviewer_name>             # Judge calibration check
  stat-eval.py flakiness <agent_type> [category]     # Flaky test detection
"""
from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

# Reuse prompt-tracker's data loading
sys.path.insert(0, str(Path(__file__).parent))
from importlib import import_module

# Import prompt-tracker functions without running its __main__
pt = import_module("prompt-tracker")


# ---------------------------------------------------------------------------
# Statistical primitives
# ---------------------------------------------------------------------------

def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def std_dev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = mean(values)
    return math.sqrt(sum((x - m) ** 2 for x in values) / (len(values) - 1))


def confidence_interval_95(values: list[float]) -> tuple[float, float]:
    """Normal approximation 95% CI for continuous scores in [0, 1]."""
    n = len(values)
    if n == 0:
        return (0.0, 0.0)
    m = mean(values)
    z = 1.96  # 95% confidence
    se = std_dev(values) / math.sqrt(n)
    return (max(0.0, m - z * se), min(1.0, m + z * se))


def pass_rate_ci(passes: int, total: int) -> tuple[float, float]:
    """Wilson score interval for pass rate (better for small samples than normal approx)."""
    if total == 0:
        return (0.0, 0.0)
    z = 1.96
    p_hat = passes / total
    denom = 1 + z * z / total
    center = (p_hat + z * z / (2 * total)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * total)) / total) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard index: |intersection| / |union|."""
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    return len(set_a & set_b) / len(union) if union else 0.0


def chi_squared_2x2(observed_a: tuple[int, int], observed_b: tuple[int, int]) -> float:
    """Chi-squared test for 2x2 contingency table. Returns p-value approximation.

    observed_a = (pass_a, fail_a)
    observed_b = (pass_b, fail_b)
    """
    a, b = observed_a
    c, d = observed_b
    n = a + b + c + d
    if n == 0:
        return 1.0

    # Expected values
    r1, r2 = a + b, c + d
    c1, c2 = a + c, b + d

    expected = [
        (r1 * c1 / n, r1 * c2 / n),
        (r2 * c1 / n, r2 * c2 / n),
    ]
    observed = [(a, b), (c, d)]

    chi2 = 0.0
    for i in range(2):
        for j in range(2):
            e = expected[i][j]
            if e > 0:
                chi2 += (observed[i][j] - e) ** 2 / e

    # Approximate p-value for 1 df using chi-squared survival function
    # Piecewise linear interpolation between critical values for 1 df
    if chi2 <= 0:
        return 1.0
    # Critical values for 1 df: (chi2, p-value)
    table = [
        (0.455, 0.50),
        (1.323, 0.25),
        (2.706, 0.10),
        (3.841, 0.05),
        (5.024, 0.025),
        (6.635, 0.01),
        (7.879, 0.005),
        (10.828, 0.001),
    ]
    if chi2 >= table[-1][0]:
        return table[-1][1]
    # Linear interpolation between bracketing entries
    for i in range(len(table) - 1):
        if chi2 <= table[i + 1][0]:
            x0, y0 = table[i]
            x1, y1 = table[i + 1]
            # Interpolate in log-p space for better accuracy
            if chi2 <= x0:
                return y0
            t = (chi2 - x0) / (x1 - x0)
            log_p = math.log(y0) + t * (math.log(y1) - math.log(y0))
            return math.exp(log_p)
    return 0.5


# ---------------------------------------------------------------------------
# Confidence interval analysis
# ---------------------------------------------------------------------------

def analyze_variant_confidence(agent_type: str, category: str = "") -> list[dict]:
    """Compute confidence intervals for all variants of an agent type."""
    events = pt.load_events(agent_type)
    data = pt.load_variants()

    # Group events by variant
    by_variant: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        vid = ev.get("variant_id", "")
        by_variant[vid].append(ev)

    results = []
    score_key = {"explorer": "f1", "architect": "score", "reviewer": "score"}.get(agent_type, "score")

    categories = [category] if category else sorted(data.get(agent_type, {}).keys())
    for cat in categories:
        cat_data = data.get(agent_type, {}).get(cat, {})
        for variant in cat_data.get("variants", []):
            vid = variant["id"]
            variant_events = by_variant.get(vid, [])
            if not variant_events:
                continue

            scores = [ev.get(score_key, 0.0) for ev in variant_events]
            ci = confidence_interval_95(scores)
            n = len(scores)

            results.append({
                "variant_id": vid,
                "category": cat,
                "agent_type": agent_type,
                "role": variant.get("role", ""),
                "active": variant.get("active", False),
                "sessions": n,
                "mean_score": round(mean(scores), 3),
                "std_dev": round(std_dev(scores), 3),
                "ci_95_lower": round(ci[0], 3),
                "ci_95_upper": round(ci[1], 3),
                "sufficient_data": n >= 10,
                "concern": "high_variance" if std_dev(scores) > 0.3 else None,
            })

    return results


# ---------------------------------------------------------------------------
# Behavioral consistency (Jaccard)
# ---------------------------------------------------------------------------

def analyze_behavioral_consistency(agent_type: str, category: str = "") -> list[dict]:
    """Measure how consistently a variant produces the same behaviors across runs.

    For explorers: consistency of files found across sessions.
    For reviewers: consistency of issue categories found.
    For architects: consistency of proposal structure.
    """
    events = pt.load_events(agent_type)

    by_variant: dict[str, list[dict]] = defaultdict(list)
    for ev in events:
        vid = ev.get("variant_id", "")
        cat = ev.get("task_category", "")
        if category and cat != category:
            continue
        by_variant[vid].append(ev)

    results = []
    for vid, variant_events in by_variant.items():
        if len(variant_events) < 2:
            results.append({
                "variant_id": vid,
                "consistency": 1.0,
                "sessions": len(variant_events),
                "note": "insufficient data (need 2+ sessions)",
            })
            continue

        # Extract behavior sets based on agent type
        behavior_sets = []
        for ev in variant_events:
            if agent_type == "explorer":
                behaviors = set(ev.get("files_found", []))
            elif agent_type == "reviewer":
                # Bucket counts into ranges to avoid Jaccard over-sensitivity
                # (exact count differences like 5 vs 6 shouldn't tank consistency)
                def _bucket(n: int) -> str:
                    if n == 0: return "0"
                    if n <= 3: return "1-3"
                    if n <= 7: return "4-7"
                    return "8+"
                issues = ev.get("issues_found", 0)
                fixed = ev.get("issues_fixed", 0)
                fps = ev.get("false_positives", 0)
                tpr = ev.get("true_positive_rate", 0)
                behaviors = {
                    f"found:{_bucket(issues)}",
                    f"fixed:{_bucket(fixed)}",
                    f"fps:{_bucket(fps)}",
                    f"tpr:{'high' if tpr > 0.7 else 'low'}",
                }
            else:
                behaviors = {f"score:{ev.get('score', 0):.1f}"}
            behavior_sets.append(behaviors)

        # Pairwise Jaccard similarity
        total_sim = 0.0
        comparisons = 0
        for i in range(len(behavior_sets)):
            for j in range(i + 1, len(behavior_sets)):
                total_sim += jaccard_similarity(behavior_sets[i], behavior_sets[j])
                comparisons += 1

        consistency = total_sim / comparisons if comparisons > 0 else 1.0

        concern = None
        if consistency < 0.5:
            concern = "critical_inconsistency"
        elif consistency < 0.7:
            concern = "unstable_behavior"

        results.append({
            "variant_id": vid,
            "consistency": round(consistency, 3),
            "sessions": len(variant_events),
            "comparisons": comparisons,
            "concern": concern,
        })

    return results


# ---------------------------------------------------------------------------
# Regression detection
# ---------------------------------------------------------------------------

def detect_regression(
    agent_type: str,
    variant_id: str,
    baseline_sessions: int = 0,
) -> dict:
    """Compare recent performance against baseline (first N sessions).

    If baseline_sessions=0, splits events 50/50.
    """
    events = pt.load_events(agent_type)
    variant_events = [ev for ev in events if ev.get("variant_id") == variant_id]

    if len(variant_events) < 6:
        return {"error": "Need at least 6 sessions for regression detection", "sessions": len(variant_events)}

    score_key = {"explorer": "f1", "architect": "score", "reviewer": "score"}.get(agent_type, "score")

    # Split into baseline and current
    if baseline_sessions <= 0:
        split = len(variant_events) // 2
    else:
        split = min(baseline_sessions, len(variant_events) - 3)

    baseline = variant_events[:split]
    current = variant_events[split:]

    baseline_scores = [ev.get(score_key, 0.0) for ev in baseline]
    current_scores = [ev.get(score_key, 0.0) for ev in current]

    # Use a threshold to convert to pass/fail for chi-squared
    threshold = mean(baseline_scores) * 0.8  # 80% of baseline mean
    baseline_pass = sum(1 for s in baseline_scores if s >= threshold)
    baseline_fail = len(baseline_scores) - baseline_pass
    current_pass = sum(1 for s in current_scores if s >= threshold)
    current_fail = len(current_scores) - current_pass

    p_value = chi_squared_2x2(
        (baseline_pass, baseline_fail),
        (current_pass, current_fail),
    )

    baseline_mean = mean(baseline_scores)
    current_mean = mean(current_scores)
    degradation = current_mean < baseline_mean * 0.95  # 5% tolerance

    return {
        "variant_id": variant_id,
        "agent_type": agent_type,
        "baseline_sessions": len(baseline),
        "current_sessions": len(current),
        "baseline_mean": round(baseline_mean, 3),
        "current_mean": round(current_mean, 3),
        "baseline_ci": [round(x, 3) for x in confidence_interval_95(baseline_scores)],
        "current_ci": [round(x, 3) for x in confidence_interval_95(current_scores)],
        "p_value": p_value,
        "significant_degradation": degradation and p_value < 0.05,
        "recommendation": (
            "REGRESSION DETECTED: significant performance drop"
            if degradation and p_value < 0.05
            else "OK: no significant regression"
        ),
    }


# ---------------------------------------------------------------------------
# Flakiness analysis
# ---------------------------------------------------------------------------

def analyze_flakiness(agent_type: str, category: str = "") -> list[dict]:
    """Identify flaky variants — those with high score variance indicating unreliable behavior."""
    events = pt.load_events(agent_type)
    score_key = {"explorer": "f1", "architect": "score", "reviewer": "score"}.get(agent_type, "score")

    by_variant: dict[str, list[float]] = defaultdict(list)
    for ev in events:
        cat = ev.get("task_category", "")
        if category and cat != category:
            continue
        vid = ev.get("variant_id", "")
        by_variant[vid].append(ev.get(score_key, 0.0))

    results = []
    for vid, scores in by_variant.items():
        if len(scores) < 3:
            continue

        sd = std_dev(scores)
        m = mean(scores)

        # Flakiness = transitions between pass/fail relative to median
        median = sorted(scores)[len(scores) // 2]
        above = [s >= median for s in scores]
        transitions = sum(1 for i in range(1, len(above)) if above[i] != above[i - 1])
        flakiness = transitions / (len(scores) - 1) if len(scores) > 1 else 0.0

        if flakiness > 0.6:
            recommendation = "Highly flaky — investigate prompt stability"
        elif flakiness > 0.3:
            recommendation = "Moderately flaky — run more sessions before promoting"
        elif sd > 0.25:
            recommendation = "High variance — consider narrowing prompt scope"
        else:
            recommendation = "Stable"

        results.append({
            "variant_id": vid,
            "sessions": len(scores),
            "mean_score": round(m, 3),
            "std_dev": round(sd, 3),
            "flakiness": round(flakiness, 3),
            "recommendation": recommendation,
        })

    return sorted(results, key=lambda r: r["flakiness"], reverse=True)


# ---------------------------------------------------------------------------
# Reviewer calibration
# ---------------------------------------------------------------------------

def check_calibration(reviewer_name: str) -> dict:
    """Check reviewer calibration against human-labeled ground truth.

    Reads calibration config from reviewer-registry.json and compares
    against labeled findings in reviewer event log.
    """
    registry_path = pt.CLAUDE_FLOW_DIR / "reviewer-registry.json"
    if not registry_path.exists():
        return {"error": f"No reviewer-registry.json at {registry_path}"}

    registry = json.loads(registry_path.read_text())
    reviewer = None
    for r in registry.get("reviewers", []):
        if r.get("name") == reviewer_name or r.get("id") == reviewer_name:
            reviewer = r
            break

    if not reviewer:
        return {"error": f"Reviewer '{reviewer_name}' not found in registry"}

    cal = reviewer.get("calibration", {})
    min_agreement = cal.get("min_agreement", registry.get("judge_calibration", {}).get("fallback_min_agreement", 0.75))

    # Load reviewer events and check for human-labeled verdicts
    events = pt.load_events("reviewer")
    reviewer_events = [
        ev for ev in events
        if ev.get("variant_id", "").startswith(reviewer_name)
        or ev.get("reviewer_name") == reviewer_name
    ]

    labeled = [ev for ev in reviewer_events if ev.get("human_verdict") is not None]

    if not labeled:
        return {
            "reviewer": reviewer_name,
            "status": "uncalibrated",
            "min_agreement": min_agreement,
            "labeled_samples": 0,
            "recommendation": "Need human-labeled findings to calibrate. Label at least 20 recent findings.",
        }

    agreements = sum(
        1 for ev in labeled
        if ev.get("human_verdict") == (ev.get("issues_found", 0) > 0)
    )
    agreement_rate = agreements / len(labeled)

    return {
        "reviewer": reviewer_name,
        "status": "calibrated",
        "agreement_rate": round(agreement_rate, 3),
        "min_agreement": min_agreement,
        "labeled_samples": len(labeled),
        "passing": agreement_rate >= min_agreement,
        "ci_95": [round(x, 3) for x in pass_rate_ci(agreements, len(labeled))],
        "recommendation": (
            f"BELOW THRESHOLD: agreement {agreement_rate:.1%} < {min_agreement:.0%}. Revise prompt or demote tier."
            if agreement_rate < min_agreement
            else f"OK: agreement {agreement_rate:.1%} >= {min_agreement:.0%}"
        ),
    }


# ---------------------------------------------------------------------------
# Upgraded promotion check (replaces raw F1 gap)
# ---------------------------------------------------------------------------

def should_promote(agent_type: str, category: str) -> list[dict]:
    """Determine promotions using CI-aware comparison instead of raw score gap.

    A variant wins only if its CI lower bound exceeds the other's CI upper bound,
    OR if both have 10+ sessions and the gap is significant (p < 0.05).
    """
    ci_results = analyze_variant_confidence(agent_type, category)
    if len(ci_results) < 2:
        return [{"note": "Need at least 2 variants for comparison"}]

    # Group by role
    by_role: dict[str, list[dict]] = defaultdict(list)
    for r in ci_results:
        by_role[r.get("role", "")].append(r)

    promotions = []
    for role, variants in by_role.items():
        active = [v for v in variants if v.get("active")]
        if len(active) < 2:
            continue

        # Sort by mean score descending
        active.sort(key=lambda v: v["mean_score"], reverse=True)
        best = active[0]
        challenger = active[1]

        # CI-based dominance: best's lower bound > challenger's upper bound
        ci_dominant = best["ci_95_lower"] > challenger["ci_95_upper"]

        # Significance test
        score_key = {"explorer": "f1", "architect": "score", "reviewer": "score"}.get(agent_type, "score")
        all_events = pt.load_events(agent_type)
        best_scores = [ev.get(score_key, 0) for ev in all_events if ev.get("variant_id") == best["variant_id"]]
        chal_scores = [ev.get(score_key, 0) for ev in all_events if ev.get("variant_id") == challenger["variant_id"]]

        threshold = mean(best_scores + chal_scores) * 0.5
        best_pass = sum(1 for s in best_scores if s >= threshold)
        chal_pass = sum(1 for s in chal_scores if s >= threshold)
        p_value = chi_squared_2x2(
            (best_pass, len(best_scores) - best_pass),
            (chal_pass, len(chal_scores) - chal_pass),
        )

        statistically_significant = ci_dominant or (
            best["sufficient_data"] and challenger["sufficient_data"]
            and p_value < 0.05 and best["mean_score"] > challenger["mean_score"]
        )

        # Enforce consistency/flakiness blockers (SKILL.md Step 3)
        blocker = None
        if statistically_significant:
            consistency_results = analyze_behavioral_consistency(agent_type, category)
            consistency_by_vid = {r["variant_id"]: r.get("consistency", 1.0) for r in consistency_results}
            winner_consistency = consistency_by_vid.get(best["variant_id"], 1.0)
            if winner_consistency < 0.5:
                blocker = f"Winner consistency {winner_consistency:.2f} < 0.5 (unstable)"

            flakiness_results = analyze_flakiness(agent_type, category)
            flakiness_by_vid = {r["variant_id"]: r.get("flakiness", 0.0) for r in flakiness_results}
            winner_flakiness = flakiness_by_vid.get(best["variant_id"], 0.0)
            if winner_flakiness > 0.6:
                blocker = f"Winner flakiness {winner_flakiness:.2f} > 0.6 (unreliable)"

        should = statistically_significant and blocker is None

        promotions.append({
            "role": role,
            "category": category,
            "winner": best["variant_id"],
            "loser": challenger["variant_id"],
            "winner_mean": best["mean_score"],
            "loser_mean": challenger["mean_score"],
            "winner_ci": [best["ci_95_lower"], best["ci_95_upper"]],
            "loser_ci": [challenger["ci_95_lower"], challenger["ci_95_upper"]],
            "ci_dominant": ci_dominant,
            "p_value": p_value,
            "should_promote": should,
            "blocker": blocker,
            "reason": (
                f"BLOCKED: {blocker}" if blocker
                else "CI lower bound exceeds challenger upper bound" if ci_dominant
                else f"Significant difference (p={p_value:.4f})" if should
                else "Not enough evidence for promotion"
            ),
        })

    return promotions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "confidence":
        agent_type = sys.argv[2] if len(sys.argv) > 2 else "explorer"
        category = sys.argv[3] if len(sys.argv) > 3 else ""
        results = analyze_variant_confidence(agent_type, category)
        print(json.dumps(results, indent=2))

    elif cmd == "consistency":
        agent_type = sys.argv[2] if len(sys.argv) > 2 else "explorer"
        category = sys.argv[3] if len(sys.argv) > 3 else ""
        results = analyze_behavioral_consistency(agent_type, category)
        print(json.dumps(results, indent=2))

    elif cmd == "regression":
        if len(sys.argv) < 4:
            print("Usage: stat-eval.py regression <agent_type> <variant_id> [baseline_sessions]")
            sys.exit(1)
        agent_type = sys.argv[2]
        variant_id = sys.argv[3]
        baseline = int(sys.argv[4]) if len(sys.argv) > 4 else 0
        result = detect_regression(agent_type, variant_id, baseline)
        print(json.dumps(result, indent=2))

    elif cmd == "calibrate":
        if len(sys.argv) < 3:
            print("Usage: stat-eval.py calibrate <reviewer_name>")
            sys.exit(1)
        result = check_calibration(sys.argv[2])
        print(json.dumps(result, indent=2))

    elif cmd == "flakiness":
        agent_type = sys.argv[2] if len(sys.argv) > 2 else "explorer"
        category = sys.argv[3] if len(sys.argv) > 3 else ""
        results = analyze_flakiness(agent_type, category)
        print(json.dumps(results, indent=2))

    elif cmd == "promote":
        if len(sys.argv) < 4:
            print("Usage: stat-eval.py promote <agent_type> <category>")
            sys.exit(1)
        results = should_promote(sys.argv[2], sys.argv[3])
        print(json.dumps(results, indent=2))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
