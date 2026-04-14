"""Tests for mutation_check.py — the Phase 5 TDD discrimination gate.

Each test builds a tiny project in tmp_path with a target module + test file,
invokes mutation_check.py as a subprocess, and asserts on the JSON report.
"""

import json
import subprocess
import sys
import textwrap
from pathlib import Path

SCRIPT = Path(__file__).parent / "mutation_check.py"


def _run(new_tests, target_files, cwd):
    """Invoke mutation_check.py, return (exit_code, report_dict)."""
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--json",
            "--new-tests",
            *[str(p) for p in new_tests],
            "--target-files",
            *[str(p) for p in target_files],
        ],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        report = {"stdout": result.stdout, "stderr": result.stderr}
    return result.returncode, report


def test_strong_test_kills_mutation(tmp_path):
    """A test with real assertions should kill at least one mutation."""
    target = tmp_path / "calc.py"
    target.write_text(
        textwrap.dedent(
            """
            def is_adult(age):
                return age >= 18
            """
        ).strip()
    )
    test_file = tmp_path / "test_calc.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from calc import is_adult

            def test_is_adult_true():
                assert is_adult(20) is True

            def test_is_adult_false():
                assert is_adult(10) is False
            """
        ).strip()
    )

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0, f"expected pass, got {exit_code}: {report}"
    assert report["skipped"] is False
    assert report["non_discriminating"] == []
    # Both tests should discriminate
    assert all(o["discriminates"] for o in report["outcomes"])


def test_trivial_test_is_caught(tmp_path):
    """A test with no real assertion (assert True) must be flagged."""
    target = tmp_path / "calc.py"
    target.write_text(
        textwrap.dedent(
            """
            def is_adult(age):
                return age >= 18
            """
        ).strip()
    )
    test_file = tmp_path / "test_calc.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from calc import is_adult

            def test_is_adult_trivial():
                is_adult(20)  # calls target but asserts nothing meaningful
                assert True
            """
        ).strip()
    )

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 1, f"expected fail, got {exit_code}: {report}"
    assert len(report["non_discriminating"]) == 1
    assert "test_is_adult_trivial" in report["non_discriminating"][0][1]


def test_skip_when_non_python_target(tmp_path):
    """Non-python target → skip (exit 0, report.skipped True)."""
    target = tmp_path / "styles.css"
    target.write_text("body { color: red; }\n")
    test_file = tmp_path / "test_styles.py"
    test_file.write_text("def test_placeholder():\n    assert True\n")

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0
    assert report["skipped"] is True
    assert "non-python" in report["skip_reason"].lower()


def test_skip_when_no_target_identifiable(tmp_path):
    """Test file shares no identifiers with any def in target → skip."""
    target = tmp_path / "calc.py"
    target.write_text("def is_adult(age):\n    return age >= 18\n")
    test_file = tmp_path / "test_unrelated.py"
    test_file.write_text("def test_placeholder():\n    assert 1 + 1 == 2\n")

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0
    assert report["skipped"] is True
    assert "no target" in report["skip_reason"].lower()


def test_skip_when_no_mutable_operators(tmp_path):
    """Target function with nothing to mutate → skip, not fail."""
    target = tmp_path / "io_util.py"
    target.write_text(
        textwrap.dedent(
            """
            def greet(name):
                return f"hello {name}"
            """
        ).strip()
    )
    test_file = tmp_path / "test_io_util.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from io_util import greet

            def test_greet():
                assert greet("x") == "hello x"
            """
        ).strip()
    )

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0
    # Either skip (no mutations available) or pass with 0 mutations run
    if not report["skipped"]:
        assert all(o["total_mutations_run"] == 0 for o in report["outcomes"])


def test_no_new_tests_is_noop(tmp_path):
    """Empty --new-tests list → skip (pure refactor case)."""
    target = tmp_path / "calc.py"
    target.write_text("def is_adult(age):\n    return age >= 18\n")

    exit_code, report = _run([], [target], tmp_path)

    assert exit_code == 0
    assert report["skipped"] is True
    assert "no new tests" in report["skip_reason"].lower()


def test_is_none_discrimination(tmp_path):
    """A test asserting `is None` / `is not None` must be gated by the
    Is/IsNot cmpop mutation (fix for CodeRabbit finding #2)."""
    target = tmp_path / "opt.py"
    target.write_text(
        textwrap.dedent(
            """
            def is_missing(x):
                return x is None
            """
        ).strip()
    )
    test_file = tmp_path / "test_opt.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from opt import is_missing

            def test_missing_true():
                assert is_missing(None) is True

            def test_missing_false():
                assert is_missing(0) is False
            """
        ).strip()
    )

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0, f"expected pass, got {exit_code}: {report}"
    assert report["skipped"] is False
    assert all(o["total_mutations_run"] > 0 for o in report["outcomes"])
    assert all(o["discriminates"] for o in report["outcomes"])


def test_arithmetic_binop_mutation(tmp_path):
    """A test asserting `add(2, 3) == 5` should be gated by + → - mutation
    (fix for CodeRabbit finding #3)."""
    target = tmp_path / "math_util.py"
    target.write_text(
        textwrap.dedent(
            """
            def add(a, b):
                return a + b
            """
        ).strip()
    )
    test_file = tmp_path / "test_math_util.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from math_util import add

            def test_add():
                assert add(2, 3) == 5
            """
        ).strip()
    )

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0, f"expected pass, got {exit_code}: {report}"
    assert report["skipped"] is False
    assert report["outcomes"][0]["total_mutations_run"] > 0
    assert report["outcomes"][0]["discriminates"]


def test_class_method_vs_module_function_collision(tmp_path):
    """When a module-level `foo()` and a class method `C.foo()` share a name,
    both must be mutated independently (fix for CodeRabbit finding #1)."""
    target = tmp_path / "dual.py"
    target.write_text(
        textwrap.dedent(
            """
            def compute(x):
                return 0

            class Calculator:
                def compute(self, x):
                    return x * 2
            """
        ).strip()
    )
    test_file = tmp_path / "test_dual.py"
    test_file.write_text(
        textwrap.dedent(
            """
            from dual import Calculator

            def test_class_method():
                c = Calculator()
                assert c.compute(3) == 6
            """
        ).strip()
    )

    exit_code, report = _run([test_file], [target], tmp_path)

    assert exit_code == 0, f"expected pass, got {exit_code}: {report}"
    assert report["skipped"] is False
    # Post-fix: tool mutates BOTH defs; the class-method mutation (* → /)
    # makes the test fail, so discrimination is recorded.
    assert any(
        o["discriminates"] and o["total_mutations_run"] > 0 for o in report["outcomes"]
    ), f"did not discriminate any class-method mutation: {report}"
