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
