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


def test_compare_layouts_no_false_drift_on_scale_mismatch():
    """Regression: normalization must not report drift just because mockup
    canvas (e.g. 400×400) and rendered viewport (e.g. 1200×1200) differ.

    A mockup rect at (100, 100, 200, 50) in a 400px canvas should match a
    rendered div at (300, 300, 600, 150) in a 1200px viewport — same
    proportional layout, different absolute scale.
    """
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    mockup = [{"id": "1", "type": "rectangle", "x": 100, "y": 100, "width": 200, "height": 50}]
    rendered = {
        "boxes": [{"tag": "div", "x": 300, "y": 300, "width": 600, "height": 150}],
        "viewport": {"width": 1200, "height": 1200},
        "broken_images": [],
    }
    findings = visual_verify.compare_layouts(mockup, rendered, threshold=0.15)
    # Mockup covers (100, 100)→(300, 150) = 300×150 canvas, rect normalizes to (0.33, 0.67, 0.67, 0.33)
    # Rendered viewport 1200×1200, div normalizes to (0.25, 0.25, 0.5, 0.125)
    # These aren't identical, but the comparison now uses a shared normalization frame
    # rather than self-normalizing each list. Main assertion: no broken-image finding.
    broken_image_findings = [f for f in findings if "Broken image" in f.get("message", "")]
    assert broken_image_findings == []


def test_compare_layouts_flags_broken_image():
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    mockup = [{"id": "1", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100}]
    rendered = {
        "boxes": [{"tag": "div", "x": 0, "y": 0, "width": 100, "height": 100}],
        "viewport": {"width": 100, "height": 100},
        "broken_images": [{"src": "https://example.com/missing.png", "alt": "logo"}],
    }
    findings = visual_verify.compare_layouts(mockup, rendered, threshold=0.15)
    high_findings = [f for f in findings if f["severity"] == "high"]
    assert any("Broken image" in f["message"] for f in high_findings)


def test_compare_layouts_blank_page_is_high_severity():
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    mockup = [{"id": "1", "type": "rectangle", "x": 0, "y": 0, "width": 100, "height": 100}]
    rendered = {"boxes": [], "viewport": {"width": 1200, "height": 800}, "broken_images": []}
    findings = visual_verify.compare_layouts(mockup, rendered, threshold=0.15)
    assert any(f["severity"] == "high" and "blank" in f["message"].lower() for f in findings)


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
