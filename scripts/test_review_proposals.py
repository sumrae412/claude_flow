#!/usr/bin/env python3
"""Tests for review-proposals CLI."""
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path


def _load_with_tmpdir(tmpdir: Path):
    os.environ["CLAUDE_FLOW_DIR"] = str(tmpdir)
    (tmpdir / "memory").mkdir(parents=True, exist_ok=True)
    spec = importlib.util.spec_from_file_location(
        "rp", Path(__file__).parent / "review-proposals.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sample_proposal(pid="prop-001", status="pending", content=None):
    return {
        "id": pid,
        "detected_at": "2026-04-07T12:00:00Z",
        "trigger": "repeated_failure",
        "evidence": {"error_class": "foo", "occurrences": 3},
        "proposed_action": "add_defensive_pattern",
        "target_file": "skills/test-skill/SKILL.md",
        "content_stub": "test stub",
        "content": content,
        "confidence": 0.8,
        "status": status,
        "applied_at": None,
        "rejected_at": None,
        "reject_reason": None,
        "evidence_fingerprint": "repeated_failure:foo",
    }


def test_load_save_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        rp.save_proposals([_sample_proposal()])
        loaded = rp.load_proposals()
        assert len(loaded) == 1
        assert loaded[0]["id"] == "prop-001"


def test_reject_marks_status():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        rp.save_proposals([_sample_proposal()])
        rc = rp.cmd_reject("prop-001", "not applicable")
        assert rc == 0
        loaded = rp.load_proposals()
        assert loaded[0]["status"] == "rejected"
        assert loaded[0]["reject_reason"] == "not applicable"
        assert loaded[0]["rejected_at"] is not None


def test_reject_nonexistent():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        rp.save_proposals([_sample_proposal()])
        rc = rp.cmd_reject("prop-nope", "reason")
        assert rc == 1


def test_apply_without_content_fails():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        # Create a target file
        target = tmpdir / "skills" / "test-skill" / "SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Existing\n")
        rp.save_proposals([_sample_proposal()])  # content=None
        rc = rp.cmd_apply("prop-001")
        assert rc == 1


def test_apply_happy_path():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        target = tmpdir / "skills" / "test-skill" / "SKILL.md"
        target.parent.mkdir(parents=True)
        target.write_text("# Existing content\n")
        rp.save_proposals([_sample_proposal(content="## New Pattern\n\nAlways do X.\n")])

        rc = rp.cmd_apply("prop-001")
        assert rc == 0

        # Target file updated
        updated = target.read_text()
        assert "# Existing content" in updated
        assert "## New Pattern" in updated
        assert "Always do X" in updated

        # Backup exists
        backups = list((tmpdir / "memory" / "skill-backups").glob("*-SKILL.md"))
        assert len(backups) == 1
        assert backups[0].read_text() == "# Existing content\n"

        # Proposal marked applied
        loaded = rp.load_proposals()
        assert loaded[0]["status"] == "applied"
        assert loaded[0]["applied_at"] is not None


def test_set_content_from_file():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        rp.save_proposals([_sample_proposal()])

        content_file = tmpdir / "draft.md"
        content_file.write_text("## Drafted Pattern\n")

        rc = rp.cmd_set_content("prop-001", str(content_file))
        assert rc == 0

        loaded = rp.load_proposals()
        assert loaded[0]["content"] == "## Drafted Pattern\n"


def test_stats_empty():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        rc = rp.cmd_stats()
        assert rc == 0


def test_stats_with_proposals():
    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        rp = _load_with_tmpdir(tmpdir)
        rp.save_proposals([
            _sample_proposal(pid="p1", status="pending"),
            _sample_proposal(pid="p2", status="applied"),
            _sample_proposal(pid="p3", status="rejected"),
        ])
        rc = rp.cmd_stats()
        assert rc == 0


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
