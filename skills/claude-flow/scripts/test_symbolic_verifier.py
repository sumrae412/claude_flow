"""test_symbolic_verifier.py — TDD tests for symbolic_verifier.py.

Run: /opt/homebrew/bin/python3.11 -m pytest test_symbolic_verifier.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from constraint_compiler import Constraint
from symbolic_verifier import (
    VerificationResult,
    run_hard_check,
    run_soft_check,
    verify_output,
    format_violations_for_retry,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _write_py(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content)
    return p


def _grep_constraint(pattern: str, scope: str = "*.py") -> Constraint:
    return Constraint(
        id=f"c-{pattern[:10]}",
        type="hard",
        check="grep",
        pattern=pattern,
        scope=scope,
        message=f"Pattern '{pattern}' required",
        source="test",
    )


def _soft_constraint(rule: str) -> Constraint:
    return Constraint(
        id="soft-1",
        type="soft",
        rule=rule,
        source="architecture-decision",
    )


# ---------------------------------------------------------------------------
# run_hard_check
# ---------------------------------------------------------------------------

class TestRunHardCheck:
    def test_grep_pass_when_pattern_present(self, tmp_path):
        f = _write_py(tmp_path, "routes.py", "def endpoint():\n    @auth_required\n    pass\n")
        c = _grep_constraint("@auth_required")
        passed, details = run_hard_check(c, str(f))
        assert passed is True
        assert details is not None

    def test_grep_fail_when_pattern_absent(self, tmp_path):
        f = _write_py(tmp_path, "routes.py", "def endpoint():\n    pass\n")
        c = _grep_constraint("@auth_required")
        passed, details = run_hard_check(c, str(f))
        assert passed is False
        assert "auth_required" in details or "pattern" in details.lower()

    def test_regex_check_type(self, tmp_path):
        # 'regex' check type should also work (pattern match)
        f = _write_py(tmp_path, "code.py", "amount = 3.14\n")
        c = Constraint(
            id="regex-1",
            type="hard",
            check="regex",
            pattern=r"amount\s*=\s*\d+\.\d+",
            scope="*.py",
            message="float amount found",
            source="test",
        )
        passed, details = run_hard_check(c, str(f))
        assert passed is True

    def test_nonexistent_file_returns_fail(self, tmp_path):
        c = _grep_constraint("@auth")
        passed, details = run_hard_check(c, str(tmp_path / "no_such_file.py"))
        assert passed is False

    def test_returns_tuple_of_two(self, tmp_path):
        f = _write_py(tmp_path, "x.py", "x = 1")
        c = _grep_constraint("x")
        result = run_hard_check(c, str(f))
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# run_soft_check
# ---------------------------------------------------------------------------

class TestRunSoftCheck:
    def test_llm_yes_returns_fail(self):
        mock_llm = MagicMock()
        mock_llm.check.return_value = "YES: The code uses raw SQL instead of repository classes."
        c = _soft_constraint("All data access through repository classes")
        passed, desc = run_soft_check(c, "db.execute('SELECT * FROM users')", mock_llm)
        assert passed is False
        assert len(desc) > 0

    def test_llm_no_returns_pass(self):
        mock_llm = MagicMock()
        mock_llm.check.return_value = "NO"
        c = _soft_constraint("All data access through repository classes")
        passed, desc = run_soft_check(c, "repo.get_users()", mock_llm)
        assert passed is True

    def test_llm_called_with_rule_and_diff(self):
        mock_llm = MagicMock()
        mock_llm.check.return_value = "NO"
        c = _soft_constraint("Use Decimal for amounts")
        run_soft_check(c, "price = 9.99", mock_llm)
        mock_llm.check.assert_called_once()
        call_args = mock_llm.check.call_args
        # The call should contain the rule text somewhere
        prompt_text = str(call_args)
        assert "Decimal" in prompt_text or "amounts" in prompt_text.lower()

    def test_returns_tuple_of_two(self):
        mock_llm = MagicMock()
        mock_llm.check.return_value = "NO"
        c = _soft_constraint("use repos")
        result = run_soft_check(c, "repo.get()", mock_llm)
        assert isinstance(result, tuple)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# VerificationResult
# ---------------------------------------------------------------------------

class TestVerificationResult:
    def test_all_pass(self):
        vr = VerificationResult(passed=True, violations=[], checked=3)
        assert vr.passed is True
        assert vr.violations == []
        assert vr.checked == 3

    def test_violations_present(self):
        vr = VerificationResult(
            passed=False,
            violations=[{"id": "c1", "message": "Missing auth"}],
            checked=2,
        )
        assert vr.passed is False
        assert len(vr.violations) == 1


# ---------------------------------------------------------------------------
# verify_output
# ---------------------------------------------------------------------------

class TestVerifyOutput:
    def test_all_hard_pass_returns_clean(self, tmp_path):
        f = _write_py(tmp_path, "routes.py", "def fn():\n    @auth_required\n    pass\n")
        c = _grep_constraint("@auth_required")
        mock_llm = MagicMock()
        result = verify_output([c], [str(f)], mock_llm)
        assert result.passed is True
        assert len(result.violations) == 0

    def test_hard_fail_recorded_as_violation(self, tmp_path):
        f = _write_py(tmp_path, "routes.py", "def fn():\n    pass\n")
        c = _grep_constraint("@auth_required")
        mock_llm = MagicMock()
        result = verify_output([c], [str(f)], mock_llm)
        assert result.passed is False
        assert len(result.violations) == 1
        assert result.violations[0]["id"] == c.id

    def test_soft_violation_recorded(self, tmp_path):
        f = _write_py(tmp_path, "service.py", "db.execute('SELECT 1')")
        c = _soft_constraint("All data access through repository classes")
        mock_llm = MagicMock()
        mock_llm.check.return_value = "YES: Raw SQL used."
        result = verify_output([c], [str(f)], mock_llm)
        assert result.passed is False
        assert len(result.violations) == 1

    def test_checked_count_matches_applicable_constraints(self, tmp_path):
        f = _write_py(tmp_path, "x.py", "@auth_required\nx = 1")
        constraints = [
            _grep_constraint("@auth_required"),
            _grep_constraint("x"),
        ]
        mock_llm = MagicMock()
        result = verify_output(constraints, [str(f)], mock_llm)
        assert result.checked == 2

    def test_empty_constraints_returns_pass(self, tmp_path):
        f = _write_py(tmp_path, "x.py", "x = 1")
        mock_llm = MagicMock()
        result = verify_output([], [str(f)], mock_llm)
        assert result.passed is True
        assert result.checked == 0


# ---------------------------------------------------------------------------
# format_violations_for_retry
# ---------------------------------------------------------------------------

class TestFormatViolationsForRetry:
    def test_empty_violations(self):
        output = format_violations_for_retry([])
        assert isinstance(output, str)

    def test_single_violation_in_output(self):
        violations = [
            {"id": "c1", "message": "Missing @auth_required", "file": "routes.py", "type": "hard"}
        ]
        output = format_violations_for_retry(violations)
        assert "auth_required" in output
        assert "c1" in output

    def test_multiple_violations_all_included(self):
        violations = [
            {"id": "c1", "message": "Missing auth", "file": "f1.py", "type": "hard"},
            {"id": "c2", "message": "Raw SQL used", "file": "f2.py", "type": "soft"},
        ]
        output = format_violations_for_retry(violations)
        assert "c1" in output
        assert "c2" in output
        assert "CONSTRAINT VIOLATIONS" in output.upper() or "violation" in output.lower()

    def test_retry_prompt_contains_instructions(self):
        violations = [{"id": "c1", "message": "Bad code", "file": "x.py", "type": "hard"}]
        output = format_violations_for_retry(violations)
        # Should contain actionable language
        assert len(output) > 50
