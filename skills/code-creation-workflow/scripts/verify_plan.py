#!/usr/bin/env python3
"""Verify implementation plan file paths and references against the codebase.

Zero-token Phase 4c verification — runs as a script instead of LLM reasoning.
Checks that files, functions, and patterns referenced in the plan actually exist.

Usage:
    python scripts/verify_plan.py <plan_file> [--project-root .]

Output: JSON with verified/missing/stale entries. Non-zero exit if material mismatches found.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def extract_file_paths(plan_text: str) -> list[dict]:
    """Extract file paths and their context from plan text."""
    entries = []

    # Match patterns like: Create: `path/to/file.py` or Modify: `path/to/file.py`
    for match in re.finditer(
        r"(Create|Modify|Test|Read):\s*`([^`]+)`", plan_text
    ):
        entries.append({"action": match.group(1), "path": match.group(2)})

    # Match patterns like: - `path/to/file.py` (in file lists)
    for match in re.finditer(r"^\s*-\s*`([^`]+\.\w+)`", plan_text, re.MULTILINE):
        path = match.group(1)
        if path not in [e["path"] for e in entries]:
            entries.append({"action": "Reference", "path": path})

    return entries


def extract_function_refs(plan_text: str) -> list[dict]:
    """Extract function/class/method references from plan text."""
    refs = []

    # Match patterns like: function_name() or ClassName.method()
    for match in re.finditer(
        r"`(\w+(?:\.\w+)?)\(\)`\s+(?:in|from)\s+`([^`]+)`", plan_text
    ):
        refs.append({"symbol": match.group(1), "file": match.group(2)})

    return refs


def extract_pattern_claims(plan_text: str) -> list[dict]:
    """Extract 'follows X pattern' claims."""
    claims = []
    for match in re.finditer(
        r"(?:follows|uses|matches|like)\s+(?:existing\s+)?(?:the\s+)?`?(\w[\w\s]*)`?\s+pattern",
        plan_text,
        re.IGNORECASE,
    ):
        claims.append({"pattern": match.group(1).strip()})
    return claims


def verify_file_path(path: str, action: str, project_root: Path) -> dict:
    """Check if a file path exists (or doesn't for Create actions)."""
    full_path = project_root / path
    exists = full_path.exists()

    if action == "Create":
        if exists:
            return {
                "path": path,
                "action": action,
                "status": "warning",
                "message": f"File already exists (plan says Create)",
            }
        else:
            return {"path": path, "action": action, "status": "ok", "message": "OK (will be created)"}
    else:
        if exists:
            return {"path": path, "action": action, "status": "ok", "message": "OK"}
        else:
            return {
                "path": path,
                "action": action,
                "status": "missing",
                "message": f"File not found",
            }


def verify_symbol(symbol: str, file_path: str, project_root: Path) -> dict:
    """Check if a symbol exists in the specified file."""
    full_path = project_root / file_path
    if not full_path.exists():
        return {
            "symbol": symbol,
            "file": file_path,
            "status": "missing",
            "message": f"File not found",
        }

    # Strip class prefix for grep
    search_term = symbol.split(".")[-1] if "." in symbol else symbol

    try:
        result = subprocess.run(
            ["grep", "-En", f"def {search_term}|class {search_term}", str(full_path)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            line = result.stdout.strip().split("\n")[0]
            return {
                "symbol": symbol,
                "file": file_path,
                "status": "ok",
                "message": f"Found: {line.strip()}",
            }
        else:
            return {
                "symbol": symbol,
                "file": file_path,
                "status": "missing",
                "message": f"Symbol '{search_term}' not found in {file_path}",
            }
    except subprocess.TimeoutExpired:
        return {
            "symbol": symbol,
            "file": file_path,
            "status": "error",
            "message": "grep timed out",
        }


def main():
    parser = argparse.ArgumentParser(description="Verify plan references against codebase")
    parser.add_argument("plan_file", help="Path to the plan markdown file")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    plan_path = Path(args.plan_file)

    if not plan_path.exists():
        print(f"Error: Plan file not found: {plan_path}", file=sys.stderr)
        sys.exit(2)

    plan_text = plan_path.read_text()

    # Extract and verify
    file_paths = extract_file_paths(plan_text)
    function_refs = extract_function_refs(plan_text)
    pattern_claims = extract_pattern_claims(plan_text)

    file_results = [verify_file_path(e["path"], e["action"], project_root) for e in file_paths]
    symbol_results = [verify_symbol(r["symbol"], r["file"], project_root) for r in function_refs]

    # Summarize
    all_results = file_results + symbol_results
    missing = [r for r in all_results if r["status"] == "missing"]
    warnings = [r for r in all_results if r["status"] == "warning"]
    errors = [r for r in all_results if r["status"] == "error"]
    ok = [r for r in all_results if r["status"] == "ok"]

    output = {
        "plan_file": str(plan_path),
        "project_root": str(project_root),
        "summary": {
            "total_checks": len(all_results),
            "ok": len(ok),
            "missing": len(missing),
            "warnings": len(warnings),
            "errors": len(errors),
            "patterns_claimed": len(pattern_claims),
        },
        "missing": missing,
        "warnings": warnings,
        "errors": errors,
        "patterns": pattern_claims,
    }

    if args.json:
        print(json.dumps(output, indent=2))
    else:
        print(f"Plan verification: {len(ok)}/{len(all_results)} references OK")
        if missing:
            print(f"\nMISSING ({len(missing)}):")
            for r in missing:
                print(f"  - {r.get('path', r.get('symbol', '?'))}: {r['message']}")
        if errors:
            print(f"\nERRORS ({len(errors)}):")
            for r in errors:
                print(f"  - {r.get('symbol', '?')}: {r['message']}")
        if warnings:
            print(f"\nWARNINGS ({len(warnings)}):")
            for r in warnings:
                print(f"  - {r['path']}: {r['message']}")
        if pattern_claims:
            print(f"\nPATTERN CLAIMS ({len(pattern_claims)}) — verify manually:")
            for p in pattern_claims:
                print(f"  - \"{p['pattern']}\"")

    # Exit non-zero if material mismatches or errors
    if missing or errors:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
