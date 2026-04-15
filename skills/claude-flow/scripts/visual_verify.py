#!/usr/bin/env python3
"""Visual verification gate for Phase 5 Step 3d.

Compares a rendered UI against the approved excalidraw mockup from Phase 4.
Catches layout regressions the test suite misses (broken images, elements
positioned wrong, structural drift from mockup).

Emits a graceful-skip envelope on any infrastructure failure:
    - Playwright not installed
    - Browser binary missing
    - URL unreachable
    - Mockup file missing or malformed

Exit codes:
    0 — pass OR skip (findings empty, or skip envelope emitted)
    1 — findings (visual discrepancies detected)
    2 — internal error

Usage:
    python skills/claude-flow/scripts/visual_verify.py \\
        --url http://localhost:3000/dashboard \\
        --mockup docs/design/dashboard/mockups/dashboard.excalidraw \\
        --json

Output shape (always):
    {
      "reviewer": "visual-verify",
      "findings": [{"severity": "medium", "message": "...", "bbox": [...]}],
      "skipped": false,
      "reason": ""
    }

Inspired by Brian/Notion's /figma verification loop — the idea that AI-built
UI should be verified against the approved mockup, not just against tests.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path


def skip(reason: str) -> dict:
    return {"reviewer": "visual-verify", "findings": [], "skipped": True, "reason": reason}


def check_playwright_available() -> tuple[bool, str]:
    if os.environ.get("PLAYWRIGHT_FORCE_UNAVAILABLE") == "1":
        return False, "playwright forced unavailable (test mode)"
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True, ""
    except ImportError as e:
        return False, f"playwright not installed: {e}"


def load_mockup(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def extract_mockup_boxes(mockup: dict) -> list[dict]:
    """Extract normalized bboxes from excalidraw JSON elements."""
    elements = mockup.get("elements", [])
    boxes = []
    for el in elements:
        if el.get("isDeleted"):
            continue
        boxes.append({
            "id": str(el.get("id", "?")),
            "type": el.get("type"),
            "x": float(el.get("x", 0)),
            "y": float(el.get("y", 0)),
            "width": float(el.get("width", 0)),
            "height": float(el.get("height", 0)),
        })
    return boxes


def render_and_extract(
    url: str,
    max_wait: int,
    wait_for_selector: str | None = None,
    trigger_script: str | None = None,
) -> tuple[dict | None, str]:
    """Render URL via headless Playwright and extract DOM element bboxes
    + viewport dimensions for normalization.

    Optional state-triggering:
    - trigger_script: JS evaluated after navigation, before extraction. Use for
      states reached by interaction (e.g. clicking submit to show validation).
    - wait_for_selector: CSS selector to wait for before extraction. Use for
      states where the marker element appears asynchronously.
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
                if trigger_script:
                    try:
                        page.evaluate(trigger_script)
                    except Exception as e:
                        return None, f"trigger_script failed: {type(e).__name__}: {e}"
                if wait_for_selector:
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=max_wait * 1000)
                    except Exception as e:
                        return None, f"wait_for_selector {wait_for_selector!r} failed: {type(e).__name__}: {e}"
                boxes_js = """
                () => {
                    const selectors = 'div, section, article, header, footer, nav, main, img, button, input, form, h1, h2, h3';
                    return Array.from(document.querySelectorAll(selectors))
                        .filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 10 && r.height > 10;
                        })
                        .map(el => {
                            const r = el.getBoundingClientRect();
                            return {tag: el.tagName.toLowerCase(), x: r.x, y: r.y, width: r.width, height: r.height};
                        });
                }
                """
                boxes = page.evaluate(boxes_js)
                viewport = page.evaluate(
                    "() => ({width: window.innerWidth, height: window.innerHeight})"
                )
                broken_images = page.evaluate("""
                () => Array.from(document.images)
                    .filter(img => !img.complete || img.naturalWidth === 0)
                    .map(img => ({src: img.src, alt: img.alt}))
                """)
                return {
                    "boxes": boxes,
                    "broken_images": broken_images,
                    "viewport": viewport,
                }, ""
            finally:
                browser.close()
    except Exception as e:
        return None, f"render failed: {type(e).__name__}: {e}"


def _normalize_boxes(boxes: list[dict], ref_w: float, ref_h: float) -> list[dict]:
    """Normalize boxes into [0,1] × [0,1] using an explicit reference frame
    so mockup and rendered coordinate spaces are comparable to each other.

    ref_w, ref_h = the canvas/viewport dimensions the boxes live in.
    """
    ref_w = ref_w or 1
    ref_h = ref_h or 1
    out = []
    for b in boxes:
        out.append({
            "id": str(b.get("id", b.get("tag", "?"))),
            "x": b["x"] / ref_w,
            "y": b["y"] / ref_h,
            "w": b.get("width", 0) / ref_w,
            "h": b.get("height", 0) / ref_h,
        })
    return out


def _mockup_canvas_dims(mockup_boxes: list[dict]) -> tuple[float, float]:
    """Derive a canvas frame from mockup element bounds.

    Excalidraw files don't always include appState dimensions, so we use
    the bounding box of all elements as the canvas reference.
    """
    if not mockup_boxes:
        return 1.0, 1.0
    w = max((b["x"] + b.get("width", 0)) for b in mockup_boxes)
    h = max((b["y"] + b.get("height", 0)) for b in mockup_boxes)
    return max(w, 1.0), max(h, 1.0)


def compare_layouts(mockup_boxes: list[dict], rendered: dict, threshold: float) -> list[dict]:
    """Compare mockup bboxes to rendered DOM bboxes. Returns findings.

    Both sides are normalized into [0,1] × [0,1] — mockup against its own
    element-bbox canvas, rendered against the browser viewport. This is not
    perfect (a designer framing a mockup at 400×400 is implicitly claiming
    the layout scales proportionally to viewport), but it's proportionally
    comparable across scale mismatches, which naive same-list normalization
    was not.
    """
    findings = []

    for img in rendered.get("broken_images", []):
        findings.append({
            "severity": "high",
            "message": f"Broken image: {img.get('src', '?')} (alt={img.get('alt', '')})",
            "bbox": None,
        })

    rendered_boxes = rendered.get("boxes", [])
    if not rendered_boxes:
        findings.append({
            "severity": "high",
            "message": "No visible structural elements rendered — page may be blank or failed to load",
            "bbox": None,
        })
        return findings

    viewport = rendered.get("viewport") or {}
    vw = viewport.get("width") or max(
        (b["x"] + b.get("width", 0)) for b in rendered_boxes
    ) or 1
    vh = viewport.get("height") or max(
        (b["y"] + b.get("height", 0)) for b in rendered_boxes
    ) or 1
    mw, mh = _mockup_canvas_dims(mockup_boxes)

    norm_mockup = _normalize_boxes(mockup_boxes, mw, mh)
    norm_rendered = _normalize_boxes(rendered_boxes, vw, vh)

    for m in norm_mockup:
        if not norm_rendered:
            closest_dist = 1.0
        else:
            closest_dist = min(
                (abs(r["x"] - m["x"]) + abs(r["y"] - m["y"]) + abs(r["w"] - m["w"]) + abs(r["h"] - m["h"])) / 4
                for r in norm_rendered
            )
        if closest_dist > threshold:
            findings.append({
                "severity": "medium",
                "message": f"Mockup element {m['id']} has no close rendered match (drift={closest_dist:.2f}, threshold={threshold})",
                "bbox": [m["x"], m["y"], m["w"], m["h"]],
            })
    return findings


def load_manifest(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict) or "screens" not in data:
        return None
    return data


def verify_manifest(manifest: dict, root: Path, render_fn, threshold: float = 0.15, max_wait: int = 10) -> list[dict]:
    """Iterate every (screen, state) in the manifest and accumulate findings.

    render_fn is injected for testability — in production it's render_and_extract.
    Every finding is tagged with 'screen' and 'state' so the user knows which
    state failed. A missing mockup_file is a HIGH-severity finding (not a skip),
    because it indicates a generator bug: the manifest claims the mockup exists.
    """
    findings: list[dict] = []
    base_url = manifest.get("base_url", "").rstrip("/")
    if not base_url:
        # Without base_url, every URL ends up as e.g. "/signup" which Playwright
        # rejects with a confusing protocol error. Fail fast with a clear message.
        findings.append({
            "severity": "high",
            "message": "Manifest missing required 'base_url' field — cannot construct URLs for rendering",
            "bbox": None,
            "screen": None,
            "state": None,
        })
        return findings
    for screen in manifest.get("screens", []):
        screen_name = screen.get("name", "?")
        path = screen.get("path", "")
        for state in screen.get("states", []):
            state_name = state.get("name", "?")
            mockup_file = state.get("mockup_file", "")
            full_mockup_path = root / mockup_file if mockup_file else None
            url = f"{base_url}{path}{state.get('url_suffix', '')}"

            if not full_mockup_path or not full_mockup_path.exists():
                findings.append({
                    "severity": "high",
                    "message": f"Manifest references missing mockup file: {mockup_file}",
                    "bbox": None,
                    "screen": screen_name,
                    "state": state_name,
                })
                continue

            mockup = load_mockup(full_mockup_path)
            if mockup is None:
                findings.append({
                    "severity": "high",
                    "message": f"Malformed mockup file: {mockup_file}",
                    "bbox": None,
                    "screen": screen_name,
                    "state": state_name,
                })
                continue

            mockup_boxes = extract_mockup_boxes(mockup)
            if not mockup_boxes:
                findings.append({
                    "severity": "medium",
                    "message": f"Mockup has no elements to compare against: {mockup_file}",
                    "bbox": None,
                    "screen": screen_name,
                    "state": state_name,
                })
                continue

            rendered, err = render_fn(
                url,
                max_wait,
                wait_for_selector=state.get("wait_for_selector"),
                trigger_script=state.get("trigger_script"),
            )
            if rendered is None:
                findings.append({
                    "severity": "high",
                    "message": f"Could not render {url}: {err}",
                    "bbox": None,
                    "screen": screen_name,
                    "state": state_name,
                })
                continue

            state_findings = compare_layouts(mockup_boxes, rendered, threshold)
            for f in state_findings:
                f["screen"] = screen_name
                f["state"] = state_name
                findings.append(f)

    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", help="(single-mockup mode) dev-server URL to render")
    ap.add_argument("--mockup", help="(single-mockup mode) path to .excalidraw file")
    ap.add_argument("--manifest", help="(state-matrix mode) path to mockup-manifest.json")
    ap.add_argument("--max-wait", type=int, default=10)
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.manifest and not (args.url and args.mockup):
        ap.error("either --manifest, or both --url and --mockup, are required")

    # Manifest mode (state matrix) takes precedence. Check manifest existence
    # before playwright so an obviously-bad manifest path surfaces a clear
    # reason instead of getting masked by the playwright-unavailable skip.
    if args.manifest:
        manifest_path = Path(args.manifest)
        manifest = load_manifest(manifest_path)
        if manifest is None:
            print(json.dumps(skip(f"manifest not found or malformed: {args.manifest}")))
            return 0

        ok, reason = check_playwright_available()
        if not ok:
            print(json.dumps(skip(reason)))
            return 0

        # Mockup paths in the manifest are resolved relative to the current
        # working directory (which is expected to be the repo root when run
        # from Phase 5). This matches how visual_verify is invoked from the
        # phase doc.
        root = Path.cwd()
        findings = verify_manifest(manifest, root=root, render_fn=render_and_extract,
                                   threshold=args.threshold, max_wait=args.max_wait)
        out = {"reviewer": "visual-verify", "findings": findings, "skipped": False, "reason": ""}
        print(json.dumps(out))
        return 1 if findings else 0

    # Single-mockup mode (backward-compat).
    ok, reason = check_playwright_available()
    if not ok:
        print(json.dumps(skip(reason)))
        return 0

    mockup_path = Path(args.mockup)
    mockup = load_mockup(mockup_path)
    if mockup is None:
        print(json.dumps(skip(f"mockup not found or malformed: {args.mockup}")))
        return 0

    mockup_boxes = extract_mockup_boxes(mockup)
    if not mockup_boxes:
        print(json.dumps(skip("mockup has no elements to compare against")))
        return 0

    rendered, err = render_and_extract(args.url, args.max_wait)
    if rendered is None:
        print(json.dumps(skip(f"could not render URL: {err}")))
        return 0

    findings = compare_layouts(mockup_boxes, rendered, args.threshold)
    out = {"reviewer": "visual-verify", "findings": findings, "skipped": False, "reason": ""}
    print(json.dumps(out))
    return 1 if findings else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(json.dumps({
            "reviewer": "visual-verify",
            "findings": [],
            "skipped": True,
            "reason": f"internal error: {type(e).__name__}: {e}",
        }))
        sys.exit(2)
