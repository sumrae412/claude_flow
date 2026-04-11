#!/usr/bin/env python3
"""Prompt optimization tracker — records outcomes and computes scores for any agent type.

Supports explorer, architect, and reviewer agent types. Each has its own
variant pool, metrics, and scoring model.

Usage:
  # Select a variant for a session
  prompt-tracker.py select <agent_type> <category> <role>

  # Record outcome event
  prompt-tracker.py record <json-payload>

  # Update variant metrics from events
  prompt-tracker.py update-metrics

  # Show variant comparison table
  prompt-tracker.py report [agent_type] [category]
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
VARIANTS_FILE = CLAUDE_FLOW_DIR / "memory" / "procedural" / "prompt-variants.json"

# Per-agent-type event files
EVENTS_FILES = {
    "explorer": CLAUDE_FLOW_DIR / "memory" / "episodic" / "exploration-events.jsonl",
    "architect": CLAUDE_FLOW_DIR / "memory" / "episodic" / "architect-events.jsonl",
    "reviewer": CLAUDE_FLOW_DIR / "memory" / "episodic" / "reviewer-events.jsonl",
}

# Backward compat alias
EVENTS_FILE = EVENTS_FILES["explorer"]

VALID_AGENT_TYPES = {"explorer", "architect", "reviewer"}

EPSILON = 0.2  # exploration rate for epsilon-greedy


def load_variants() -> dict:
    if VARIANTS_FILE.exists():
        return json.loads(VARIANTS_FILE.read_text())
    return {"schema_version": 1, "explorer": {}}


def save_variants(data: dict) -> None:
    VARIANTS_FILE.write_text(json.dumps(data, indent=2) + "\n")


def events_file_for(agent_type: str) -> Path:
    return EVENTS_FILES.get(agent_type, EVENTS_FILES["explorer"])


def append_event(event: dict, agent_type: str = "explorer") -> None:
    event["ts"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event["agent_type"] = agent_type
    path = events_file_for(agent_type)
    with open(path, "a") as f:
        f.write(json.dumps(event) + "\n")


def load_events(agent_type: str = "explorer") -> list[dict]:
    path = events_file_for(agent_type)
    if not path.exists():
        return []
    events = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def load_all_events() -> list[dict]:
    """Load events across all agent types."""
    all_events = []
    for agent_type in VALID_AGENT_TYPES:
        all_events.extend(load_events(agent_type))
    return all_events


# ---------------------------------------------------------------------------
# Variant selection (epsilon-greedy)
# ---------------------------------------------------------------------------

def select_variant(agent_type: str, category: str, role: str) -> dict:
    """Select a prompt variant using epsilon-greedy strategy.

    agent_type: explorer, architect, or reviewer
    """
    data = load_variants()
    cat_data = data.get(agent_type, {}).get(category)
    if not cat_data:
        return {"error": f"No variants for {agent_type}/{category}"}

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

    # Primary score metric differs per agent type
    primary_metric = {
        "explorer": "f1_sum",
        "architect": "score_sum",
        "reviewer": "score_sum",
    }.get(agent_type, "f1_sum")

    # Epsilon-greedy: exploit best 80%, explore random 20%
    if random.random() < EPSILON:
        chosen = random.choice(active)
    else:
        def avg_score(v):
            s = v["metrics"]["sessions"]
            return v["metrics"].get(primary_metric, 0) / s if s > 0 else 0.0
        chosen = max(active, key=avg_score)

    return {"variant_id": chosen["id"], "prompt": chosen["prompt"]}


# ---------------------------------------------------------------------------
# Score computation
# ---------------------------------------------------------------------------

def compute_explorer_scores(
    files_found: list[str],
    files_used_in_impl: list[str],
    phase5_retries: int = 0,
    
) -> dict:
    """Compute precision, recall, F1, and final score for explorer prompts."""
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


# Backward compat alias
compute_scores = compute_explorer_scores


def compute_architect_scores(
    refinement_rounds: int = 0,
    review_issues_critical: int = 0,
    review_issues_total: int = 0,
    
    user_chose_this: bool = True,
) -> dict:
    """Compute score for architect prompts.

    Metrics:
    - selection_rate: was this architect's proposal chosen by the user?
    - convergence: fewer refinement rounds = better initial architecture
    - quality: fewer critical review issues in Phase 6 = better design
    - score: weighted combination
    """
    # Selection: binary — was this variant's proposal chosen?
    selection = 1.0 if user_chose_this else 0.0

    # Convergence: inversely proportional to refinement rounds (0-3 scale)
    convergence = max(0.0, 1.0 - (refinement_rounds / 3.0))

    # Quality: penalize critical issues, lightly penalize total
    critical_penalty = min(review_issues_critical * 0.15, 0.6)
    total_penalty = min(review_issues_total * 0.02, 0.3)
    quality = max(0.0, 1.0 - critical_penalty - total_penalty)

    # Weighted score: selection matters most, then quality, then convergence
    score = (selection * 0.4) + (quality * 0.35) + (convergence * 0.25)

    return {
        "selection": round(selection, 3),
        "convergence": round(convergence, 3),
        "quality": round(quality, 3),
        "score": round(score, 3),
        "refinement_rounds": refinement_rounds,
        "review_issues_critical": review_issues_critical,
        "review_issues_total": review_issues_total,
    }


def compute_reviewer_scores(
    issues_found: int = 0,
    issues_fixed: int = 0,
    issues_dismissed: int = 0,
    false_positives: int = 0,
) -> dict:
    """Compute score for reviewer prompts.

    Metrics:
    - true_positive_rate: issues that were actually fixed / total found
    - signal_to_noise: (found - false_positives) / found
    - score: true_positive_rate * signal_to_noise
    """
    total = issues_found if issues_found > 0 else 1

    true_positive_rate = min(issues_fixed / total, 1.0)
    signal_to_noise = max(0.0, min((issues_found - false_positives) / total, 1.0))

    score = true_positive_rate * signal_to_noise

    return {
        "true_positive_rate": round(true_positive_rate, 3),
        "signal_to_noise": round(signal_to_noise, 3),
        "score": round(score, 3),
        "issues_found": issues_found,
        "issues_fixed": issues_fixed,
        "issues_dismissed": issues_dismissed,
        "false_positives": false_positives,
    }


# ---------------------------------------------------------------------------
# Record an exploration event
# ---------------------------------------------------------------------------

def record_event(payload: dict) -> dict:
    """Record an outcome event for any agent type and return computed scores."""
    agent_type = payload.get("agent_type", "explorer")

    if agent_type == "architect":
        scores = compute_architect_scores(
            refinement_rounds=payload.get("refinement_rounds", 0),
            review_issues_critical=payload.get("review_issues_critical", 0),
            review_issues_total=payload.get("review_issues_total", 0),
            user_chose_this=payload.get("user_chose_this", True),
        )
        event = {
            "session_id": payload.get("session_id", "unknown"),
            "task_category": payload.get("task_category", "general"),
            "variant_id": payload.get("variant_id", "unknown"),
            "role": payload.get("role", "simplicity"),
            **scores,
        }

    elif agent_type == "reviewer":
        scores = compute_reviewer_scores(
            issues_found=payload.get("issues_found", 0),
            issues_fixed=payload.get("issues_fixed", 0),
            issues_dismissed=payload.get("issues_dismissed", 0),
            false_positives=payload.get("false_positives", 0),
        )
        event = {
            "session_id": payload.get("session_id", "unknown"),
            "task_category": payload.get("task_category", "general"),
            "variant_id": payload.get("variant_id", "unknown"),
            "role": payload.get("role", "overshoot"),
            **scores,
        }

    else:
        # Explorer (default)
        files_found = payload.get("files_found", [])
        files_used = payload.get("files_used_in_impl", [])
        retries = payload.get("phase5_retries", 0)
        plan_steps = payload.get("plan_steps", 1)
        scores = compute_explorer_scores(files_found, files_used, retries, plan_steps)
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

    append_event(event, agent_type)
    return event


# ---------------------------------------------------------------------------
# Update variant metrics from events
# ---------------------------------------------------------------------------

def _update_explorer_metrics(variant: dict, variant_events: list[dict]) -> None:
    m = variant["metrics"]
    m["sessions"] = len(variant_events)
    m["total_files_found"] = sum(ev.get("files_found_count", len(ev.get("files_found", []))) for ev in variant_events)
    m["total_overlap_files"] = sum(len(set(ev.get("files_used_in_impl", [])) & set(ev.get("files_found", []))) for ev in variant_events)
    m["total_files_needed"] = sum(len(ev.get("files_used_in_impl", [])) for ev in variant_events)
    m["total_retries"] = sum(ev.get("phase5_retries", 0) for ev in variant_events)
    m["precision_sum"] = round(sum(ev.get("precision", 0) for ev in variant_events), 3)
    m["recall_sum"] = round(sum(ev.get("recall", 0) for ev in variant_events), 3)
    m["f1_sum"] = round(sum(ev.get("f1", 0) for ev in variant_events), 3)

    # Per-domain retry rates for thinking-budget auto-tuning
    from collections import defaultdict
    domain_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "retries": 0})
    for ev in variant_events:
        dom = ev.get("domain")
        if not dom:
            continue
        domain_stats[dom]["attempts"] += 1
        domain_stats[dom]["retries"] += ev.get("phase5_retries", 0)
    m["retry_rates_by_domain"] = {
        dom: {
            "attempts": s["attempts"],
            "retries": s["retries"],
            "rate": round(s["retries"] / s["attempts"], 3) if s["attempts"] else 0.0,
        }
        for dom, s in domain_stats.items()
    }


def _update_architect_metrics(variant: dict, variant_events: list[dict]) -> None:
    m = variant["metrics"]
    m["sessions"] = len(variant_events)
    m["selection_sum"] = round(sum(ev.get("selection", 0) for ev in variant_events), 3)
    m["convergence_sum"] = round(sum(ev.get("convergence", 0) for ev in variant_events), 3)
    m["quality_sum"] = round(sum(ev.get("quality", 0) for ev in variant_events), 3)
    m["score_sum"] = round(sum(ev.get("score", 0) for ev in variant_events), 3)


def _update_reviewer_metrics(variant: dict, variant_events: list[dict]) -> None:
    m = variant["metrics"]
    m["sessions"] = len(variant_events)
    m["total_issues_found"] = sum(ev.get("issues_found", 0) for ev in variant_events)
    m["total_issues_fixed"] = sum(ev.get("issues_fixed", 0) for ev in variant_events)
    m["total_false_positives"] = sum(ev.get("false_positives", 0) for ev in variant_events)
    m["tpr_sum"] = round(sum(ev.get("true_positive_rate", 0) for ev in variant_events), 3)
    m["stn_sum"] = round(sum(ev.get("signal_to_noise", 0) for ev in variant_events), 3)
    m["score_sum"] = round(sum(ev.get("score", 0) for ev in variant_events), 3)


_METRIC_UPDATERS = {
    "explorer": _update_explorer_metrics,
    "architect": _update_architect_metrics,
    "reviewer": _update_reviewer_metrics,
}


def update_metrics() -> dict:
    """Recompute variant metrics from all events across all agent types."""
    data = load_variants()
    total_updated = 0
    total_events = 0

    for agent_type in VALID_AGENT_TYPES:
        events = load_events(agent_type)
        total_events += len(events)

        event_map: dict[str, list[dict]] = {}
        for ev in events:
            vid = ev.get("variant_id", "")
            event_map.setdefault(vid, []).append(ev)

        updater = _METRIC_UPDATERS.get(agent_type, _update_explorer_metrics)

        for category, cat_data in data.get(agent_type, {}).items():
            for variant in cat_data.get("variants", []):
                vid = variant["id"]
                variant_events = event_map.get(vid, [])
                if not variant_events:
                    continue
                updater(variant, variant_events)
                total_updated += 1

    save_variants(data)
    return {"updated_variants": total_updated, "total_events": total_events}


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def _report_explorer(data: dict, category: str = "") -> list[str]:
    lines = ["## Explorer Variants", ""]
    categories = [category] if category else sorted(data.get("explorer", {}).keys())

    for cat in categories:
        cat_data = data.get("explorer", {}).get(cat)
        if not cat_data:
            continue

        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| Variant | Role | Sessions | Avg Precision | Avg Recall | Avg F1 | Status |")
        lines.append("|---------|------|----------|---------------|------------|--------|--------|")

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
    events = load_events("explorer")
    if events:
        missed_files: dict[str, int] = {}
        for ev in events:
            for f in ev.get("files_needed_not_found", []):
                missed_files[f] = missed_files.get(f, 0) + 1
        if missed_files:
            lines.append("### Most Commonly Missed Files")
            lines.append("")
            for f, count in sorted(missed_files.items(), key=lambda x: -x[1])[:10]:
                lines.append(f"- **{f}** ({count} misses)")
            lines.append("")

    return lines


def _report_architect(data: dict, category: str = "") -> list[str]:
    lines = ["## Architect Variants", ""]
    categories = [category] if category else sorted(data.get("architect", {}).keys())

    for cat in categories:
        cat_data = data.get("architect", {}).get(cat)
        if not cat_data:
            continue

        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| Variant | Role | Sessions | Avg Selection | Avg Quality | Avg Score | Status |")
        lines.append("|---------|------|----------|---------------|-------------|-----------|--------|")

        for v in sorted(cat_data["variants"], key=lambda x: x["role"]):
            m = v["metrics"]
            s = m.get("sessions", 0)
            avg_sel = round(m.get("selection_sum", 0) / s, 2) if s > 0 else 0
            avg_q = round(m.get("quality_sum", 0) / s, 2) if s > 0 else 0
            avg_score = round(m.get("score_sum", 0) / s, 2) if s > 0 else 0
            status = "active" if v["active"] else "retired"
            if v["id"] == cat_data.get("current_best"):
                status = "winner"
            lines.append(f"| {v['id']} | {v['role']} | {s} | {avg_sel} | {avg_q} | {avg_score} | {status} |")
        lines.append("")

    return lines


def _report_reviewer(data: dict, category: str = "") -> list[str]:
    lines = ["## Reviewer Variants", ""]
    categories = [category] if category else sorted(data.get("reviewer", {}).keys())

    for cat in categories:
        cat_data = data.get("reviewer", {}).get(cat)
        if not cat_data:
            continue

        lines.append(f"### {cat}")
        lines.append("")
        lines.append("| Variant | Role | Sessions | Avg TPR | Avg S/N | Avg Score | Status |")
        lines.append("|---------|------|----------|---------|---------|-----------|--------|")

        for v in sorted(cat_data["variants"], key=lambda x: x["role"]):
            m = v["metrics"]
            s = m.get("sessions", 0)
            avg_tpr = round(m.get("tpr_sum", 0) / s, 2) if s > 0 else 0
            avg_stn = round(m.get("stn_sum", 0) / s, 2) if s > 0 else 0
            avg_score = round(m.get("score_sum", 0) / s, 2) if s > 0 else 0
            status = "active" if v["active"] else "retired"
            if v["id"] == cat_data.get("current_best"):
                status = "winner"
            lines.append(f"| {v['id']} | {v['role']} | {s} | {avg_tpr} | {avg_stn} | {avg_score} | {status} |")
        lines.append("")

    return lines


def report(agent_type: str = "", category: str = "") -> str:
    """Generate a comparison report for variants."""
    data = load_variants()
    lines = ["# Prompt Variant Performance Report", ""]

    types_to_report = [agent_type] if agent_type else sorted(VALID_AGENT_TYPES)

    for at in types_to_report:
        if at == "explorer":
            lines.extend(_report_explorer(data, category))
        elif at == "architect":
            lines.extend(_report_architect(data, category))
        elif at == "reviewer":
            lines.extend(_report_reviewer(data, category))

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
        if len(sys.argv) < 5:
            print("Usage: prompt-tracker.py select <agent_type> <category> <role>")
            print(f"  agent_type: {', '.join(sorted(VALID_AGENT_TYPES))}")
            sys.exit(1)
        if sys.argv[2] not in VALID_AGENT_TYPES:
            print(f"Error: agent_type must be one of {sorted(VALID_AGENT_TYPES)}")
            print(f"  Got: '{sys.argv[2]}'")
            print("  Hint: the CLI changed — agent_type is now required as the first arg")
            sys.exit(1)
        result = select_variant(sys.argv[2], sys.argv[3], sys.argv[4])
        print(json.dumps(result, indent=2))

    elif cmd == "record":
        if len(sys.argv) < 3:
            print("Usage: prompt-tracker.py record <json-payload>")
            print('  payload must include "agent_type" (default: explorer)')
            sys.exit(1)
        payload = json.loads(sys.argv[2])
        result = record_event(payload)
        print(json.dumps(result, indent=2))

    elif cmd == "update-metrics":
        result = update_metrics()
        print(json.dumps(result, indent=2))

    elif cmd == "report":
        agent_type = sys.argv[2] if len(sys.argv) > 2 else ""
        cat = sys.argv[3] if len(sys.argv) > 3 else ""
        print(report(agent_type, cat))

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
