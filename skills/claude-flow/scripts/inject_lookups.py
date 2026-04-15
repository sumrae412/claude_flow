#!/usr/bin/env python3
"""Authoring-time lookup injection — prevent hallucination by running
deterministic lookups and injecting the results into implementer prompts.

Inspired by Brian/Notion's `find-icon` skill: don't let the LLM guess
when a script can look up the truth.

Two scopes:
- plan (--scope plan): run once before Phase 5; results shared by all implementers
- step (--scope step): run at subagent dispatch time; narrower, per-file

Each detector returns (result_str, skipped_reason) and never raises.
See skills/claude-flow/references/lookup-detectors.md for the registry.

Usage:
    python skills/claude-flow/scripts/inject_lookups.py \\
        --scope plan \\
        --files alembic/versions/new.py app/routes/new.py \\
        --json

Output:
    {
      "scope": "plan",
      "lookups": {"alembic_heads": "<output>", "fastapi_routes": "<output>"},
      "skipped_detectors": ["sqlalchemy_columns: no model files in scope"]
    }

Note: this script uses a purpose-built output shape (lookups dict keyed by
detector name), NOT the canonical `{reviewer, findings, skipped, reason}`
envelope used by CLI-backed reviewers like visual_verify.py. The schemas
serve different purposes — reviewers produce findings for fix loops; this
produces reference facts for prompt injection.

Exit codes: 0 always (unless internal error = 2).
"""
from __future__ import annotations
import argparse
import ast
import fnmatch
import json
import re
import subprocess
import sys
from pathlib import Path


def _matches_any(file_path: str, patterns: list[str]) -> bool:
    """True if file_path matches any glob pattern (with or without leading dirs)."""
    for pat in patterns:
        if fnmatch.fnmatch(file_path, pat):
            return True
        # Also try matching without leading directories (glob anywhere in path)
        basename_pat = pat.split("/")[-1] if "/" in pat else pat
        if fnmatch.fnmatch(Path(file_path).name, basename_pat):
            # Only accept basename match if the directory prefix also matches
            pat_dir = "/".join(pat.split("/")[:-1])
            if not pat_dir or pat_dir in file_path:
                return True
    return False


def _any_match(patterns: list[str], files: list[str]) -> bool:
    return any(_matches_any(f, patterns) for f in files)


def _safe_resolve(project: Path, rel: str) -> Path | None:
    """Resolve `rel` inside `project`; return None if it would escape the root.

    Prevents `--files ../../etc/passwd` from reading outside the project.
    """
    try:
        candidate = (project / rel).resolve()
    except (OSError, ValueError):
        return None
    try:
        candidate.relative_to(project)
    except ValueError:
        return None
    return candidate


# ---- Detectors ----

def detect_alembic_heads(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["alembic/versions/*.py", "alembic/*.py", "alembic/versions/*"]
    if not _any_match(triggers, files):
        return None, "no alembic files in scope"
    if not (project / "alembic").exists():
        return None, "no alembic/ dir in project"
    try:
        result = subprocess.run(
            ["alembic", "heads"],
            cwd=str(project), capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            heads = result.stdout.strip() or "(no heads)"
            return f"Current alembic heads:\n{heads}", None
        return None, f"alembic CLI failed: {result.stderr.strip()[:200]}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return None, f"alembic CLI unavailable: {e}"


def detect_fastapi_routes(files: list[str], project: Path) -> tuple[str | None, str | None]:
    route_roots = ["app/routes", "routes", "app"]
    route_files: list[Path] = []
    for root in route_roots:
        root_path = project / root
        if root_path.exists() and root_path.is_dir():
            route_files.extend(root_path.rglob("*.py"))
    if not route_files:
        return None, "no route files found (checked app/routes, routes, app)"

    pattern = re.compile(
        r'@(?:router|app)\.(get|post|put|delete|patch|options|head)\(\s*["\']([^"\']+)["\']'
    )
    routes = []
    for path in route_files[:100]:
        try:
            text = path.read_text()
        except OSError:
            continue
        rel = str(path.relative_to(project))
        for m in pattern.finditer(text):
            routes.append(f"  {m.group(1).upper():<6} {m.group(2)}  ({rel})")
    if not routes:
        return None, "no @router/@app route decorators found"
    return "Existing routes (avoid conflicts):\n" + "\n".join(routes[:150]), None


def detect_sqlalchemy_columns(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["app/models/*.py", "models/*.py", "*/models/*.py"]
    matched = [f for f in files if _matches_any(f, triggers)]
    if not matched:
        return None, "no model files in scope"

    results = []
    for rel in matched:
        path = _safe_resolve(project, rel)
        if path is None or not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, OSError, ValueError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            cols = []
            for stmt in node.body:
                if not isinstance(stmt, ast.Assign):
                    continue
                for tgt in stmt.targets:
                    if not isinstance(tgt, ast.Name):
                        continue
                    if not isinstance(stmt.value, ast.Call):
                        continue
                    fn = stmt.value.func
                    is_column = (
                        (isinstance(fn, ast.Name) and fn.id == "Column")
                        or (isinstance(fn, ast.Attribute) and fn.attr == "Column")
                    )
                    if is_column:
                        cols.append(tgt.id)
            if cols:
                results.append(f"  {rel}::{node.name}: {', '.join(cols)}")
    if not results:
        return None, "no SQLAlchemy Column definitions found in scope files"
    return "Real model columns (use exactly these names):\n" + "\n".join(results), None


def detect_css_classes(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["*.css", "*.scss"]
    matched = [f for f in files if _matches_any(f, triggers)]
    if not matched:
        return None, "no CSS/SCSS files in scope"
    pattern = re.compile(r'\.([a-zA-Z_][\w-]*)\s*[,{:]')
    classes: set[str] = set()
    for rel in matched:
        path = _safe_resolve(project, rel)
        if path is None or not path.exists():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        classes.update(pattern.findall(text))
    if not classes:
        return None, "no CSS classes found in scope files"
    sorted_classes = sorted(classes)
    return (
        "Existing CSS classes in touched stylesheets (use exactly these names):\n"
        + ", ".join(sorted_classes[:100])
    ), None


def detect_react_components(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["*.tsx", "*.jsx"]
    matched = [f for f in files if _matches_any(f, triggers)]
    if not matched:
        return None, "no React files in scope"
    pattern = re.compile(r'export\s+(?:default\s+)?(?:function|const|class)\s+([A-Z]\w+)')
    comps = []
    for rel in matched:
        path = _safe_resolve(project, rel)
        if path is None or not path.exists():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        for name in pattern.findall(text):
            comps.append(f"  {name} — from {rel}")
    if not comps:
        return None, "no component exports found in scope files"
    return "Exported components (use exactly these names):\n" + "\n".join(comps[:80]), None


PLAN_DETECTORS = [
    ("alembic_heads", detect_alembic_heads),
    ("fastapi_routes", detect_fastapi_routes),
]
STEP_DETECTORS = [
    ("sqlalchemy_columns", detect_sqlalchemy_columns),
    ("css_classes", detect_css_classes),
    ("react_components", detect_react_components),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["plan", "step"], required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    detectors = PLAN_DETECTORS if args.scope == "plan" else STEP_DETECTORS

    lookups: dict[str, str] = {}
    skipped: list[str] = []
    for name, fn in detectors:
        try:
            result, skip_reason = fn(args.files, project)
        except Exception as e:
            skipped.append(f"{name}: detector error {type(e).__name__}: {e}")
            continue
        if result:
            lookups[name] = result
        elif skip_reason:
            skipped.append(f"{name}: {skip_reason}")

    out = {"scope": args.scope, "lookups": lookups, "skipped_detectors": skipped}
    if args.json:
        print(json.dumps(out))
    else:
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({
            "scope": "error",
            "lookups": {},
            "skipped_detectors": [f"internal: {type(e).__name__}: {e}"],
        }))
        sys.exit(2)
