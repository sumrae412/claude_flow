#!/usr/bin/env python3
"""
Slim MEMORY.md index entries that exceed the line-length threshold.

For each over-long entry:
- If linked topic file exists: replace the entry with `- [Title](slug.md) — <one-line hook>`.
  The full detail is assumed to already live in the topic file (or we append it under
  `## Detail (migrated from MEMORY.md)` if --append-detail is set).
- If linked topic file is missing: create the topic file from the entry's detail,
  then slim the index entry.
- If the entry has no link: generate a slug from the title, create the topic file,
  add the link, slim the index entry.

Usage:
    python3 slim_memory_index.py <memory_dir> [--threshold 250] [--apply] [--append-detail]

Without --apply, prints a dry-run report of what would change.

Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class IndexEntry:
    line_no: int
    raw: str
    title: str
    slug: str | None
    detail: str
    length: int


# Standard format: - [Title](slug.md) — detail
# Slug must start with letter, contain only [a-z0-9_-], end before .md
TITLE_LINK_RE = re.compile(r"^- \[([^\]]+)\]\(([a-z][a-z0-9_-]+)\.md\)\s*[—-]\s*(.*)$")
# Bold format: - **Title:** detail   (Title may include any non-* chars including colons)
TITLE_BOLD_RE = re.compile(r"^- \*\*([^*]+?)[:.]?\*\*\s*[:—-]?\s*(.*)$")
# Plain format: - Title — detail   (Title is one phrase before em-dash)
TITLE_PLAIN_RE = re.compile(r"^- ([A-Z][^—]{2,120})—\s*(.*)$")


def slugify(title: str) -> str:
    # Strip leading category labels like "Pattern: ", "Gotcha: ", etc., but keep
    # the substantive title — never produce an empty slug.
    stripped = re.sub(r"^[A-Z][A-Za-z][\w ]*:\s*", "", title)
    if not stripped.strip():
        stripped = title
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", stripped).strip("_").lower()
    return cleaned[:60] or "untitled"


def parse_entry(line_no: int, raw: str) -> IndexEntry | None:
    line = raw.rstrip("\n")
    if not line.startswith("- "):
        return None
    m = TITLE_LINK_RE.match(line)
    if m:
        title, slug, detail = m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
        return IndexEntry(line_no, line, title, slug, detail, len(line))
    m = TITLE_BOLD_RE.match(line)
    if m:
        title, detail = m.group(1).strip(), m.group(2).strip()
        return IndexEntry(line_no, line, title, None, detail, len(line))
    m = TITLE_PLAIN_RE.match(line)
    if m:
        title, detail = m.group(1).strip(), m.group(2).strip()
        return IndexEntry(line_no, line, title, None, detail, len(line))
    return None


def first_sentence(text: str, max_len: int) -> str:
    """Extract a short hook from the detail. Prefer the first complete sentence
    that fits, otherwise truncate at a word boundary."""
    text = text.strip()
    if not text:
        return ""
    # Try to find the first sentence terminator inside max_len
    for end_char in [".", ";", "—"]:
        idx = text.find(end_char)
        while idx != -1 and idx < max_len:
            # Skip dots inside backticks/parens
            chunk = text[: idx + 1]
            if chunk.count("`") % 2 == 0 and chunk.count("(") == chunk.count(")"):
                return chunk.rstrip()
            idx = text.find(end_char, idx + 1)
    if len(text) <= max_len:
        return text
    # Truncate at word boundary
    cut = text[:max_len].rsplit(" ", 1)[0].rstrip(",.;:—-")
    return f"{cut}…"


def render_entry(entry: IndexEntry, hook: str, slug: str) -> str:
    # Hook may be empty if entry was already a one-liner
    suffix = f" — {hook}" if hook else ""
    return f"- [{entry.title}]({slug}.md){suffix}"


def ensure_topic_file(memory_dir: Path, slug: str, title: str, detail: str, append_detail: bool) -> tuple[bool, str]:
    """Return (created_or_modified, action_description)."""
    path = memory_dir / f"{slug}.md"
    if not path.exists():
        body = f"# {title}\n\n{detail}\n"
        path.write_text(body)
        return True, f"created {path.name} ({len(detail)}c)"
    if not append_detail:
        return False, f"kept existing {path.name} (detail not appended)"
    # Append only if the detail isn't already substantively present
    existing = path.read_text()
    # Sample first 100 chars of detail; if present, skip
    probe = re.sub(r"\s+", " ", detail[:100])
    existing_normalized = re.sub(r"\s+", " ", existing)
    if probe and probe in existing_normalized:
        return False, f"detail already present in {path.name}"
    with path.open("a") as f:
        f.write(f"\n## Detail (migrated from MEMORY.md)\n\n{detail}\n")
    return True, f"appended detail to {path.name} ({len(detail)}c)"


def process(memory_dir: Path, threshold: int, apply: bool, append_detail: bool) -> int:
    memory_md = memory_dir / "MEMORY.md"
    if not memory_md.exists():
        print(f"ERROR: {memory_md} not found", file=sys.stderr)
        return 2

    lines = memory_md.read_text().splitlines(keepends=True)
    new_lines = list(lines)
    changes = 0
    report: list[str] = []

    for i, raw in enumerate(lines):
        entry = parse_entry(i + 1, raw)
        if entry is None or entry.length <= threshold:
            continue

        # Decide slug
        slug = entry.slug or slugify(entry.title)
        # Compute hook
        # Total budget: threshold - len("- [<title>](<slug>.md) — ")
        # Subtract 4 for safety: trailing newline + ellipsis room + em-dash width drift
        prefix_len = len(f"- [{entry.title}]({slug}.md) — ")
        hook_budget = max(40, threshold - prefix_len - 4)
        hook = first_sentence(entry.detail, hook_budget)
        new_line = render_entry(entry, hook, slug) + "\n"

        # Topic-file action
        action = "skipped topic file"
        if entry.slug is None:
            modified, action = ensure_topic_file(memory_dir, slug, entry.title, entry.detail, append_detail=True)
        else:
            topic_path = memory_dir / f"{entry.slug}.md"
            if not topic_path.exists():
                modified, action = ensure_topic_file(memory_dir, entry.slug, entry.title, entry.detail, append_detail=True)
            else:
                modified, action = ensure_topic_file(memory_dir, entry.slug, entry.title, entry.detail, append_detail=append_detail)

        if apply:
            new_lines[i] = new_line
        report.append(
            f"L{entry.line_no}: {entry.length}c → {len(new_line.rstrip())}c | {action} | new: {new_line.rstrip()[:120]}"
        )
        changes += 1

    if apply and changes:
        memory_md.write_text("".join(new_lines))

    print(f"=== Memory Index Slim Report (threshold={threshold}, apply={apply}, append_detail={append_detail}) ===")
    print(f"Entries over threshold: {changes}")
    for line in report:
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("memory_dir", type=Path, help="Directory containing MEMORY.md and topic files")
    parser.add_argument("--threshold", type=int, default=250, help="Max index-line length (default 250)")
    parser.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    parser.add_argument(
        "--append-detail",
        action="store_true",
        help="Append over-flow detail to existing topic files (default: only create new ones)",
    )
    args = parser.parse_args()
    return process(args.memory_dir, args.threshold, args.apply, args.append_detail)


if __name__ == "__main__":
    sys.exit(main())
