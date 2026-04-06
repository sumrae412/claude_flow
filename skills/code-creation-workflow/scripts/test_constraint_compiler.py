"""test_constraint_compiler.py — TDD tests for constraint_compiler.py.

Run: /opt/homebrew/bin/python3.11 -m pytest test_constraint_compiler.py -v
"""

import json
import tempfile
from pathlib import Path

import pytest

from constraint_compiler import (
    Constraint,
    compile_from_file,
    compile_from_architecture,
    compile_from_build_state,
    merge_constraint_sets,
    to_json,
    from_json,
)


# ---------------------------------------------------------------------------
# Constraint dataclass
# ---------------------------------------------------------------------------

class TestConstraint:
    def test_hard_constraint_fields(self):
        c = Constraint(
            id="c1",
            type="hard",
            check="grep",
            pattern="@auth_required",
            scope="routes/*.py",
            message="All routes must have @auth_required",
            source="CLAUDE.md",
        )
        assert c.id == "c1"
        assert c.type == "hard"
        assert c.check == "grep"
        assert c.pattern == "@auth_required"
        assert c.scope == "routes/*.py"
        assert c.message == "All routes must have @auth_required"
        assert c.source == "CLAUDE.md"

    def test_soft_constraint_uses_rule(self):
        c = Constraint(
            id="c2",
            type="soft",
            rule="All data access through repository classes",
            source="architecture-decision",
        )
        assert c.type == "soft"
        assert c.rule == "All data access through repository classes"
        # check/pattern/scope not required for soft
        assert c.check is None
        assert c.pattern is None

    def test_defaults(self):
        c = Constraint(id="x", type="soft", rule="use repos")
        assert c.scope is None
        assert c.message is None
        assert c.source is None
        assert c.check is None
        assert c.pattern is None


# ---------------------------------------------------------------------------
# to_json / from_json
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_hard_constraint_round_trip(self):
        c = Constraint(
            id="c1",
            type="hard",
            check="grep",
            pattern="@auth_required",
            scope="routes/*.py",
            message="Must have auth",
            source="CLAUDE.md",
        )
        serialized = to_json([c])
        data = json.loads(serialized)
        assert len(data["constraints"]) == 1
        assert data["constraints"][0]["id"] == "c1"

    def test_from_json_round_trip(self):
        constraints = [
            Constraint(id="c1", type="hard", check="grep", pattern="foo", scope="*.py", message="msg", source="src"),
            Constraint(id="c2", type="soft", rule="use repos", source="arch"),
        ]
        serialized = to_json(constraints)
        restored = from_json(serialized)
        assert len(restored) == 2
        assert restored[0].id == "c1"
        assert restored[0].type == "hard"
        assert restored[1].id == "c2"
        assert restored[1].type == "soft"
        assert restored[1].rule == "use repos"

    def test_empty_list(self):
        s = to_json([])
        assert from_json(s) == []


# ---------------------------------------------------------------------------
# compile_from_file
# ---------------------------------------------------------------------------

class TestCompileFromFile:
    def _write_md(self, tmp_path: Path, content: str) -> Path:
        p = tmp_path / "CLAUDE.md"
        p.write_text(content)
        return p

    def test_extracts_rules_from_markdown(self, tmp_path):
        content = """# Project Rules

- All routes must use @auth_required decorator.
- Never use bare except clauses.
- Always validate input with pydantic.
- Use Decimal for monetary amounts.
"""
        p = self._write_md(tmp_path, content)
        constraints = compile_from_file(str(p), "CLAUDE.md")
        assert len(constraints) >= 2
        # All should have source set
        for c in constraints:
            assert c.source == "CLAUDE.md"
            assert c.id is not None

    def test_grep_pattern_becomes_hard_constraint(self, tmp_path):
        content = """- All routes must have @auth_required."""
        p = self._write_md(tmp_path, content)
        constraints = compile_from_file(str(p), "CLAUDE.md")
        # @auth_required is a grep-able pattern → should produce at least one hard constraint
        hard = [c for c in constraints if c.type == "hard"]
        assert len(hard) >= 1

    def test_design_rule_becomes_soft_constraint(self, tmp_path):
        content = """- Always use repository classes for data access."""
        p = self._write_md(tmp_path, content)
        constraints = compile_from_file(str(p), "CLAUDE.md")
        soft = [c for c in constraints if c.type == "soft"]
        assert len(soft) >= 1

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            compile_from_file(str(tmp_path / "nonexistent.md"), "src")

    def test_non_imperative_lines_skipped(self, tmp_path):
        content = """# Title

This is just a description of the project.
It explains the background context.
"""
        p = self._write_md(tmp_path, content)
        constraints = compile_from_file(str(p), "CLAUDE.md")
        # Should produce few or no constraints (no imperative keywords)
        assert len(constraints) == 0


# ---------------------------------------------------------------------------
# compile_from_architecture
# ---------------------------------------------------------------------------

class TestCompileFromArchitecture:
    def test_extracts_design_rules(self):
        arch_text = """
## Architecture Decision

All data access must go through repository classes.
Services must never query the database directly.
Amount fields should use Decimal type.
"""
        constraints = compile_from_architecture(arch_text)
        assert len(constraints) >= 1
        for c in constraints:
            assert c.source == "architecture-decision"
            assert c.type in ("hard", "soft")

    def test_returns_empty_for_blank_text(self):
        assert compile_from_architecture("") == []
        assert compile_from_architecture("   ") == []


# ---------------------------------------------------------------------------
# compile_from_build_state
# ---------------------------------------------------------------------------

class TestCompileFromBuildState:
    def test_extracts_from_decisions_made(self):
        build_state = {
            "steps": {
                "step_1": {
                    "decisions_made": ["Use Decimal for all monetary amounts"],
                    "failed_approaches": [],
                }
            }
        }
        constraints = compile_from_build_state(build_state)
        assert len(constraints) >= 1
        assert any(c.source == "build-state" for c in constraints)

    def test_extracts_from_failed_approaches(self):
        build_state = {
            "steps": {
                "step_2": {
                    "decisions_made": [],
                    "failed_approaches": ["Raw SQL bypasses ORM events"],
                }
            }
        }
        constraints = compile_from_build_state(build_state)
        assert len(constraints) >= 1

    def test_empty_build_state_returns_empty(self):
        assert compile_from_build_state({}) == []
        assert compile_from_build_state({"steps": {}}) == []


# ---------------------------------------------------------------------------
# merge_constraint_sets
# ---------------------------------------------------------------------------

class TestMergeConstraintSets:
    def test_deduplicates_by_content(self):
        c1 = Constraint(id="a1", type="soft", rule="use repos", source="arch")
        c2 = Constraint(id="a2", type="soft", rule="use repos", source="build-state")
        merged = merge_constraint_sets([[c1], [c2]])
        # Same rule → deduplicated to 1
        assert len(merged) == 1

    def test_keeps_different_rules(self):
        c1 = Constraint(id="a", type="soft", rule="use repos", source="arch")
        c2 = Constraint(id="b", type="soft", rule="use Decimal", source="arch")
        merged = merge_constraint_sets([[c1], [c2]])
        assert len(merged) == 2

    def test_hard_constraint_preferred_over_soft_duplicate(self):
        c_soft = Constraint(id="s1", type="soft", rule="@auth_required", source="manual")
        c_hard = Constraint(id="h1", type="hard", check="grep", pattern="@auth_required",
                            scope="*.py", message="auth required", source="CLAUDE.md",
                            rule="@auth_required")
        merged = merge_constraint_sets([[c_soft], [c_hard]])
        assert len(merged) == 1
        assert merged[0].type == "hard"

    def test_empty_sets(self):
        assert merge_constraint_sets([]) == []
        assert merge_constraint_sets([[], []]) == []
