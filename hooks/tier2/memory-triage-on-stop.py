#!/usr/bin/env python3
"""Scan MEMORY_DIR for entries not indexed in MEMORY.md; write REVIEW_QUEUE.md.

Mechanical only — no clustering, no subjective promotion decisions.
Writes to $MEMORY_DIR/REVIEW_QUEUE.md. Does NOT modify MEMORY.md or commit.
"""
import sys
import pathlib
import datetime

memory_dir = pathlib.Path(sys.argv[1])
index = memory_dir / "MEMORY.md"
queue = memory_dir / "REVIEW_QUEUE.md"

if not index.exists():
    sys.exit(0)

indexed = index.read_text()
unindexed = []
for md in sorted(memory_dir.glob("*.md")):
    if md.name in ("MEMORY.md", "REVIEW_QUEUE.md"):
        continue
    if md.name not in indexed:
        unindexed.append(md.name)

now = datetime.datetime.now().isoformat(timespec="seconds")

if not unindexed:
    queue.write_text(
        f"# Review Queue\n\n_Last scanned: {now}_\n\nAll memory files indexed.\n"
    )
    sys.exit(0)

lines = [
    "# Review Queue",
    "",
    f"_Last scanned: {now}_",
    "",
    "## Memory files not linked from MEMORY.md",
    "",
]
lines.extend(f"- [ ] `{name}`" for name in unindexed)
lines.append("")
lines.append("_Review each entry; add a one-line pointer to MEMORY.md or delete if stale._")
lines.append("")
queue.write_text("\n".join(lines))
