#!/usr/bin/env python3
"""
Mechanical reviewer selection for Phase 6 cascading review.

Replaces the LLM-prose "look at the diff and decide which conditional
reviewers to dispatch" step with deterministic glob + content matching against
reviewer-registry.json.

Inputs:
- A diff file list (one path per arg or via stdin)
- The reviewer-registry.json path (auto-detected from project root or passed)
- Optionally a directory containing the diff content for content_pattern checks
  (--diff-dir; default: current working directory)

Output (JSON to stdout):
{
  "always": [
    {"id": "coderabbit", "cascade_tier": 1, "subagent_type": "...", ...}
  ],
  "conditional_matched": [
    {"id": "async-reviewer", "cascade_tier": 3, "matched_files": ["..."], ...}
  ],
  "conditional_skipped": [
    {"id": "google-api-reviewer", "reason": "no file matched ..."}
  ],
  "by_tier": {"1": ["coderabbit"], "2": [...], "3": [...]}
}

Phase 6 then dispatches by tier, applying the early-exit rule (skip later
tiers if Tier 1 found no HIGH+ issues).

Stdlib only.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from pathlib import Path


def load_registry(path: Path) -> dict:
    if not path.exists():
        return {"reviewers": []}
    return json.loads(path.read_text())


def find_default_registry(start: Path) -> Path | None:
    """Walk up looking for reviewer-registry.json; check $HOME/.claude/ as fallback."""
    cur = start.resolve()
    for _ in range(8):
        cand = cur / "reviewer-registry.json"
        if cand.exists():
            return cand
        cand = cur / ".claude" / "reviewer-registry.json"
        if cand.exists():
            return cand
        if cur == cur.parent:
            break
        cur = cur.parent
    fallback = Path.home() / ".claude" / "reviewer-registry.json"
    return fallback if fallback.exists() else None


def file_matches_patterns(file_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(file_path, pat):
            return True
        # Also try matching without leading **/ for convenience
        if pat.startswith("**/") and fnmatch.fnmatch(file_path, pat[3:]):
            return True
        if not pat.startswith("**/") and fnmatch.fnmatch(file_path, f"**/{pat}"):
            return True
    return False


def count_content_matches(matched_files: list[str], pattern: str, diff_dir: Path) -> int:
    """Count occurrences of `pattern` (regex) across the matched files.

    Reads each file from diff_dir; missing files contribute 0. Used for the
    `content_pattern` + `threshold` reviewer gating in the registry.
    """
    if not pattern:
        return 0
    rx = re.compile(pattern, re.MULTILINE)
    total = 0
    for fp in matched_files:
        path = (diff_dir / fp).resolve()
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        total += len(rx.findall(text))
    return total


def select(registry: dict, file_paths: list[str], diff_dir: Path) -> dict:
    always: list[dict] = []
    matched: list[dict] = []
    skipped: list[dict] = []
    for r in registry.get("reviewers", []):
        if r.get("tier") == "always":
            always.append(r)
            continue
        # conditional
        patterns = r.get("file_patterns", [])
        matched_files = [fp for fp in file_paths if file_matches_patterns(fp, patterns)]
        if not matched_files:
            skipped.append({"id": r["id"], "reason": f"no file matched {patterns}"})
            continue
        content_pattern = r.get("content_pattern")
        threshold = int(r.get("threshold", 0) or 0)
        if content_pattern and threshold > 0:
            count = count_content_matches(matched_files, content_pattern, diff_dir)
            if count < threshold:
                skipped.append(
                    {
                        "id": r["id"],
                        "reason": f"content_pattern matched {count}x; needs ≥{threshold}",
                    }
                )
                continue
        matched.append({**r, "matched_files": matched_files})

    by_tier: dict[str, list[str]] = {}
    for r in always + matched:
        tier = str(r.get("cascade_tier", "?"))
        by_tier.setdefault(tier, []).append(r["id"])

    return {
        "always": always,
        "conditional_matched": matched,
        "conditional_skipped": skipped,
        "by_tier": by_tier,
        "input_file_count": len(file_paths),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=None,
        help="reviewer-registry.json path (auto-detected by walking up from cwd)",
    )
    parser.add_argument(
        "--diff-dir",
        type=Path,
        default=Path.cwd(),
        help="Directory to resolve relative paths against for content_pattern checks",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="File paths from the diff. If empty, read one path per line from stdin.",
    )
    args = parser.parse_args()

    file_paths = args.files
    if not file_paths and not sys.stdin.isatty():
        file_paths = [line.strip() for line in sys.stdin if line.strip()]

    registry_path = args.registry or find_default_registry(args.diff_dir)
    if registry_path is None:
        print(json.dumps({"error": "reviewer-registry.json not found"}), file=sys.stderr)
        return 2
    registry = load_registry(registry_path)
    result = select(registry, file_paths, args.diff_dir)
    result["registry_path"] = str(registry_path)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
