#!/usr/bin/env python3
"""Probe for Playwright availability. Stdlib only.

Returns JSON: {"available": bool, "reason": str, "browsers": [...]}

Used by visual_verify.py to decide between full rendering and graceful skip.
"""
from __future__ import annotations
import json
import sys


def probe() -> dict:
    try:
        import playwright  # noqa: F401
    except ImportError as e:
        return {"available": False, "reason": f"playwright not installed: {e}", "browsers": []}

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return {"available": False, "reason": f"playwright.sync_api import failed: {e}", "browsers": []}

    browsers = []
    try:
        with sync_playwright() as p:
            for name in ("chromium", "firefox", "webkit"):
                try:
                    browser = getattr(p, name).launch(headless=True)
                    browser.close()
                    browsers.append(name)
                except Exception:
                    continue
    except Exception as e:
        return {"available": False, "reason": f"playwright runtime error: {e}", "browsers": []}

    if not browsers:
        return {
            "available": False,
            "reason": "no browser binaries installed (run `playwright install chromium`)",
            "browsers": [],
        }
    return {"available": True, "reason": "", "browsers": browsers}


if __name__ == "__main__":
    print(json.dumps(probe()))
    sys.exit(0)
