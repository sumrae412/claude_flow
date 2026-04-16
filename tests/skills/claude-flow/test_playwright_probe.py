"""Tests for _playwright_probe.py — must return valid JSON with stable shape."""
import json
import subprocess
import sys
from pathlib import Path

def _resolve_script(name):
    for p in (
        Path.home() / ".claude" / "skills" / "claude-flow" / "scripts" / name,
        Path(__file__).parents[4] / "claude-skills" / "claude-flow" / "scripts" / name,
    ):
        if p.exists():
            return p
    raise RuntimeError(f"{name} not found; install claude-skills via claude_flow/install.sh")


SCRIPT = _resolve_script("_playwright_probe.py")


def test_probe_returns_json():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=30
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "available" in data
    assert "reason" in data
    assert "browsers" in data
    assert isinstance(data["available"], bool)
    assert isinstance(data["reason"], str)
    assert isinstance(data["browsers"], list)


def test_probe_reason_non_empty_when_unavailable():
    result = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=30
    )
    data = json.loads(result.stdout)
    if not data["available"]:
        assert data["reason"], "reason must be non-empty when available=False"
        assert data["browsers"] == []
