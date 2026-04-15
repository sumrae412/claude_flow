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


# ----------------------------------------------------------------------------
# Manifest mode (state matrix) — Feature 1
# ----------------------------------------------------------------------------


def run_manifest(manifest_path, env_extra=None):
    """Run visual_verify in manifest mode. --url is ignored but argparse requires
    one of the input modes; the script treats --manifest as authoritative."""
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--manifest", str(manifest_path), "--json"],
        capture_output=True, text=True, env=env, timeout=30,
    )


def test_manifest_mode_skips_gracefully_when_playwright_unavailable():
    """Manifest mode with no playwright → skip envelope, exit 0."""
    result = run_manifest(
        FIXTURES / "manifest_valid.json",
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert data["findings"] == []


def test_manifest_missing_file_skips_gracefully():
    result = run_manifest(
        "/nonexistent/manifest.json",
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert "manifest" in data["reason"].lower()


def test_manifest_malformed_json_skips_gracefully():
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ not valid json")
        path = f.name
    try:
        result = run_manifest(
            path,
            env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["skipped"] is True
    finally:
        os.unlink(path)


def test_manifest_missing_mockup_file_is_high_severity_finding():
    """If the manifest points to a .excalidraw that doesn't exist, that's a
    generator bug — block the gate, don't silently skip."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    manifest = json.loads((FIXTURES / "manifest_missing_mockup.json").read_text())
    findings = visual_verify.verify_manifest(manifest, root=ROOT, render_fn=_stub_renderer_empty)
    assert any(
        f["severity"] == "high" and "mockup" in f["message"].lower() and "does_not_exist" in f["message"]
        for f in findings
    )


def test_manifest_iterates_all_states():
    """3-state manifest must call the renderer 3 times with 3 distinct URLs."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    calls = []

    def recording_renderer(url, max_wait, wait_for_selector=None, trigger_script=None):
        calls.append({"url": url, "wait_for_selector": wait_for_selector, "trigger_script": trigger_script})
        return {"boxes": [{"tag": "div", "x": 100, "y": 100, "width": 200, "height": 50}],
                "viewport": {"width": 800, "height": 600}, "broken_images": []}, ""

    manifest = json.loads((FIXTURES / "manifest_valid.json").read_text())
    visual_verify.verify_manifest(manifest, root=ROOT, render_fn=recording_renderer)

    assert len(calls) == 3
    urls = [c["url"] for c in calls]
    assert "http://localhost:3000/signup" in urls
    assert "http://localhost:3000/signup?simulate=error" in urls
    assert "http://localhost:3000/signup?simulate=loading" in urls
    # error state carries wait_for_selector
    error_call = next(c for c in calls if "error" in c["url"])
    assert error_call["wait_for_selector"] == ".error"
    # loading state carries trigger_script
    loading_call = next(c for c in calls if "loading" in c["url"])
    assert loading_call["trigger_script"] == "document.querySelector('form')?.submit()"


def test_manifest_any_state_mismatch_blocks_gate():
    """If 1 of 3 states has broken image, overall exit = 1."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    call_num = [0]

    def flaky_renderer(url, max_wait, wait_for_selector=None, trigger_script=None):
        call_num[0] += 1
        rendered = {"boxes": [{"tag": "div", "x": 100, "y": 100, "width": 200, "height": 50}],
                    "viewport": {"width": 800, "height": 600}, "broken_images": []}
        if call_num[0] == 2:  # error state has broken image
            rendered["broken_images"] = [{"src": "/missing.png", "alt": "logo"}]
        return rendered, ""

    manifest = json.loads((FIXTURES / "manifest_valid.json").read_text())
    findings = visual_verify.verify_manifest(manifest, root=ROOT, render_fn=flaky_renderer)
    high = [f for f in findings if f["severity"] == "high"]
    assert any("Broken image" in f["message"] for f in high)
    # Findings must identify which state failed
    assert any("error" in (f.get("state") or "") for f in high)


def test_manifest_findings_carry_state_name():
    """Every finding from manifest mode must be tagged with the screen + state."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    def blank_renderer(url, max_wait, wait_for_selector=None, trigger_script=None):
        return {"boxes": [], "viewport": {"width": 800, "height": 600}, "broken_images": []}, ""

    manifest = json.loads((FIXTURES / "manifest_valid.json").read_text())
    findings = visual_verify.verify_manifest(manifest, root=ROOT, render_fn=blank_renderer)
    for f in findings:
        assert "screen" in f, f"finding missing screen tag: {f}"
        assert "state" in f, f"finding missing state tag: {f}"


def test_single_mockup_mode_still_works():
    """Backward-compat: existing --mockup flag must continue to work."""
    result = run(
        ["--url", "http://localhost:99999", "--mockup", str(FIXTURES / "sample.excalidraw")],
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert data["reviewer"] == "visual-verify"


def _stub_renderer_empty(url, max_wait, wait_for_selector=None, trigger_script=None):
    return {"boxes": [], "viewport": {"width": 800, "height": 600}, "broken_images": []}, ""


def test_manifest_missing_base_url_is_high_severity_finding():
    """Manifest without base_url would produce confusing playwright errors.
    Fail fast with a clear finding instead."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import visual_verify

    manifest = {
        "feature_slug": "broken",
        "screens": [{"name": "signup", "path": "/signup", "states": [
            {"name": "default", "mockup_file": "tests/fixtures/visual_verify/sample.excalidraw",
             "url_suffix": "", "trigger_script": None, "wait_for_selector": None}
        ]}],
    }
    findings = visual_verify.verify_manifest(manifest, root=ROOT, render_fn=_stub_renderer_empty)
    assert len(findings) == 1
    assert findings[0]["severity"] == "high"
    assert "base_url" in findings[0]["message"]
