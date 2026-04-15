"""Tests for extract_mockup.py — Playwright DOM → Excalidraw skeleton.

This is a spike: extraction is inherently lossy (no gradients, no transforms,
flattened z-index). Tests verify the output shape is always valid Excalidraw
or a skip envelope, never a corrupted file.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "skills" / "claude-flow" / "scripts" / "extract_mockup.py"


def run(args, env_extra=None):
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True, text=True, env=env, timeout=30,
    )


def test_skip_when_playwright_unavailable():
    with tempfile.NamedTemporaryFile(suffix=".excalidraw", delete=False) as tf:
        out = tf.name
    try:
        result = run(
            ["--url", "http://localhost:99999", "--output", out],
            env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
        )
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["skipped"] is True
        assert "playwright" in data["reason"].lower()
        # Must not write a partial file when skipping
        assert not Path(out).exists() or Path(out).stat().st_size == 0
    finally:
        Path(out).unlink(missing_ok=True)


def test_skip_when_output_path_missing():
    """--output is required; argparse must reject without it."""
    result = run(
        ["--url", "http://example.com"],
        env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
    )
    assert result.returncode != 0


def test_dom_to_excalidraw_valid_json_with_unique_ids():
    """DOM box list → Excalidraw JSON: every element has unique id, supported type."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import extract_mockup

    dom_boxes = [
        {"tag": "div", "x": 0, "y": 0, "width": 800, "height": 100, "text": "", "fontSize": 0},
        {"tag": "h1", "x": 10, "y": 10, "width": 200, "height": 40, "text": "Title", "fontSize": 32},
        {"tag": "button", "x": 300, "y": 50, "width": 100, "height": 40, "text": "Submit", "fontSize": 14},
    ]
    excal = extract_mockup.dom_to_excalidraw(dom_boxes)

    assert excal["type"] == "excalidraw"
    assert isinstance(excal["elements"], list)
    assert len(excal["elements"]) == 3
    ids = [e["id"] for e in excal["elements"]]
    assert len(set(ids)) == 3, "element ids must be unique"
    types = {e["type"] for e in excal["elements"]}
    supported = {"rectangle", "ellipse", "text", "arrow", "line", "diamond"}
    assert types.issubset(supported), f"unsupported types: {types - supported}"


def test_dom_to_excalidraw_caps_output_elements():
    """If DOM has hundreds of boxes, cap to keep file Claude-writable."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import extract_mockup

    dom_boxes = [
        {"tag": "div", "x": i * 10, "y": i * 10, "width": 50, "height": 50, "text": "", "fontSize": 0}
        for i in range(300)
    ]
    excal = extract_mockup.dom_to_excalidraw(dom_boxes)
    assert len(excal["elements"]) <= 80, "should cap at 80 elements for Claude-writable size"


def test_dom_to_excalidraw_preserves_text_content():
    """Text-bearing elements should round-trip their text string."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import extract_mockup

    dom_boxes = [
        {"tag": "h1", "x": 0, "y": 0, "width": 200, "height": 40, "text": "Welcome back", "fontSize": 32},
    ]
    excal = extract_mockup.dom_to_excalidraw(dom_boxes)
    text_elements = [e for e in excal["elements"] if e["type"] == "text"]
    assert len(text_elements) == 1
    assert text_elements[0]["text"] == "Welcome back"


def test_empty_dom_returns_empty_excalidraw():
    """Zero-box DOM should still produce a valid (empty) Excalidraw file,
    not a crash or a corrupted file."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import extract_mockup

    excal = extract_mockup.dom_to_excalidraw([])
    assert excal["type"] == "excalidraw"
    assert excal["elements"] == []


def test_cli_skip_envelope_shape():
    """Every skip must return the canonical envelope keys."""
    with tempfile.NamedTemporaryFile(suffix=".excalidraw", delete=False) as tf:
        out = tf.name
    try:
        result = run(
            ["--url", "http://localhost:1", "--output", out],
            env_extra={"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"},
        )
        data = json.loads(result.stdout)
        for key in ("tool", "skipped", "reason"):
            assert key in data, f"missing key: {key}"
        assert data["tool"] == "extract-mockup"
    finally:
        Path(out).unlink(missing_ok=True)


def test_dom_to_excalidraw_filters_tiny_boxes():
    """Pixel-perfect DOM has lots of 1x1 tracking spans, spacers, etc.
    The skeleton should ignore boxes smaller than a meaningful threshold."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import extract_mockup

    dom_boxes = [
        {"tag": "img", "x": 0, "y": 0, "width": 1, "height": 1, "text": "", "fontSize": 0},  # tracker pixel
        {"tag": "span", "x": 10, "y": 10, "width": 3, "height": 3, "text": "", "fontSize": 0},  # spacer
        {"tag": "h1", "x": 0, "y": 0, "width": 200, "height": 40, "text": "Title", "fontSize": 32},  # keep
    ]
    excal = extract_mockup.dom_to_excalidraw(dom_boxes)
    assert len(excal["elements"]) == 1
    assert excal["elements"][0]["type"] == "text"


def test_skip_envelope_on_zero_dom_extracted():
    """If Playwright runs but returns 0 elements, emit skip (likely SPA
    before hydration, or wrong URL) — do not write an empty file that
    downstream treats as ground truth."""
    sys.path.insert(0, str(ROOT / "skills" / "claude-flow" / "scripts"))
    import extract_mockup

    # Emulate: extract_from_url returns empty box list
    skip_env = extract_mockup.build_skip_envelope("no DOM elements extracted — page may not be hydrated")
    assert skip_env["skipped"] is True
    assert "DOM" in skip_env["reason"] or "hydrated" in skip_env["reason"]
