#!/usr/bin/env python3
"""Flag SKILL.md files that exceed the progressive-disclosure threshold.

Scans ~/.claude/skills (excluding .claude/worktrees snapshots) and emits a
markdown report to docs/audits/<date>-progressive-disclosure.md.

Thresholds (rough, tuned to ~5 tokens/line for markdown):
  >= 300 lines  → candidate (~2K tokens resident)
  >= 500 lines  → high priority
  >= 800 lines  → critical (likely wastes >4K tokens every session)

A skill is "already split" if it has phases/ or references/ subdirs sibling
to SKILL.md — those are excluded from the report as refactored.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ROOT = Path.home() / ".claude" / "skills"
DEFAULT_OUT = Path("docs/audits")
CANDIDATE = 300
HIGH = 500
CRITICAL = 800


@dataclass
class SkillEntry:
    name: str
    path: Path
    lines: int
    already_split: bool

    @property
    def severity(self) -> str:
        if self.lines >= CRITICAL:
            return "critical"
        if self.lines >= HIGH:
            return "high"
        if self.lines >= CANDIDATE:
            return "candidate"
        return "ok"


def find_skills(root: Path) -> list[SkillEntry]:
    entries: list[SkillEntry] = []
    for skill_md in root.rglob("SKILL.md"):
        # Skip worktree snapshots — they are stale copies.
        if ".claude/worktrees" in str(skill_md):
            continue
        skill_dir = skill_md.parent
        already_split = any(
            (skill_dir / sub).is_dir() for sub in ("phases", "references")
        )
        try:
            lines = sum(1 for _ in skill_md.open())
        except OSError:
            continue
        entries.append(
            SkillEntry(
                name=skill_dir.name,
                path=skill_md,
                lines=lines,
                already_split=already_split,
            )
        )
    return entries


def render_report(entries: list[SkillEntry], root: Path) -> str:
    entries = sorted(entries, key=lambda e: -e.lines)
    candidates = [e for e in entries if e.lines >= CANDIDATE and not e.already_split]
    split = [e for e in entries if e.already_split]

    today = dt.date.today().isoformat()
    out = [
        f"# Progressive Disclosure Audit — {today}",
        "",
        f"Scanned `{root}` ({len(entries)} SKILL.md files, worktree snapshots excluded).",
        "",
        "**Thresholds:**",
        f"- `critical` ≥ {CRITICAL} lines — refactor now",
        f"- `high` ≥ {HIGH} lines — refactor soon",
        f"- `candidate` ≥ {CANDIDATE} lines — consider splitting",
        "",
        f"## Refactor candidates ({len(candidates)})",
        "",
    ]
    if not candidates:
        out.append("_None — all skills under the threshold or already split._")
    else:
        out.append("| Severity | Lines | Skill | Path |")
        out.append("|----------|-------|-------|------|")
        for e in candidates:
            rel = e.path.resolve()
            out.append(f"| {e.severity} | {e.lines} | `{e.name}` | `{rel}` |")

    out.extend(["", f"## Already split ({len(split)})", ""])
    if split:
        out.append(", ".join(f"`{e.name}`" for e in split))
    else:
        out.append("_None._")

    out.extend(
        [
            "",
            "## Recommended split pattern",
            "",
            "Extract phase/reference content into sibling files, leave a thin router:",
            "",
            "```",
            "skill-name/",
            "  SKILL.md           # router (~150 lines / ~1K tokens)",
            "  phases/            # phase-specific content, loaded on demand",
            "  references/        # lookup tables, patterns, edge cases",
            "```",
            "",
            "Partition a monolithic SKILL.md without loading it into context:",
            "",
            "```bash",
            "sed -n 'M,Np' src/SKILL.md > references/patterns.md",
            "```",
            "",
            "See MEMORY entries `progressive_disclosure.md` and `token_efficiency_overhaul.md`.",
            "",
        ]
    )
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--stdout", action="store_true", help="Print report; do not write file.")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"error: root does not exist: {root}", file=sys.stderr)
        return 2

    entries = find_skills(root)
    report = render_report(entries, root)

    if args.stdout:
        print(report)
        return 0

    args.out_dir.mkdir(parents=True, exist_ok=True)
    out_path = args.out_dir / f"{dt.date.today().isoformat()}-progressive-disclosure.md"
    out_path.write_text(report)
    print(f"wrote {out_path} ({len(entries)} skills scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
