#!/usr/bin/env python3
"""Mutation-based test discrimination gate for Phase 5 TDD.

For each new test, mutate its target function(s) one operator at a time and
verify that at least one mutation causes the test to FAIL. A test that passes
under every mutation is non-discriminating (e.g., `assert True`, weak
assertions) and should be rejected.

Inspired by: Scaling Coding Agents via Atomic Skills (arXiv:2604.05013) — unit
tests only earn reward when they pass original code AND fail injected bugs.

Usage:
    python scripts/mutation_check.py \\
        --new-tests tests/test_foo.py tests/test_bar.py \\
        --target-files src/foo.py src/bar.py \\
        [--json]

Exit codes:
    0 — all new tests discriminate OR skip conditions met (non-python,
        no target, no new tests, pytest unavailable)
    1 — one or more new tests failed to kill any mutation
    2 — internal error

Skip semantics: this is a lite gate. When we cannot run meaningfully (wrong
language, no targets, env missing), we emit skip and exit 0 rather than block
the workflow. Silence-on-failure is worse than silence-on-inapplicability.
"""

from __future__ import annotations

import argparse
import ast
import copy
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

PASS_EXIT = 0
FAIL_EXIT = 1
ERROR_EXIT = 2

# Cap on mutations per target function so perf doesn't blow up on large bodies.
MAX_MUTATIONS_PER_TARGET = 12


@dataclass
class TestOutcome:
    test_file: str
    test_name: str
    target: str
    total_mutations_run: int = 0
    killed_mutations: int = 0
    discriminates: bool = False


@dataclass
class Report:
    skipped: bool = False
    skip_reason: str = ""
    outcomes: list = field(default_factory=list)
    non_discriminating: list = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(
            {
                "skipped": self.skipped,
                "skip_reason": self.skip_reason,
                "outcomes": [asdict(o) for o in self.outcomes],
                "non_discriminating": self.non_discriminating,
            },
            indent=2,
        )


# -------------------- target identification --------------------


def extract_defs(py_path: Path) -> set[str]:
    """Return the set of top-level + method names defined in py_path."""
    try:
        tree = ast.parse(py_path.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def extract_identifiers(py_path: Path) -> set[str]:
    """Return identifier-like tokens appearing in py_path source."""
    try:
        text = py_path.read_text()
    except (UnicodeDecodeError, OSError):
        return set()
    return set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", text))


def find_targets(test_files: list[Path], target_files: list[Path]) -> list[tuple[Path, str]]:
    """For each (test_file, target_file), return (target_file, def_name) pairs
    where def_name appears in the test file.

    Heuristic C per the design doc — grep-based, fast, good-enough.
    """
    pairs: list[tuple[Path, str]] = []
    for tf in test_files:
        test_identifiers = extract_identifiers(tf)
        for src in target_files:
            for def_name in extract_defs(src):
                if def_name in test_identifiers:
                    pairs.append((src, def_name))
    # Deduplicate while preserving order
    seen = set()
    unique: list[tuple[Path, str]] = []
    for pair in pairs:
        key = (str(pair[0]), pair[1])
        if key not in seen:
            seen.add(key)
            unique.append(pair)
    return unique


# -------------------- mutation operators --------------------


# Each operator returns a NEW node or None (to leave unchanged).
# We walk the tree, collect mutation sites, then produce one mutated tree per site.


def _flip_cmpop(op: ast.cmpop):
    mapping = {
        ast.Eq: ast.NotEq,
        ast.NotEq: ast.Eq,
        ast.Lt: ast.GtE,
        ast.GtE: ast.Lt,
        ast.LtE: ast.Gt,
        ast.Gt: ast.LtE,
    }
    cls = mapping.get(type(op))
    return cls() if cls else None


def _flip_boolop(op: ast.boolop):
    mapping = {ast.And: ast.Or, ast.Or: ast.And}
    cls = mapping.get(type(op))
    return cls() if cls else None


def _bump_constant(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    return None  # strings/floats/None — skip for v1


def collect_mutation_sites(func_node: ast.AST) -> list[tuple[str, callable]]:
    """Walk func_node; return list of (description, mutator) pairs.

    Each mutator takes (tree_copy) and applies one mutation in place.
    """
    sites: list[tuple[str, callable]] = []

    # Locate each mutable node by path (list of (attr, index|None) from root).
    # Then the mutator descends the copy along the same path and swaps in place.

    def record(path, desc, make_replacement):
        sites.append((desc, lambda tree: _apply_at_path(tree, path, make_replacement)))

    def walk(node, path):
        # Compare: each op in node.ops is mutable
        if isinstance(node, ast.Compare):
            for i, op in enumerate(node.ops):
                flipped = _flip_cmpop(op)
                if flipped is not None:
                    record(path + [("ops", i)], f"flip-cmpop({type(op).__name__})", lambda _old, f=flipped: f)
        # BoolOp
        if isinstance(node, ast.BoolOp):
            flipped = _flip_boolop(node.op)
            if flipped is not None:
                record(path + [("op", None)], f"flip-boolop({type(node.op).__name__})", lambda _old, f=flipped: f)
        # Constant (True/False/int)
        if isinstance(node, ast.Constant):
            bumped = _bump_constant(node.value)
            if bumped is not None:
                record(path, f"const({node.value}->{bumped})", lambda _old, b=bumped: ast.copy_location(ast.Constant(value=b), _old))
        # UnaryOp `not x` → drop the not
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            operand = node.operand
            record(path, "drop-not", lambda _old, o=operand: o)

        # Recurse into child fields
        for field_name, value in ast.iter_fields(node):
            if isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, ast.AST):
                        walk(item, path + [(field_name, i)])
            elif isinstance(value, ast.AST):
                walk(value, path + [(field_name, None)])

    walk(func_node, [])
    return sites[:MAX_MUTATIONS_PER_TARGET]


def _apply_at_path(tree, path, make_replacement):
    """Descend into tree along path; replace final node via make_replacement(old)."""
    if not path:
        return make_replacement(tree)
    node = tree
    for attr, idx in path[:-1]:
        value = getattr(node, attr)
        if idx is not None:
            node = value[idx]
        else:
            node = value
    attr, idx = path[-1]
    value = getattr(node, attr)
    if idx is not None:
        old = value[idx]
        value[idx] = make_replacement(old)
    else:
        old = value
        setattr(node, attr, make_replacement(old))
    return tree


def generate_mutants(src_tree: ast.Module, target_def_name: str):
    """Yield (description, mutated_source_string) for each single-mutation variant
    of the target function inside src_tree."""
    # Find the target function def
    for node in ast.walk(src_tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == target_def_name:
            sites = collect_mutation_sites(node)
            for desc, mutator in sites:
                tree_copy = copy.deepcopy(src_tree)
                # Find the corresponding func in the copy and mutate it
                for copy_node in ast.walk(tree_copy):
                    if (
                        isinstance(copy_node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and copy_node.name == target_def_name
                    ):
                        mutator(copy_node)
                        break
                try:
                    yield desc, ast.unparse(tree_copy)
                except (ValueError, AttributeError):
                    continue
            break


# -------------------- test discovery + pytest runner --------------------


def discover_test_names(test_file: Path) -> list[str]:
    try:
        tree = ast.parse(test_file.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []
    names = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            names.append(node.name)
    return names


def pytest_available() -> bool:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def run_test(test_file: Path, test_name: str, cwd: Path, env: dict) -> bool:
    """Return True if the test passes, False if it fails."""
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            f"{test_file}::{test_name}",
            "-x",
            "--no-header",
            "-q",
            "--tb=no",
            "-p",
            "no:cacheprovider",
        ],
        cwd=cwd,
        env=env,
        capture_output=True,
        timeout=30,
    )
    return result.returncode == 0


# -------------------- orchestration --------------------


def check_test_against_mutations(
    test_file: Path,
    test_name: str,
    target_file: Path,
    target_def: str,
    cwd: Path,
) -> TestOutcome:
    """Run the test against each mutation of target_def; return outcome."""
    outcome = TestOutcome(
        test_file=str(test_file),
        test_name=test_name,
        target=f"{target_file.name}::{target_def}",
    )
    try:
        src_tree = ast.parse(target_file.read_text())
    except (SyntaxError, UnicodeDecodeError, OSError):
        return outcome

    original_text = target_file.read_text()
    env = {**os.environ, "PYTHONPATH": f"{cwd}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}

    try:
        for _desc, mutated_src in generate_mutants(src_tree, target_def):
            outcome.total_mutations_run += 1
            target_file.write_text(mutated_src)
            try:
                passed = run_test(test_file, test_name, cwd, env)
            except subprocess.TimeoutExpired:
                continue
            if not passed:
                outcome.killed_mutations += 1
                outcome.discriminates = True
                # Early-exit: one kill is enough per the paper's rule.
                break
    finally:
        target_file.write_text(original_text)

    return outcome


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--new-tests", nargs="*", default=[], help="Paths to new/modified test files")
    parser.add_argument("--target-files", nargs="*", default=[], help="Paths to modified production files")
    parser.add_argument("--json", action="store_true", help="Emit JSON report to stdout")
    args = parser.parse_args()

    report = Report()

    # Skip: no new tests
    if not args.new_tests:
        report.skipped = True
        report.skip_reason = "no new tests supplied (pure refactor or no test changes)"
        _emit(report, args.json)
        return PASS_EXIT

    test_paths = [Path(p) for p in args.new_tests]
    target_paths = [Path(p) for p in args.target_files]

    # Skip: non-python targets (any non-.py target means we can't mutate uniformly)
    python_targets = [p for p in target_paths if p.suffix == ".py"]
    if target_paths and not python_targets:
        report.skipped = True
        report.skip_reason = "non-python targets only — mutation gate is python-only in v1"
        _emit(report, args.json)
        return PASS_EXIT

    # Skip: no pytest available
    if not pytest_available():
        report.skipped = True
        report.skip_reason = "pytest not available in current interpreter"
        _emit(report, args.json)
        return PASS_EXIT

    # Find target pairs (def_name ∈ test identifiers)
    pairs = find_targets(test_paths, python_targets)
    if not pairs:
        report.skipped = True
        report.skip_reason = "no target functions identifiable from new tests"
        _emit(report, args.json)
        return PASS_EXIT

    # Work in a tmp copy of the cwd so we never actually mutate real files on disk.
    # But targets need to be importable by the tests — easiest is to operate in-place
    # with a finally-restore. That's what check_test_against_mutations does.
    cwd = test_paths[0].parent.resolve()

    # For each new test × target pairing in the same directory, run the check.
    for test_file in test_paths:
        test_names = discover_test_names(test_file)
        test_identifiers = extract_identifiers(test_file)
        for target_file, target_def in pairs:
            if target_def not in test_identifiers:
                continue  # Test doesn't reference this def
            for test_name in test_names:
                # Only associate tests that mention the target def in their own body,
                # OR any test in a file where the def appears (v1 simplification).
                outcome = check_test_against_mutations(
                    test_file, test_name, target_file, target_def, cwd
                )
                report.outcomes.append(outcome)
                if not outcome.discriminates and outcome.total_mutations_run > 0:
                    report.non_discriminating.append([str(test_file), test_name])

    # If every test either ran zero mutations (nothing to mutate) or killed ≥1,
    # we pass. Non-discriminating = ran mutations but killed none.
    _emit(report, args.json)
    return FAIL_EXIT if report.non_discriminating else PASS_EXIT


def _emit(report: Report, as_json: bool) -> None:
    if as_json:
        print(report.to_json())
    else:
        if report.skipped:
            print(f"SKIP: {report.skip_reason}")
        elif report.non_discriminating:
            print(f"FAIL: {len(report.non_discriminating)} non-discriminating test(s):")
            for tf, tn in report.non_discriminating:
                print(f"  - {tf}::{tn}")
        else:
            print(f"PASS: {len(report.outcomes)} outcome(s) checked, all discriminate")


if __name__ == "__main__":
    sys.exit(main())
