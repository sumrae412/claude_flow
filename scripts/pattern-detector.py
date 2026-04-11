#!/usr/bin/env python3
"""Pattern detector — scans event files for recurring patterns and queues proposals.

Emits proposals to memory/procedural/proposed-skill-updates.jsonl for manual review.
Never auto-applies.

Triggers:
  - repeated_failure: same error_class ≥3 times across ≥3 sessions
  - high_retry_domain: domain with >50% retry rate over ≥5 attempts
  - dead_pattern: pattern cited in skill with 0 matching events in 30+ days

Skipped in v1: repeated_correction (requires parsing session-learnings output).
"""
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(os.environ.get(
    "CLAUDE_FLOW_DIR",
    Path(__file__).resolve().parent.parent,
))
FAILURE_EVENTS = REPO_DIR / "memory" / "episodic" / "failure-events.jsonl"
EXPLORER_EVENTS = REPO_DIR / "memory" / "episodic" / "exploration-events.jsonl"
PROPOSALS_FILE = REPO_DIR / "memory" / "procedural" / "proposed-skill-updates.jsonl"

# Minimum thresholds
REPEATED_FAILURE_MIN_COUNT = 3
REPEATED_FAILURE_MIN_SESSIONS = 3
HIGH_RETRY_RATE_THRESHOLD = 0.50
HIGH_RETRY_MIN_ATTEMPTS = 5

# Domain → target skill file mapping
DOMAIN_TARGET_MAP = {
    "routes": "skills/defensive-backend-flows/SKILL.md",
    "migrations": "skills/defensive-backend-flows/SKILL.md",
    "auth": "skills/defensive-backend-flows/SKILL.md",
    "ui": "skills/defensive-ui-flows/SKILL.md",
    "tests": "skills/coding-best-practices/SKILL.md",
}
DEFAULT_TARGET = "skills/code-creation-workflow/SKILL.md"


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def load_proposals() -> list[dict]:
    return load_jsonl(PROPOSALS_FILE)


def existing_fingerprints(proposals: list[dict]) -> set[str]:
    """Return fingerprints of pending, applied, or rejected proposals."""
    return {p.get("evidence_fingerprint") for p in proposals if p.get("evidence_fingerprint")}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def make_proposal_id(trigger: str, seq: int) -> str:
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"prop-{date}-{trigger[:4]}-{seq:03d}"


def target_for_domain(domain: str | None) -> str:
    if not domain:
        return DEFAULT_TARGET
    return DOMAIN_TARGET_MAP.get(domain, DEFAULT_TARGET)


# ---------------------------------------------------------------------------
# Trigger 1: repeated_failure
# ---------------------------------------------------------------------------

def detect_repeated_failures(events: list[dict]) -> list[dict]:
    """Group failure events by error_class; emit proposals for recurring classes."""
    by_class: dict[str, dict] = defaultdict(lambda: {"count": 0, "sessions": set(), "samples": []})
    for ev in events:
        err = ev.get("error_class")
        if not err:
            continue
        by_class[err]["count"] += 1
        sess = ev.get("session_id")
        if sess:
            by_class[err]["sessions"].add(sess)
        if len(by_class[err]["samples"]) < 3:
            by_class[err]["samples"].append(ev)

    proposals = []
    for err_class, data in by_class.items():
        if data["count"] < REPEATED_FAILURE_MIN_COUNT:
            continue
        if len(data["sessions"]) < REPEATED_FAILURE_MIN_SESSIONS:
            continue

        # Infer domain from first sample
        domain = data["samples"][0].get("domain") if data["samples"] else None
        target = target_for_domain(domain)

        # Confidence: count beyond threshold + session diversity
        extra_occurrences = data["count"] - REPEATED_FAILURE_MIN_COUNT
        confidence = min(0.5 + 0.1 * extra_occurrences + 0.05 * (len(data["sessions"]) - REPEATED_FAILURE_MIN_SESSIONS), 1.0)

        proposals.append({
            "trigger": "repeated_failure",
            "evidence": {
                "error_class": err_class,
                "occurrences": data["count"],
                "sessions": sorted(data["sessions"]),
            },
            "proposed_action": "add_defensive_pattern",
            "target_file": target,
            "content_stub": f"Recurring failure `{err_class}` — hit {data['count']}x across {len(data['sessions'])} sessions",
            "content": None,
            "confidence": round(confidence, 2),
            "evidence_fingerprint": f"repeated_failure:{err_class}",
        })
    return proposals


# ---------------------------------------------------------------------------
# Trigger 2: high_retry_domain
# ---------------------------------------------------------------------------

def detect_high_retry_domains(explorer_events: list[dict]) -> list[dict]:
    """Emit proposals for domains with >50% retry rate over ≥5 attempts."""
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "retries": 0})
    for ev in explorer_events:
        dom = ev.get("domain")
        if not dom:
            continue
        stats[dom]["attempts"] += 1
        # Count attempts that had ≥1 retry, not total retry count
        if ev.get("phase5_retries", 0) > 0:
            stats[dom]["retries"] += 1

    proposals = []
    for dom, s in stats.items():
        if s["attempts"] < HIGH_RETRY_MIN_ATTEMPTS:
            continue
        rate = s["retries"] / s["attempts"]
        if rate <= HIGH_RETRY_RATE_THRESHOLD:
            continue

        confidence = min(0.4 + (rate - HIGH_RETRY_RATE_THRESHOLD) + 0.05 * (s["attempts"] - HIGH_RETRY_MIN_ATTEMPTS), 1.0)

        proposals.append({
            "trigger": "high_retry_domain",
            "evidence": {
                "domain": dom,
                "retry_rate": round(rate, 3),
                "attempts": s["attempts"],
                "retries": s["retries"],
            },
            "proposed_action": "add_domain_guidance",
            "target_file": target_for_domain(dom),
            "content_stub": f"Domain `{dom}` retries {int(rate*100)}% of the time ({s['retries']}/{s['attempts']})",
            "content": None,
            "confidence": round(confidence, 2),
            "evidence_fingerprint": f"high_retry_domain:{dom}",
        })
    return proposals


# ---------------------------------------------------------------------------
# Main detection pipeline
# ---------------------------------------------------------------------------

def detect_all() -> list[dict]:
    """Run all detectors, dedupe against existing proposals, return new proposals."""
    existing = load_proposals()
    seen_fps = existing_fingerprints(existing)

    failures = load_jsonl(FAILURE_EVENTS)
    explorer = load_jsonl(EXPLORER_EVENTS)

    candidates = []
    candidates.extend(detect_repeated_failures(failures))
    candidates.extend(detect_high_retry_domains(explorer))

    # Dedupe + add boilerplate fields
    new_proposals = []
    for i, c in enumerate(candidates, start=1):
        if c["evidence_fingerprint"] in seen_fps:
            continue
        new_proposals.append({
            "id": make_proposal_id(c["trigger"], len(existing) + i),
            "detected_at": now_iso(),
            "status": "pending",
            "applied_at": None,
            "rejected_at": None,
            "reject_reason": None,
            **c,
        })

    return new_proposals


def write_proposals(new_proposals: list[dict]) -> None:
    if not new_proposals:
        return
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with PROPOSALS_FILE.open("a") as f:
        for p in new_proposals:
            f.write(json.dumps(p) + "\n")


def main():
    new = detect_all()
    write_proposals(new)
    if not new:
        print("No new patterns detected.")
    else:
        print(f"Detected {len(new)} new proposal(s):")
        for p in new:
            print(f"  [{p['id']}] {p['trigger']}: {p['content_stub']} (confidence {p['confidence']})")
        print(f"\nReview with: python3 scripts/review-proposals.py list")


if __name__ == "__main__":
    main()
