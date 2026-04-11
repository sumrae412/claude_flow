#!/usr/bin/env python3
"""Tests for pattern-detector."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


def _load_with_tmpdir(tmpdir: Path):
    """Load pattern-detector with CLAUDE_FLOW_DIR set to tmpdir."""
    os.environ["CLAUDE_FLOW_DIR"] = str(tmpdir)
    (tmpdir / "memory" / "episodic").mkdir(parents=True, exist_ok=True)
    (tmpdir / "memory" / "semantic").mkdir(parents=True, exist_ok=True)
    (tmpdir / "memory" / "procedural").mkdir(parents=True, exist_ok=True)
    # Force reload to pick up env var
    spec = importlib.util.spec_from_file_location(
        "pd", Path(__file__).parent / "pattern-detector.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_repeated_failure_below_threshold():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)
        events = [
            {"session_id": "a", "error_class": "foo"},
            {"session_id": "b", "error_class": "foo"},
        ]
        proposals = pd.detect_repeated_failures(events)
        assert proposals == []


def test_repeated_failure_meets_threshold():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)
        events = [
            {"session_id": "a", "error_class": "foo"},
            {"session_id": "b", "error_class": "foo"},
            {"session_id": "c", "error_class": "foo"},
        ]
        proposals = pd.detect_repeated_failures(events)
        assert len(proposals) == 1
        assert proposals[0]["trigger"] == "repeated_failure"
        assert proposals[0]["evidence"]["error_class"] == "foo"
        assert proposals[0]["evidence"]["occurrences"] == 3
        assert proposals[0]["confidence"] >= 0.5


def test_repeated_failure_needs_session_diversity():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)
        # 5 occurrences but only 2 sessions — should NOT trigger
        events = [{"session_id": "a", "error_class": "foo"}] * 3 + \
                 [{"session_id": "b", "error_class": "foo"}] * 2
        proposals = pd.detect_repeated_failures(events)
        assert proposals == []


def test_high_retry_domain():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)
        # 4/5 attempts retried → 80% rate over 5 attempts
        events = [
            {"domain": "migrations", "phase5_retries": 1},
            {"domain": "migrations", "phase5_retries": 2},
            {"domain": "migrations", "phase5_retries": 1},
            {"domain": "migrations", "phase5_retries": 0},
            {"domain": "migrations", "phase5_retries": 3},
        ]
        proposals = pd.detect_high_retry_domains(events)
        assert len(proposals) == 1
        assert proposals[0]["trigger"] == "high_retry_domain"
        assert proposals[0]["evidence"]["domain"] == "migrations"
        assert proposals[0]["evidence"]["retry_rate"] == 0.8


def test_high_retry_domain_below_min_attempts():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)
        # Only 3 attempts — under threshold
        events = [
            {"domain": "migrations", "phase5_retries": 1},
            {"domain": "migrations", "phase5_retries": 1},
            {"domain": "migrations", "phase5_retries": 1},
        ]
        proposals = pd.detect_high_retry_domains(events)
        assert proposals == []


def test_domain_target_mapping():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)
        assert "defensive-backend" in pd.target_for_domain("routes")
        assert "defensive-ui" in pd.target_for_domain("ui")
        assert pd.target_for_domain(None) == pd.DEFAULT_TARGET
        assert pd.target_for_domain("unknown") == pd.DEFAULT_TARGET


def test_detect_all_dedupes():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)

        # Pre-populate proposals file with an existing fingerprint
        existing = {
            "id": "prop-old-001",
            "trigger": "repeated_failure",
            "evidence_fingerprint": "repeated_failure:foo",
            "status": "pending",
        }
        (tmpdir / "memory" / "procedural" / "proposed-skill-updates.jsonl").write_text(json.dumps(existing) + "\n")

        # Write failure events matching the existing fingerprint
        failures = [
            {"session_id": "a", "error_class": "foo"},
            {"session_id": "b", "error_class": "foo"},
            {"session_id": "c", "error_class": "foo"},
        ]
        (tmpdir / "memory" / "episodic" / "failure-events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in failures)
        )

        new = pd.detect_all()
        assert new == []  # Deduped


def test_detect_all_emits_new_proposals():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        pd = _load_with_tmpdir(tmpdir)

        failures = [
            {"session_id": "a", "error_class": "novel_error"},
            {"session_id": "b", "error_class": "novel_error"},
            {"session_id": "c", "error_class": "novel_error"},
        ]
        (tmpdir / "memory" / "episodic" / "failure-events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in failures)
        )

        new = pd.detect_all()
        assert len(new) == 1
        assert new[0]["status"] == "pending"
        assert new[0]["id"].startswith("prop-")
        assert new[0]["detected_at"]


if __name__ == "__main__":
    import inspect
    tests = [fn for name, fn in globals().items()
             if name.startswith("test_") and inspect.isfunction(fn)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"✓ {t.__name__}")
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
