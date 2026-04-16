#!/usr/bin/env python3
"""
Mechanical file-pattern → domain → gotcha-key matching for memory-injection.

Replaces the LLM-prose Steps 3-4 in skills/memory-injection/SKILL.md with
deterministic glob matching against the domain table in
skills/claude-flow/references/memory-injection.md.

Inputs:
- A list of file paths (one per arg or via stdin)
- The memory-injection.md reference file (parsed for the domain table)
- The MEMORY.md file (parsed for one-line gotcha entries by semantic key)

Output (JSON to stdout):
{
  "matched_domains": ["models", "services"],
  "matched_keys": ["client-sync-map", "is-primary-contact", ...],
  "matched_entries": [
    {"key": "is-primary-contact", "line": "- [...](...) — ...", "topic_file": "is_primary_contact.md"},
    ...
  ],
  "skipped": []
}

The LLM caller assembles the final PROJECT_GOTCHAS block from this output.
Stdlib only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


def parse_domain_table(reference_file: Path) -> list[dict]:
    """Parse the markdown domain table from memory-injection.md.

    Expected table format:
        | Domain | File Patterns | Gotcha Keys |
        |--------|--------------|-------------|
        | models | `models/*`, `alembic/*` | `key1`, `key2`, `key3` |
    """
    if not reference_file.exists():
        return []
    rows = []
    in_table = False
    for raw in reference_file.read_text().splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            in_table = False
            continue
        if "Domain" in line and "File Patterns" in line and "Gotcha Keys" in line:
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if not in_table:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        domain = cells[0]
        patterns = [p.strip().strip("`") for p in cells[1].split(",") if p.strip()]
        keys = [k.strip().strip("`") for k in cells[2].split(",") if k.strip()]
        rows.append({"domain": domain, "patterns": patterns, "keys": keys})
    return rows


def match_files_to_domains(file_paths: list[str], domain_table: list[dict]) -> tuple[list[str], list[str]]:
    matched_domains: set[str] = set()
    matched_keys: set[str] = set()
    for fp in file_paths:
        for row in domain_table:
            for pat in row["patterns"]:
                # Convert simple glob (`models/*`) to fnmatch (`*models/*`) so it
                # matches any prefix on the path
                if fnmatch.fnmatch(fp, pat) or fnmatch.fnmatch(fp, f"*/{pat}"):
                    matched_domains.add(row["domain"])
                    matched_keys.update(row["keys"])
                    break
    return sorted(matched_domains), sorted(matched_keys)


def parse_memory_index(memory_md: Path) -> dict[str, dict]:
    """Return {semantic_key: {"line": ..., "topic_file": slug}} where semantic
    key is derived from the topic-file slug (filename stem with underscores
    converted to hyphens, lowercase). This matches the convention in the
    memory-injection.md domain table."""
    if not memory_md.exists():
        return {}
    entries = {}
    link_re = re.compile(r"\[([^\]]+)\]\(([a-z][a-z0-9_-]+)\.md\)")
    for raw in memory_md.read_text().splitlines():
        if not raw.startswith("- "):
            continue
        m = link_re.search(raw)
        if not m:
            continue
        slug = m.group(2)
        key = slug.replace("_", "-")
        entries[key] = {"line": raw.rstrip(), "topic_file": f"{slug}.md"}
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("memory_dir", type=Path, help="Directory containing MEMORY.md")
    parser.add_argument(
        "--reference",
        type=Path,
        default=Path(__file__).parent.parent / "references" / "memory-injection.md",
        help="memory-injection.md reference file (defaults to claude-flow's copy)",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="File paths to match (touched files in current task). If empty, read one path per line from stdin.",
    )
    args = parser.parse_args()

    file_paths = args.files
    if not file_paths and not sys.stdin.isatty():
        file_paths = [line.strip() for line in sys.stdin if line.strip()]

    domain_table = parse_domain_table(args.reference)
    matched_domains, matched_keys = match_files_to_domains(file_paths, domain_table)

    memory_index = parse_memory_index(args.memory_dir / "MEMORY.md")
    matched_entries = []
    skipped = []
    for key in matched_keys:
        if key in memory_index:
            matched_entries.append({"key": key, **memory_index[key]})
        else:
            skipped.append(key)

    output = {
        "matched_domains": matched_domains,
        "matched_keys": matched_keys,
        "matched_entries": matched_entries,
        "skipped": skipped,
        "input_file_count": len(file_paths),
    }
    json.dump(output, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
