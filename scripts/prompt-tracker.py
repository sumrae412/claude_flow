#!/usr/bin/env python3
"""Prompt optimization tracker — records exploration outcomes and computes scores.

Usage:
  # Select a variant for a session
  prompt-tracker.py select <category> <role>

  # Record exploration outcome
  prompt-tracker.py record <json-payload>

  # Update variant metrics from exploration events
  prompt-tracker.py update-metrics

  # Show variant comparison table
  prompt-tracker.py report [category]
"""

import json
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

CLAUDE_FLOW_DIR = Path(os.environ.get(
    "CLAUDE_FLOW_DIR",
    Path(__file__).resolve().parent.parent,
))
VARIANTS_FILE = CLAUDE_FLOW_DIR / "memory" / "prompt-variants.json"
EVENTS_FILE = CLAUDE_FLOW_DIR / "memory" / "exploration-events.jsonl"

EPSILON = 0.2  # exploration rate for epsilon-greedy


def load_variants() -> dict:
    if VARIANTS_FILE.exists():
        return json.loads(VARIANTS_FILE.read_text())
    return {"schema_version": 1, "explorer": {}}


def save_variants(data: dict) -> None:
    VARIANTS_FILE.write_text(json.dumps(data, indent=2) + "\n")


def append_event(event: dict) -> None:
    event["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(EVENTS_FILE, "a") as f:
        f.write(json.dumps(event) + "\n")


def load_events() -> list[dict]:
    if not EVENTS_FILE.exists():
        return []
    events = []
    for line in EVENTS_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


# ---------------------------------------------------------------------------
# Variant selection (epsilon-greedy)
# ---------------------------------------------------------------------------

def select_variant(category: str, role: str) -> dict:
    """Select a prompt variant using epsilon-greedy strategy."""
    data = load_variants()
    cat_data = data.get("explorer", {}).get(category)
    if not cat_data:
        return {"error": f"No variants for category '{category}'"}

    active = [v for v in cat_data["variants"] if v.get("active") and v.get("role") == role]
    if not active:
        return {"error": f"No active variants for {category}/{role}"}

    if len(active) == 1:
        return {"variant_id": active[0]["id"], "prompt": active[0]["prompt"]}

    min_sessions = cat_data.get("min_sessions", 10)

    # If any variant has fewer than min_sessions, round-robin
    under_threshold = [v for v in active if v["metrics"]["sessions"] < min_sessions]
    if under_threshold:
        # Pick the one with fewest sessions
        chosen = min(under_threshold, key=lambda v: v["metrics"]["sessions"])
        return {"variant_id": chosen["id"], "prompt": chosen["prompt"]}

    # Epsilon-greedy: exploit best 80%, explore random 20%
    if random.random() < EPSILON:
        chosen = random.choice(active)
    else:
        # Pick variant with highest avg F1
        def avg_f1(v):
            s = v["metrics"]["sessions"]
            return v["metrics"]["f1_sum"] / s if s > 0 else 0.0
        chosen = max(active, key=avg_f1)

    return {"variant_id": chosen["id"], "prompt": chosen["prompt"]}


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------

def compute_scores(
    files_found: list[str],
    files_used_in_impl: list[str],
    phase5_retries: int = 0,
    plan_steps: int = 1,
) -> dict:
    """Compute precision, recall, F1, and final score."""
    found_set = set(files_found)
    used_set = set(files_used_in_impl)
    overlap = found_set & used_set
    missed = used_set - found_set

    precision = len(overlap) / len(found_set) if found_set else 0.0
    recall = len(overlap) / len(used_set) if used_set else 0.0

    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    retry_rate = min(phase5_retries / max(plan_steps, 1), 1.0)
    score = f1 * (1.0 - retry_rate)

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "score": round(score, 3),
        "files_found_count": len(found_set),
        "files_used_count": len(used_set),
        "overlap_count": len(overlap),
        "missed_count": len(missed),
        "missed_files": sorted(missed),
    }


# ---------------------------------------------------------------------------
# Record an exploration event
# ---------------------------------------------------------------------------

def record_event(payload: dict) -> dict:
    """Record an exploration event and return computed scores."""
    files_found = payload.get("files_found", [])
    files_used = payload.get("files_used_in_impl", [])
    retries = payload.get("phase5_retries", 0)
    plan_steps = payload.get("plan_steps", 1)

    scores = compute_scores(files_found, files_used, retries, plan_steps)

    event = {
        "session_id": payload.get("session_id", "unknown"),
        "task_category": payload.get("task_category", "general"),
        "variant_id": payload.get("variant_id", "unknown"),
        "explorer_role": payload.get("explorer_role", "A"),
        "files_found": files_found,
        "files_used_in_impl": files_used,
        "files_needed_not_found": scores["missed_files"],
        "precision": scores["precision"],
        "recall": scores["recall"],
        "f1": scores["f1"],
        "phase5_retries": retries,
        "score": scores["score"],
    }
    append_event(event)
    return event


# ---------------------------------------------------------------------------
# Update variant metrics from events
# ---------------------------------------------------------------------------

def update_metrics() -> dict:
    """Recompute variant metrics from all events."""
    data = load_variants()
    events = load_events()

    # Build a lookup: variant_id -> list of events
    event_map: dict[str, list[dict]] = {}
    for ev in events:
        vid = ev.get("variant_id", "")
        event_map.setdefault(vid, []).append(ev)

    updated = 0
    for category, cat_data in data.get("explorer", {}).items():
        for variant in cat_data.get("variants", []):
            vid = variant["id"]
            variant_events = event_map.get(vid, [])
            if not variant_events:
                continue

            m = variant["metrics"]
            m["sessions"] = len(variant_events)
            m["total_files_found"] = sum(ev.get("files_found_count", len(ev.get("files_found", []))) for ev in variant_events)
            m["total_files_used"] = sum(len(set(ev.get("files_used_in_impl", [])) & set(ev.get("files_found", []))) for ev in variant_events)
            m["total_files_needed"] = sum(len(ev.get("files_used_in_impl", [])) for ev in variant_events)
            m["total_retries"] = sum(ev.get("phase5_retries", 0) for ev in variant_events)
            m["precision_sum"] = round(sum(ev.get("precision", 0) for ev in variant_events), 3)
            m["recall_sum"] = round(sum(ev.get("recall", 0) for ev in variant_events), 3)
            m["f1_sum"] = round(sum(ev.get("f1", 0) for ev in variant_events), 3)
            updated += 1

    save_variants(data)
    return {"updated_variants": updated, "total_events": len(events)}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def report(category: str = "") -> str:
    """Generate a comparison report for variants."""
    data = load_variants()
    lines = ["# Prompt Variant Performance Report", ""]

    categories = [category] if category else sorted(data.get("explorer", {}).keys())

    for cat in categories:
        cat_data = data.get("explorer", {}).get(cat)
        if not cat_data:
            continue

        lines.append(f"## {cat}")
        lines.append("")
        lines.append(f"| Variant | Role | Sessions | Avg Precision | Avg Recall | Avg F1 | Status |")
        lines.append(f"|---------|------|----------|---------------|------------|--------|--------|")

        for v in sorted(cat_data["variants"], key=lambda x: x["role"]):
            m = v["metrics"]
            s = m["sessions"]
            avg_p = round(m["precision_sum"] / s, 2) if s > 0 else 0
            avg_r = round(m["recall_sum"] / s, 2) if s > 0 else 0
            avg_f1 = round(m["f1_sum"] / s, 2) if s > 0 else 0
            status = "active" if v["active"] else "retired"
            best_a = cat_data.get("current_best_A")
            best_b = cat_data.get("current_best_B")
            if v["id"] in (best_a, best_b):
                status = "winner"
            lines.append(f"| {v['id']} | {v['role']} | {s} | {avg_p} | {avg_r} | {avg_f1} | {status} |")

        lines.append("")

    # Miss pattern analysis
    events = load_events()
    if events:
        missed_files: dict[str, int] = {}
        for ev in events:
            for f in ev.get("files_needed_not_found", []):
                missed_files[f] = missed_files.get(f, 0) + 1

        if missed_files:
            lines.append("## Most Commonly Missed Files")
            lines.append("")
            for f, count in sorted(missed_files.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"- **{f}** ({count} misses)")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "select":
        if len(sys.argv) < 4:
            print("Usage: prompt-tracker.py select <category> <role>")
            sys.exit(1)
        result = select_variant(sys.argv[2], sys.argv[3])
        print(json.dumps(result, indent=2))

    elif cmd == "record":
        if len(sys.argv) < 3:
            print("Usage: prompt-tracker.py record <json-payload>")
            sys.exit(1)
        payload = json.loads(sys.argv[2])
        result = record_event(payload)
        print(json.dumps(result, indent=2))

    elif cmd == "update-metrics":
        result = update_metrics()
        print(json.dumps(result, indent=2))

    elif cmd == "report":
        cat = sys.argv[2] if len(sys.argv) > 2 else ""
        print(report(cat))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
