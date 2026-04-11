#!/usr/bin/env python3
from __future__ import annotations
"""Review CLI for skill-update proposals produced by pattern-detector.py.

Commands:
  list                 — show pending proposals
  list --all           — show all proposals (pending/applied/rejected)
  show <id>            — full proposal
  set-content <id> <file>  — load proposal content from a file
  apply <id>           — backup target, append content, mark applied
  reject <id> <reason> — mark rejected with reason
  stats                — counts by status/trigger
"""
import argparse
import json
import os
import shutil
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_DIR = Path(os.environ.get(
    "CLAUDE_FLOW_DIR",
    Path(__file__).resolve().parent.parent,
))
PROPOSALS_FILE = REPO_DIR / "memory" / "procedural" / "proposed-skill-updates.jsonl"
BACKUP_DIR = REPO_DIR / "memory" / "skill-backups"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_proposals() -> list[dict]:
    if not PROPOSALS_FILE.exists():
        return []
    out = []
    for line in PROPOSALS_FILE.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line))
    return out


def save_proposals(proposals: list[dict]) -> None:
    PROPOSALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROPOSALS_FILE.write_text(
        "\n".join(json.dumps(p) for p in proposals) + ("\n" if proposals else "")
    )


def find_proposal(proposals: list[dict], pid: str) -> dict | None:
    for p in proposals:
        if p.get("id") == pid:
            return p
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_list(show_all: bool) -> int:
    proposals = load_proposals()
    filtered = proposals if show_all else [p for p in proposals if p.get("status") == "pending"]
    if not filtered:
        print("No proposals." if show_all else "No pending proposals.")
        return 0

    print(f"{'ID':<30}{'Status':<12}{'Conf':<8}{'Trigger':<20}Summary")
    print("-" * 100)
    for p in filtered:
        conf = f"{p.get('confidence', 0):.2f}"
        low = " [low]" if p.get("confidence", 0) < 0.3 else ""
        summary = p.get("content_stub", "")[:60]
        print(f"{p['id']:<30}{p['status']:<12}{conf + low:<8}{p['trigger']:<20}{summary}")
    return 0


def cmd_show(pid: str) -> int:
    proposals = load_proposals()
    p = find_proposal(proposals, pid)
    if not p:
        print(f"Proposal {pid} not found.", file=sys.stderr)
        return 1
    print(json.dumps(p, indent=2))
    return 0


def cmd_set_content(pid: str, content_file: str) -> int:
    proposals = load_proposals()
    p = find_proposal(proposals, pid)
    if not p:
        print(f"Proposal {pid} not found.", file=sys.stderr)
        return 1

    content_path = Path(content_file)
    if not content_path.exists():
        print(f"Content file not found: {content_file}", file=sys.stderr)
        return 1

    p["content"] = content_path.read_text()
    save_proposals(proposals)
    print(f"Set content for {pid} ({len(p['content'])} chars)")
    return 0


def cmd_apply(pid: str) -> int:
    proposals = load_proposals()
    p = find_proposal(proposals, pid)
    if not p:
        print(f"Proposal {pid} not found.", file=sys.stderr)
        return 1
    if p.get("status") != "pending":
        print(f"Proposal {pid} is {p['status']}, not pending.", file=sys.stderr)
        return 1
    if not p.get("content"):
        print(f"Proposal {pid} has no content. Use `set-content` first.", file=sys.stderr)
        return 1

    target = REPO_DIR / p["target_file"]
    if not target.exists():
        print(f"Target file does not exist: {target}", file=sys.stderr)
        return 1

    # Backup
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = BACKUP_DIR / f"{ts}-{target.name}"
    shutil.copy2(target, backup_path)

    # Append content
    with target.open("a") as f:
        if not target.read_text().endswith("\n"):
            f.write("\n")
        f.write("\n" + p["content"])
        if not p["content"].endswith("\n"):
            f.write("\n")

    # Mark applied
    p["status"] = "applied"
    p["applied_at"] = now_iso()
    save_proposals(proposals)

    print(f"Applied {pid} to {p['target_file']}")
    print(f"Backup: {backup_path}")
    return 0


def cmd_reject(pid: str, reason: str) -> int:
    proposals = load_proposals()
    p = find_proposal(proposals, pid)
    if not p:
        print(f"Proposal {pid} not found.", file=sys.stderr)
        return 1
    if p.get("status") != "pending":
        print(f"Proposal {pid} is {p['status']}, not pending.", file=sys.stderr)
        return 1

    p["status"] = "rejected"
    p["rejected_at"] = now_iso()
    p["reject_reason"] = reason
    save_proposals(proposals)
    print(f"Rejected {pid}: {reason}")
    return 0


def cmd_stats() -> int:
    proposals = load_proposals()
    if not proposals:
        print("No proposals yet.")
        return 0

    status_counts = Counter(p.get("status", "?") for p in proposals)
    trigger_counts = Counter(p.get("trigger", "?") for p in proposals)

    print("=== Proposals by Status ===")
    for status, count in sorted(status_counts.items()):
        print(f"  {status:<12}{count}")

    print("\n=== Proposals by Trigger ===")
    for trigger, count in sorted(trigger_counts.items()):
        print(f"  {trigger:<20}{count}")

    print(f"\nTotal: {len(proposals)}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Review skill-update proposals")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list")
    p_list.add_argument("--all", action="store_true")

    p_show = sub.add_parser("show")
    p_show.add_argument("id")

    p_set = sub.add_parser("set-content")
    p_set.add_argument("id")
    p_set.add_argument("file")

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("id")

    p_reject = sub.add_parser("reject")
    p_reject.add_argument("id")
    p_reject.add_argument("reason")

    sub.add_parser("stats")

    args = parser.parse_args()

    if args.command == "list":
        return cmd_list(args.all)
    if args.command == "show":
        return cmd_show(args.id)
    if args.command == "set-content":
        return cmd_set_content(args.id, args.file)
    if args.command == "apply":
        return cmd_apply(args.id)
    if args.command == "reject":
        return cmd_reject(args.id, args.reason)
    if args.command == "stats":
        return cmd_stats()
    return 1


if __name__ == "__main__":
    sys.exit(main())
