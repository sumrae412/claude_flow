#!/usr/bin/env python3
"""Per-case + critical-miss analysis for the 2026-04-24 sonnet-vs-opus eval.

Throwaway — committed as-is for decision doc reproducibility, not as reusable lib.
"""
import json
import sys
from collections import defaultdict
from statistics import mean, stdev


def analyze(path: str, label: str) -> None:
    d = json.load(open(path))
    rows = d["per_case"]

    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    crit_fails: dict[str, dict[str, dict[str, int]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(int))
    )
    crit_total: dict[str, int] = defaultdict(int)
    for r in rows:
        key = (r["case"], r["arm"])
        j = r.get("judge", {})
        if j.get("score") is not None:
            groups[key].append(j["score"])
        for c in j.get("per_criterion", []):
            if not c.get("passed"):
                crit_fails[r["case"]][r["arm"]][c["criterion"]] += 1
            crit_total[c["criterion"]] += 1

    print(f"\n=== {label} — Per (case, arm) judge scores ===")
    cases = sorted(set(r["case"] for r in rows))
    for case in cases:
        print(f"\n{case}:")
        for arm in ["sonnet_solo", "opus_solo"]:
            scores = groups[(case, arm)]
            if scores:
                m = mean(scores)
                s = stdev(scores) if len(scores) > 1 else 0.0
                print(
                    f"  {arm:13s} mean={m:.3f} stdev={s:.3f} "
                    f"min={min(scores):.2f} max={max(scores):.2f} n={len(scores)}"
                )

    print(f"\n=== {label} — Critical-miss check (Sonnet missed >=50% of trials) ===")
    for case in cases:
        sonnet_fails = crit_fails[case].get("sonnet_solo", {})
        opus_fails = crit_fails[case].get("opus_solo", {})
        for crit, n_miss in sorted(sonnet_fails.items(), key=lambda kv: -kv[1]):
            if n_miss >= 8:
                opus_miss = opus_fails.get(crit, 0)
                print(
                    f"  {case:42s} Sonnet miss {n_miss}/15 | "
                    f"Opus miss {opus_miss}/15 | {crit[:70]}"
                )


if __name__ == "__main__":
    for path, label in zip(sys.argv[1::2], sys.argv[2::2]):
        analyze(path, label)
