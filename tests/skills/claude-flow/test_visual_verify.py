"""Tests for visual_verify.py — all paths must return the skip envelope shape."""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "skills" / "claude-flow" / "scripts" / "visual_verify.py"
FIXTURES = ROOT / "tests" / "fixtures" / "visual_verify"


def run(args, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args, "--json"],
        capture_output=True, text=True, env=env, timeout=30,
    )


def test_skip_when_playwright_forced_unavailable():
    result = run(
        ["--url", "http://localhost:99999", "--mockup", str(FIXTURES / "sample.excalidraw")],
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert "playwright" in data["reason"].lower()
    assert data["findings"] == []


def test_skip_when_mockup_missing():
    result = run(
        ["--url", "about:blank", "--mockup", "/nonexistent.excalidraw"],
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["skipped"] is True


def test_output_shape_is_skip_envelope():
    """Every output path must return the canonical envelope keys."""
    result = run(
        ["--url", "about:blank", "--mockup", "/nonexistent.excalidraw"],
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    data = json.loads(result.stdout)
    for key in ("reviewer", "findings", "skipped", "reason"):
        assert key in data, f"missing key: {key}"
    assert data["reviewer"] == "visual-verify"
    assert isinstance(data["findings"], list)


def test_exit_code_zero_on_skip():
    # Skip paths must exit 0 — never block the workflow
    result = run(
        ["--url", "http://localhost:1", "--mockup", "/nonexistent"],
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode == 0


def test_empty_mockup_skips():
    """Mockup with no elements must skip, not crash."""
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".excalidraw", delete=False) as f:
        f.write('{"type":"excalidraw","version":2,"elements":[]}')
        path = f.name
    try:
        result = run(
            ["--url", "about:blank", "--mockup", path],
            env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
        )
        data = json.loads(result.stdout)
        assert data["skipped"] is True
    finally:
        os.unlink(path)
