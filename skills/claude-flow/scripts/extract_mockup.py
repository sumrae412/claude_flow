#!/usr/bin/env python3
"""Extract an Excalidraw skeleton from a live URL via Playwright DOM + bbox.

Used by Phase 4 when the task is a UI *refactor* — seed the mockup from the
existing production layout rather than a blank canvas, so the iteration
starts from reality instead of imagination.

This is a spike. Extraction is inherently lossy:
- No gradients, no box-shadow, no backdrop filters — flattened rectangles.
- No z-index respect — elements are emitted in DOM order, not stacking order.
- No pseudo-elements (`::before`, `::after`) — they don't appear in
  `querySelectorAll`.
- No transforms — `getBoundingClientRect` returns the transformed box, which
  is usually what you want, but the mockup loses the transform metadata.
- No text styling beyond fontSize (no weight, color, family) — Excalidraw
  text primitives don't carry those anyway.

Every failure mode emits a skip envelope instead of a corrupted file. The
consumer (`excalidraw-canvas` skill) is instructed to fall back to the
blank-canvas path when skip fires.

Exit codes:
    0 — success OR skip (never writes partial files)
    1 — usage error (argparse)
    2 — internal error (unhandled exception — still emits skip envelope)

Output: writes `.excalidraw` JSON to --output path. Also prints a JSON
status line to stdout:
    {"tool": "extract-mockup", "skipped": bool, "reason": str, "output": str}
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path

MAX_ELEMENTS = 80
MIN_BOX_DIMENSION = 5  # pixels — anything smaller is a tracker/spacer, drop it


def build_skip_envelope(reason: str, output: str = "") -> dict:
    return {
        "tool": "extract-mockup",
        "skipped": True,
        "reason": reason,
        "output": output,
    }


def check_playwright_available() -> tuple[bool, str]:
    if os.environ.get("PLAYWRIGHT_FORCE_UNAVAILABLE") == "1":
        return False, "playwright forced unavailable (test mode)"
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True, ""
    except ImportError as e:
        return False, f"playwright not installed: {e}"


def extract_from_url(url: str, max_wait: int) -> tuple[list[dict] | None, str]:
    """Render URL and extract a list of DOM box descriptors.

    Each box: {tag, x, y, width, height, text, fontSize}
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return None, f"playwright import failed: {e}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(url, timeout=max_wait * 1000, wait_until="domcontentloaded")
                boxes_js = """
                () => {
                    const selectors = 'div, section, article, header, footer, nav, main, aside, img, button, input, textarea, select, form, label, h1, h2, h3, h4, h5, h6, p, span, a, li, ul, ol';
                    return Array.from(document.querySelectorAll(selectors))
                        .map(el => {
                            const r = el.getBoundingClientRect();
                            const cs = window.getComputedStyle(el);
                            const txt = (el.childElementCount === 0 && el.textContent)
                                ? el.textContent.trim().slice(0, 80) : '';
                            return {
                                tag: el.tagName.toLowerCase(),
                                x: r.x,
                                y: r.y,
                                width: r.width,
                                height: r.height,
                                text: txt,
                                fontSize: parseFloat(cs.fontSize) || 0,
                            };
                        })
                        .filter(b => b.width > 0 && b.height > 0);
                }
                """
                boxes = page.evaluate(boxes_js)
                return boxes, ""
            finally:
                browser.close()
    except Exception as e:
        return None, f"extract failed: {type(e).__name__}: {e}"


def _tag_to_excal_type(tag: str, has_text: bool) -> str:
    """Map HTML tag to Excalidraw element type."""
    text_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "a", "label", "li"}
    if has_text and tag in text_tags:
        return "text"
    if tag in ("img", "button", "input", "textarea", "select"):
        return "rectangle"
    return "rectangle"


def dom_to_excalidraw(dom_boxes: list[dict]) -> dict:
    """Convert a list of DOM box descriptors to an Excalidraw file dict.

    Filters tiny boxes (< MIN_BOX_DIMENSION). Caps at MAX_ELEMENTS to keep
    the output Claude-writable.
    """
    filtered = [
        b for b in dom_boxes
        if b.get("width", 0) >= MIN_BOX_DIMENSION and b.get("height", 0) >= MIN_BOX_DIMENSION
    ]

    # Sort by area descending so the most visually significant boxes come
    # first — if we cap, the cap drops the smallest/least-important elements.
    filtered.sort(key=lambda b: b["width"] * b["height"], reverse=True)
    filtered = filtered[:MAX_ELEMENTS]

    elements = []
    for i, b in enumerate(filtered):
        has_text = bool(b.get("text"))
        el_type = _tag_to_excal_type(b.get("tag", ""), has_text)
        elem = {
            "id": f"extracted-{i}",
            "type": el_type,
            "x": float(b["x"]),
            "y": float(b["y"]),
            "width": float(b["width"]),
            "height": float(b["height"]),
            "strokeColor": "#1e1e1e",
            "backgroundColor": "transparent",
            "strokeWidth": 1,
            "roughness": 1,
            "opacity": 100,
            "seed": 1,
            "version": 1,
            "versionNonce": 0,
            "isDeleted": False,
            "groupIds": [],
            "frameId": None,
            "boundElements": None,
            "updated": 0,
            "link": None,
            "locked": False,
        }
        if el_type == "text":
            elem["text"] = b.get("text", "")
            elem["fontSize"] = float(b.get("fontSize") or 16)
            elem["fontFamily"] = 1
            elem["textAlign"] = "left"
            elem["verticalAlign"] = "top"
            elem["baseline"] = 0
            elem["containerId"] = None
            elem["originalText"] = b.get("text", "")
        elements.append(elem)

    return {
        "type": "excalidraw",
        "version": 2,
        "source": "extract_mockup.py",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="URL of the live page to extract")
    ap.add_argument("--output", required=True, help="path to write .excalidraw skeleton")
    ap.add_argument("--max-wait", type=int, default=10)
    args = ap.parse_args()

    output_path = Path(args.output)

    ok, reason = check_playwright_available()
    if not ok:
        print(json.dumps(build_skip_envelope(reason, str(output_path))))
        return 0

    boxes, err = extract_from_url(args.url, args.max_wait)
    if boxes is None:
        print(json.dumps(build_skip_envelope(err, str(output_path))))
        return 0

    if not boxes:
        print(json.dumps(build_skip_envelope(
            "no DOM elements extracted — page may not be hydrated or URL is blank",
            str(output_path),
        )))
        return 0

    excal = dom_to_excalidraw(boxes)

    if not excal["elements"]:
        print(json.dumps(build_skip_envelope(
            "all DOM elements filtered (too small) — extract would be empty, skipping",
            str(output_path),
        )))
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(excal, indent=2))

    print(json.dumps({
        "tool": "extract-mockup",
        "skipped": False,
        "reason": "",
        "output": str(output_path),
        "elements_written": len(excal["elements"]),
    }))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({
            "tool": "extract-mockup",
            "skipped": True,
            "reason": f"internal error: {type(e).__name__}: {e}",
            "output": "",
        }))
        sys.exit(2)
