#!/usr/bin/env python3
"""Convert a freeform memory dump into a review-only import file."""
from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

CATEGORY_PROJECT_FACTS: str = "Project Facts"
CATEGORY_USER_PREFERENCES: str = "User Preferences"
CATEGORY_DECISIONS: str = "Decisions"
CATEGORY_GOTCHAS: str = "Recurring Gotchas"
CATEGORY_REJECTED: str = "Rejected / Too Vague / Task-Specific"

CATEGORIES: list[str] = [
    CATEGORY_PROJECT_FACTS,
    CATEGORY_USER_PREFERENCES,
    CATEGORY_DECISIONS,
    CATEGORY_GOTCHAS,
    CATEGORY_REJECTED,
]

PREFERENCE_PATTERNS: tuple[str, ...] = (
    "prefer",
    "never",
    "always",
    "i like",
    "i don't want",
    "responses",
    "style",
    "tone",
)
DECISION_PATTERNS: tuple[str, ...] = (
    "decided",
    "decision",
    "chose",
    "approved",
    "rejected",
)
GOTCHA_PATTERNS: tuple[str, ...] = (
    "gotcha",
    "bug",
    "failed",
    "avoid",
    "do not",
    "breaks",
    "regression",
    "watch out",
)
PROJECT_FACT_PATTERNS: tuple[str, ...] = (
    "repo",
    "repository",
    "project",
    "script",
    "hook",
    "skill",
    "memory",
    "tool",
    "workflow",
    "docs/",
    "tests/",
)
TEMPORAL_PATTERNS: tuple[str, ...] = (
    "today",
    "tomorrow",
    "yesterday",
    "this task",
    "current task",
    "right now",
    "for now",
)
GENERIC_PATTERNS: tuple[str, ...] = (
    "be careful",
    "remember this",
    "important",
    "todo",
)


def split_candidate_lines(text: str) -> list[str]:
    """Return non-empty candidate memory lines from markdown or plain text."""
    candidates: list[str] = []
    for raw_line in text.splitlines():
        line: str = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^>\s*", "", line)
        line = re.sub(r"^[-*+]\s+(\[[ xX]\]\s*)?", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = line.strip()
        if line:
            candidates.append(line)
    return candidates


def _contains_any(line: str, patterns: tuple[str, ...]) -> bool:
    normalized: str = line.casefold()
    return any(pattern in normalized for pattern in patterns)


def _is_too_vague_or_task_specific(line: str) -> bool:
    normalized: str = line.casefold()
    word_count: int = len(re.findall(r"\w+", line))
    if word_count < 3:
        return True
    if _contains_any(line, TEMPORAL_PATTERNS):
        return True
    if normalized in GENERIC_PATTERNS:
        return True
    if normalized.rstrip(".") in GENERIC_PATTERNS:
        return True
    return False


def classify_line(line: str) -> str:
    """Classify one candidate line using deterministic priority rules."""
    if _is_too_vague_or_task_specific(line):
        return CATEGORY_REJECTED
    if _contains_any(line, GOTCHA_PATTERNS):
        return CATEGORY_GOTCHAS
    if _contains_any(line, DECISION_PATTERNS) or re.search(
        r"\buse\b.+\bover\b",
        line,
        re.IGNORECASE,
    ):
        return CATEGORY_DECISIONS
    if _contains_any(line, PREFERENCE_PATTERNS):
        return CATEGORY_USER_PREFERENCES
    if _contains_any(line, PROJECT_FACT_PATTERNS):
        return CATEGORY_PROJECT_FACTS
    return CATEGORY_PROJECT_FACTS


def categorize_lines(lines: list[str]) -> dict[str, list[str]]:
    """Group candidate lines by review category."""
    categorized: dict[str, list[str]] = {
        category: [] for category in CATEGORIES
    }
    for line in lines:
        categorized[classify_line(line)].append(line)
    return categorized


def build_review_markdown(
    source: Path,
    categorized: dict[str, list[str]],
) -> str:
    """Build checkbox markdown for manual import review."""
    generated: str = datetime.datetime.now(
        datetime.timezone.utc,
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    lines: list[str] = [
        "# Import Review",
        "",
        f"_Source: {source}_",
        f"_Generated: {generated}_",
        "",
    ]
    for category in CATEGORIES:
        lines.append(f"## {category}")
        lines.append("")
        entries: list[str] = categorized.get(category, [])
        if entries:
            lines.extend(f"- [ ] {entry}" for entry in entries)
        else:
            lines.append("- [ ]")
        lines.append("")
    return "\n".join(lines)


def _resolve_path(path: Path, project_root: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _validate_output_path(path: Path) -> None:
    if path.name == "MEMORY.md":
        raise ValueError("Refusing to write canonical MEMORY.md")
    parts: tuple[str, ...] = path.parts
    protected_dirs: tuple[tuple[str, str], ...] = (
        ("memory", "semantic"),
        ("memory", "procedural"),
        ("memory", "episodic"),
    )
    for first, second in protected_dirs:
        for index, part in enumerate(parts[:-1]):
            if part == first and parts[index + 1] == second:
                raise ValueError(f"Refusing to write under {first}/{second}")


def write_import_review(
    source: Path,
    output: Path,
    project_root: Path,
    force: bool = False,
) -> Path:
    """Read source and write categorized review markdown."""
    source_path: Path = _resolve_path(source, project_root)
    output_path: Path = _resolve_path(output, project_root)
    _validate_output_path(output_path)
    if output_path.exists() and not force:
        raise FileExistsError(
            f"{output_path} exists; pass --force to overwrite",
        )

    text: str = source_path.read_text(encoding="utf-8")
    categorized: dict[str, list[str]] = categorize_lines(
        split_candidate_lines(text),
    )
    markdown: str = build_review_markdown(source_path, categorized)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser(
        description="Create a review-only memory import file.",
    )
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("memory/IMPORT_REVIEW.md"),
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--force", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint."""
    args: argparse.Namespace = parse_args(argv)
    try:
        output_path: Path = write_import_review(
            source=args.source,
            output=args.out,
            project_root=args.project_root,
            force=args.force,
        )
    except (FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
