"""Tests for audit_phase3_questions.py — classify lookup vs intent questions."""
import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[3] / "skills" / "claude-flow" / "scripts" / "audit_phase3_questions.py"


def run(questions):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        input=json.dumps(questions),
        capture_output=True, text=True, timeout=30,
    )
    return result


def _classify(questions):
    result = run(questions)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_output_shape():
    data = _classify(["What should the error say?"])
    assert "questions" in data
    assert "summary" in data
    for q in data["questions"]:
        assert "question" in q
        assert "self_answerable" in q
        assert "reason" in q
    assert "total" in data["summary"]
    assert "self_answerable" in data["summary"]
    assert "user_facing" in data["summary"]


def test_file_existence_flagged_self_answerable():
    data = _classify(["Does the file app/models/user.py exist?"])
    assert data["questions"][0]["self_answerable"] is True
    assert data["questions"][0]["suggested_lookup"] is not None


def test_column_question_flagged_self_answerable():
    data = _classify(["What columns does the Client model have?"])
    assert data["questions"][0]["self_answerable"] is True


def test_alembic_question_flagged_self_answerable():
    data = _classify(["What is the current migration head?"])
    assert data["questions"][0]["self_answerable"] is True
    assert "alembic" in data["questions"][0]["suggested_lookup"].lower()


def test_user_intent_never_self_answerable():
    data = _classify([
        "Should the signup flow send a welcome email?",
        "What should the error message say?",
        "Which design approach do you prefer?",
        "How should we handle the edge case of empty input?",
    ])
    for q in data["questions"]:
        assert q["self_answerable"] is False, f"intent question wrongly flagged: {q['question']}"


def test_mixed_list_classifies_correctly():
    data = _classify([
        "Does app/models/user.py exist?",          # self-answerable
        "Should we cache the query results?",       # user intent
        "What columns does User have?",             # self-answerable
        "How should we handle validation errors?",  # user intent (edge case)
    ])
    assert data["summary"]["total"] == 4
    assert data["summary"]["self_answerable"] == 2
    assert data["summary"]["user_facing"] == 2


def test_ambiguous_defaults_to_user_facing():
    """Conservative: if no pattern matches, leave as user-facing."""
    data = _classify(["Tell me about the feature."])
    assert data["questions"][0]["self_answerable"] is False


def test_intent_pattern_beats_lookup_pattern():
    """'Should we use columns X, Y, Z?' — has 'columns' but also 'should', intent wins."""
    data = _classify(["Should we add new columns to the User model?"])
    assert data["questions"][0]["self_answerable"] is False


def test_invalid_json_returns_exit_2():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        input="not json",
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2


def test_non_array_input_returns_exit_2():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        input='{"not": "array"}',
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 2
