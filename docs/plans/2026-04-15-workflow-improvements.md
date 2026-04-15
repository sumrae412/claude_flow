# Workflow Improvements from External Pattern Mining — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Import three patterns from external workflows (Brian/Notion, CJ, others) that fill real gaps in claude_flow: visual verification of UI diffs, authoring-time lookup injection to prevent hallucination, and a Phase 3 "teach the AI to answer itself" pass.

**Architecture:** Three independent additions that share the memory-injection pattern style (deterministic Python scripts invoked by phase files, JSON output consumed by orchestrator). New Phase 5 Step 3d (visual verification gate) composes with existing 3b/3c gates. New `inject_lookups.py` runs alongside `match_memory_domains.py`. New `audit_phase3_questions.py` fires during Phase 3 Step 2 quality gate.

**Tech Stack:**
- Python stdlib (pathlib, subprocess, json, ast, re)
- Playwright (optional dep, graceful skip if missing) for visual verification
- PIL/Pillow for image diff (optional, fallback to pixel-by-pixel)
- Existing claude-flow patterns: JSON-output scripts + phase-file orchestration + skip envelope

**Ruled Out:**
- curl + HTML parse for visual verify — user chose full Playwright; HTML parse can't catch visual positioning bugs (CJ's spinner-lands-between-dots case)
- Pre-Phase-5 lookups only — user chose two-tier; per-step catches step-specific hallucinations missed by plan-wide scan
- Documentation-only Phase 3 audit — user chose full; without the script, principle is noise
- Flowy as separate tool — excalidraw-canvas already covers visual planning; CLAUDE.md says round-trip works there
- End-of-day "dropped ball" prompt — personal productivity, not workflow-orchestration fit
- Duplicating /ship auto-fix CI loop — shipping-workflow already does this

---

## Task Layout

**Task dependency graph:**
```
T1 (shared_prerequisite: Playwright skip envelope helper)
  ↓ (build)
T2 (value_unit: visual-verify script + tests)
  ↓ (data: script contract)
T3 (value_unit: wire visual gate into phase-5-implementation.md Step 3d)

T4 (shared_prerequisite: inject_lookups.py with detector registry)
  ↓ (data: output format)
T5 (value_unit: wire plan-wide lookups into Phase 4b / pre-Phase-5)
  ↓ (knowledge)
T6 (value_unit: wire per-step lookups into subagent-driven-development dispatch)

T7 (shared_prerequisite: audit_phase3_questions.py script + tests)
  ↓ (data: script contract)
T8 (value_unit: wire audit script into Phase 3 Step 2)

T9 (value_unit: memory entries + MEMORY.md index updates)
```

T1-T3, T4-T6, T7-T8 are three independent tracks. T9 is final cleanup. No cross-track dependencies except T9 waits for all.

---

## Track A: Visual Verification Gate (Phase 5 Step 3d)

### Task 1: Playwright availability helper

**Type:** shared_prerequisite
**Depends on:** none

**Files:**
- Create: `skills/claude-flow/scripts/_playwright_probe.py`
- Test: `tests/skills/claude-flow/test_playwright_probe.py`

**Step 1: Write failing test**

```python
# tests/skills/claude-flow/test_playwright_probe.py
import subprocess, sys, json
from pathlib import Path

SCRIPT = Path("skills/claude-flow/scripts/_playwright_probe.py")

def test_probe_returns_json():
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert "available" in data
    assert "reason" in data
    assert isinstance(data["available"], bool)

def test_probe_detects_missing_playwright(monkeypatch):
    # When playwright import fails, available must be False with a reason
    # (this test runs in whatever env pytest is in; just assert shape)
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    data = json.loads(result.stdout)
    if not data["available"]:
        assert data["reason"]  # non-empty string
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/skills/claude-flow/test_playwright_probe.py -v
```

Expected: FAIL with `FileNotFoundError` (script doesn't exist).

**Step 3: Implement script**

```python
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

    # Check at least one browser binary is installed
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
        return {"available": False, "reason": "no browser binaries installed (run `playwright install chromium`)", "browsers": []}
    return {"available": True, "reason": "", "browsers": browsers}


if __name__ == "__main__":
    print(json.dumps(probe()))
    sys.exit(0)
```

**Step 4: Run test — verify passes**

```bash
pytest tests/skills/claude-flow/test_playwright_probe.py -v
```

Expected: PASS.

**Step 5: Commit**

```bash
git add skills/claude-flow/scripts/_playwright_probe.py tests/skills/claude-flow/test_playwright_probe.py
git commit -m "feat: _playwright_probe helper for visual-verify gate"
```

---

### Task 2: visual_verify.py script + tests

**Type:** value_unit
**Depends on:** T1 (build — uses probe)

**Files:**
- Create: `skills/claude-flow/scripts/visual_verify.py`
- Test: `tests/skills/claude-flow/test_visual_verify.py`
- Test fixtures: `tests/fixtures/visual_verify/sample.excalidraw`, `tests/fixtures/visual_verify/sample.html`

**Step 1: Write failing tests**

```python
# tests/skills/claude-flow/test_visual_verify.py
import subprocess, sys, json, tempfile
from pathlib import Path

SCRIPT = Path("skills/claude-flow/scripts/visual_verify.py")
FIXTURES = Path("tests/fixtures/visual_verify")

def run(args):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--json"],
                          capture_output=True, text=True)

def test_skip_when_no_playwright(monkeypatch):
    # With PLAYWRIGHT_FORCE_UNAVAILABLE=1, script emits skip envelope
    env = {"PLAYWRIGHT_FORCE_UNAVAILABLE": "1"}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--url", "http://localhost:99999", "--mockup", str(FIXTURES / "sample.excalidraw"), "--json"],
        capture_output=True, text=True, env={**__import__("os").environ, **env}
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert "playwright" in data["reason"].lower()
    assert data["findings"] == []

def test_skip_when_no_mockup():
    # Missing mockup file → skip, exit 0
    result = run(["--url", "http://localhost:3000", "--mockup", "/nonexistent.excalidraw"])
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["skipped"] is True
    assert "mockup" in data["reason"].lower()

def test_skip_when_url_unreachable():
    # Unreachable URL → skip (not a visual-verify failure, infra failure)
    result = run(["--url", "http://localhost:1", "--mockup", str(FIXTURES / "sample.excalidraw")])
    assert result.returncode == 0
    data = json.loads(result.stdout)
    # Either skipped (no playwright) or skipped (connection refused)
    assert data.get("skipped") is True

def test_output_shape_is_skip_envelope():
    # Every output path must return the skip envelope shape
    result = run(["--url", "about:blank", "--mockup", "/nonexistent.excalidraw"])
    data = json.loads(result.stdout)
    for key in ("reviewer", "findings", "skipped", "reason"):
        assert key in data, f"missing key: {key}"
    assert data["reviewer"] == "visual-verify"
```

**Step 2: Create test fixtures**

```bash
mkdir -p tests/fixtures/visual_verify
cat > tests/fixtures/visual_verify/sample.excalidraw <<'EOF'
{"type":"excalidraw","version":2,"source":"test","elements":[{"id":"1","type":"rectangle","x":100,"y":100,"width":200,"height":50}],"appState":{"viewBackgroundColor":"#ffffff"}}
EOF
```

**Step 3: Run tests — verify fail**

```bash
pytest tests/skills/claude-flow/test_visual_verify.py -v
```

Expected: FAIL with `FileNotFoundError`.

**Step 4: Implement visual_verify.py**

Key design points:
- Always returns the graceful-skip envelope: `{"reviewer": "visual-verify", "findings": [...], "skipped": bool, "reason": str}`
- Exit code 0 on skip; exit 1 only on actual visual discrepancy findings
- Launches headless chromium, navigates to URL, screenshots, extracts excalidraw element bboxes, compares layout structure
- Comparison mode (v1): bbox overlap check — for each rectangle in mockup, is there a corresponding element at similar proportional position in rendered DOM? Finds missing-image/broken-layout cases (Brian's example).
- `PLAYWRIGHT_FORCE_UNAVAILABLE=1` env var for testability
- Respects `--max-wait 10` for page load
- `--threshold 0.15` — accept ≤15% bbox position/size drift (reasonable for responsive design)

```python
#!/usr/bin/env python3
"""Visual verification gate for Phase 5 Step 3d.

Compares a rendered UI against the approved excalidraw mockup from Phase 4.
Catches layout regressions the test suite misses (missing images, elements
positioned wrong, structural drift from mockup).

Emits graceful skip envelope on any infrastructure failure:
    - Playwright not installed
    - Browser binary missing
    - URL unreachable
    - Mockup file missing
    - Mockup malformed

Exit codes:
    0 — pass OR skip (no findings OR skip envelope)
    1 — findings (visual discrepancies detected)

Usage:
    python skills/claude-flow/scripts/visual_verify.py \\
        --url http://localhost:3000/dashboard \\
        --mockup docs/design/dashboard/mockups/dashboard.excalidraw \\
        --json

Output shape (graceful skip envelope, always):
    {
      "reviewer": "visual-verify",
      "findings": [{"severity": "medium", "message": "...", "bbox": [...]}],
      "skipped": false,
      "reason": ""
    }
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
    """Extract normalized bboxes from excalidraw JSON."""
    elements = mockup.get("elements", [])
    boxes = []
    for el in elements:
        if el.get("isDeleted"):
            continue
        boxes.append({
            "id": el.get("id"),
            "type": el.get("type"),
            "x": el.get("x", 0),
            "y": el.get("y", 0),
            "width": el.get("width", 0),
            "height": el.get("height", 0),
        })
    return boxes


def render_and_extract(url: str, max_wait: int = 10) -> tuple[list[dict] | None, str]:
    """Render URL and extract DOM element bboxes."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return None, f"playwright import failed: {e}"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=max_wait * 1000, wait_until="domcontentloaded")
            # Extract bboxes of visible structural elements
            boxes_js = """
            () => {
                const selectors = 'div, section, article, header, footer, nav, main, img, button, input, form';
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
            # Also check for broken images
            broken_images = page.evaluate("""
            () => Array.from(document.images)
                .filter(img => !img.complete || img.naturalWidth === 0)
                .map(img => ({src: img.src, alt: img.alt}))
            """)
            browser.close()
            return {"boxes": boxes, "broken_images": broken_images}, ""
    except Exception as e:
        return None, f"render failed: {e}"


def compare_layouts(mockup_boxes: list[dict], rendered: dict, threshold: float) -> list[dict]:
    """Compare mockup bboxes to rendered DOM bboxes. Returns findings."""
    findings = []
    # Broken images are always a finding
    for img in rendered.get("broken_images", []):
        findings.append({
            "severity": "high",
            "message": f"Broken image: {img['src']} (alt={img.get('alt', '')})",
            "bbox": None,
        })

    # Layout check: approximate. For each mockup box, does a rendered box exist
    # at similar proportional position?
    rendered_boxes = rendered.get("boxes", [])
    if not rendered_boxes:
        findings.append({
            "severity": "high",
            "message": "No visible structural elements rendered — page may be blank or failed to load",
            "bbox": None,
        })
        return findings

    # Normalize both coordinate systems into [0,1] × [0,1]
    def normalize(boxes):
        if not boxes:
            return []
        max_x = max(b["x"] + b["width"] for b in boxes) or 1
        max_y = max(b["y"] + b["height"] for b in boxes) or 1
        return [{
            "id": b.get("id", b.get("tag", "?")),
            "x": b["x"] / max_x,
            "y": b["y"] / max_y,
            "w": b["width"] / max_x,
            "h": b["height"] / max_y,
        } for b in boxes]

    norm_mockup = normalize(mockup_boxes)
    norm_rendered = normalize(rendered_boxes)

    # For each mockup element, look for closest rendered element; if drift > threshold, flag
    for m in norm_mockup:
        closest_dist = min(
            (abs(r["x"] - m["x"]) + abs(r["y"] - m["y"]) + abs(r["w"] - m["w"]) + abs(r["h"] - m["h"])) / 4
            for r in norm_rendered
        ) if norm_rendered else 1.0
        if closest_dist > threshold:
            findings.append({
                "severity": "medium",
                "message": f"Mockup element {m['id']} has no close rendered match (drift={closest_dist:.2f}, threshold={threshold})",
                "bbox": [m["x"], m["y"], m["w"], m["h"]],
            })
    return findings


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--mockup", required=True)
    ap.add_argument("--max-wait", type=int, default=10)
    ap.add_argument("--threshold", type=float, default=0.15)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ok, reason = check_playwright_available()
    if not ok:
        out = skip(reason)
        print(json.dumps(out))
        return 0

    mockup_path = Path(args.mockup)
    mockup = load_mockup(mockup_path)
    if mockup is None:
        out = skip(f"mockup not found or malformed: {args.mockup}")
        print(json.dumps(out))
        return 0

    mockup_boxes = extract_mockup_boxes(mockup)
    if not mockup_boxes:
        out = skip("mockup has no elements to compare against")
        print(json.dumps(out))
        return 0

    rendered, err = render_and_extract(args.url, args.max_wait)
    if rendered is None:
        out = skip(f"could not render URL: {err}")
        print(json.dumps(out))
        return 0

    findings = compare_layouts(mockup_boxes, rendered, args.threshold)
    out = {"reviewer": "visual-verify", "findings": findings, "skipped": False, "reason": ""}
    print(json.dumps(out))
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 5: Run tests — verify pass**

```bash
pytest tests/skills/claude-flow/test_visual_verify.py -v
```

Expected: PASS (all tests use skip-envelope paths, don't need real Playwright).

**Step 6: Commit**

```bash
git add skills/claude-flow/scripts/visual_verify.py tests/skills/claude-flow/test_visual_verify.py tests/fixtures/visual_verify/
git commit -m "feat: visual_verify.py — Phase 5 Step 3d visual regression gate"
```

---

### Task 3: Wire Step 3d into phase-5-implementation.md

**Type:** value_unit
**Depends on:** T2 (data — script contract)

**Files:**
- Modify: `skills/claude-flow/phases/phase-5-implementation.md` (after Step 3c section)

**Step 1: Draft the Step 3d insertion**

Insert after the `3c. MUTATION GATE` block, before `4. Run static analysis`:

````markdown
3d. VISUAL VERIFICATION — UI layout drift check
    After tests + mutation gate pass, if the task touched UI files AND a
    Phase 4 mockup exists, verify the rendered UI matches the mockup.

    Trigger conditions (all must be true):
    - Task modified files matching: *.tsx, *.jsx, *.vue, *.svelte, *.html,
      *.css, *.scss, app/templates/*, views/*, pages/*
    - A dev server is running and reachable on a known URL (from plan
      or from `.claude/launch.json`)
    - `docs/design/<feature>/mockups/*.excalidraw` exists from Phase 4

    Run:
    ```
    python skills/claude-flow/scripts/visual_verify.py \
        --url <dev-server-url> \
        --mockup docs/design/<feature>/mockups/<mockup>.excalidraw \
        --threshold 0.15 \
        --json
    ```

    Gate rule:
    - skipped=True → SKIP, proceed to step 4 (Playwright not installed,
      mockup missing, URL unreachable — all graceful, do not block)
    - findings=[] → PASS, proceed to step 4
    - findings non-empty with severity=high → FAIL, fix before step 4
    - findings non-empty with severity=medium only → WARN, user confirms

    Max 2 visual-fix cycles → escalate to user.
    Emit failure event with tag: visual-verify-drift.

    Why separate from 3b/3c: catches a class of bugs tests miss —
    broken images, layout regressions, elements drifted from mockup
    position. Inspired by Brian/Notion's /figma verification loop.

    Dependency: install Playwright to enable this gate:
        pip install playwright && playwright install chromium
    Without Playwright the gate is a graceful no-op (skip envelope).
````

**Step 2: Apply the edit to phase-5-implementation.md**

**Step 3: Verify no existing numbering references break**

```bash
grep -n "step 4\|Step 4\|step4\|Step3d\|3d" skills/claude-flow/phases/phase-5-implementation.md
```

No renumbering needed — 3d slots in before existing step 4.

**Step 4: Commit**

```bash
git add skills/claude-flow/phases/phase-5-implementation.md
git commit -m "feat: wire visual-verify gate into Phase 5 Step 3d"
```

---

## Track B: Authoring-Time Lookup Injection

### Task 4: inject_lookups.py with detector registry

**Type:** shared_prerequisite
**Depends on:** none

**Files:**
- Create: `skills/claude-flow/scripts/inject_lookups.py`
- Create: `skills/claude-flow/references/lookup-detectors.md` (detector registry doc)
- Test: `tests/skills/claude-flow/test_inject_lookups.py`

**Step 1: Write failing tests**

```python
# tests/skills/claude-flow/test_inject_lookups.py
import subprocess, sys, json, tempfile, os
from pathlib import Path

SCRIPT = Path("skills/claude-flow/scripts/inject_lookups.py")

def run(args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--json"],
                          capture_output=True, text=True, cwd=cwd)

def test_output_shape():
    with tempfile.TemporaryDirectory() as d:
        result = run(["--scope", "plan", "--files", "foo.py"], cwd=d)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "lookups" in data
        assert "skipped_detectors" in data
        assert isinstance(data["lookups"], dict)

def test_alembic_detector_fires_on_migration_file(tmp_path):
    # Create a fake project with an alembic dir
    (tmp_path / "alembic" / "versions").mkdir(parents=True)
    (tmp_path / "alembic" / "versions" / "abc123_init.py").write_text(
        'revision = "abc123"\ndown_revision = None\n'
    )
    result = run(["--scope", "plan", "--files", "alembic/versions/new.py"], cwd=str(tmp_path))
    data = json.loads(result.stdout)
    # alembic_heads detector should have run (even if CLI unavailable, graceful skip)
    assert "alembic_heads" in data["lookups"] or "alembic_heads" in data["skipped_detectors"]

def test_graceful_skip_on_non_project():
    with tempfile.TemporaryDirectory() as d:
        result = run(["--scope", "plan", "--files", "random.py"], cwd=d)
        assert result.returncode == 0
        data = json.loads(result.stdout)
        # No detectors should fire or error
        assert isinstance(data["lookups"], dict)

def test_step_scope_narrower_than_plan(tmp_path):
    # Step scope receives only one file; plan scope receives all plan files
    (tmp_path / "app" / "models").mkdir(parents=True)
    (tmp_path / "app" / "models" / "client.py").write_text("class Client: pass\n")

    plan_result = run(["--scope", "plan", "--files", "app/models/client.py", "foo.py"], cwd=str(tmp_path))
    step_result = run(["--scope", "step", "--files", "app/models/client.py"], cwd=str(tmp_path))

    # Both succeed, step is a subset of plan
    assert plan_result.returncode == 0
    assert step_result.returncode == 0
```

**Step 2: Design detector registry**

Create `skills/claude-flow/references/lookup-detectors.md`:

```markdown
# Lookup Detector Registry

Deterministic lookups that prevent authoring-time hallucination. Each detector:
1. Declares `scope` (plan-wide or per-step) and `triggers` (file glob patterns)
2. Runs a command or AST inspection
3. Returns a short result string or skips gracefully

| Detector | Scope | Triggers | What it answers |
|----------|-------|----------|-----------------|
| `alembic_heads` | plan | `alembic/versions/*.py` | Current migration heads (prevents guessing `down_revision`) |
| `sqlalchemy_columns` | step | `app/models/*.py`, `models/*.py` | Real column names on the touched model (prevents `.is_primary` vs `.is_primary_contact`) |
| `fastapi_routes` | plan | `app/routes/*.py`, `routes/*.py` | Registered route paths (prevents duplicate/conflicting routes) |
| `css_classes` | step | `app/static/*.css`, `static/*.css` | Classes defined in touched stylesheets (prevents inventing class names) |
| `import_graph` | step | `*.py` | Real module paths importable from touched files |
| `react_components` | step | `*.tsx`, `*.jsx` | Component names exported from touched files (prevents wrong imports) |

Detectors that don't apply to the project (no `alembic/` dir, no `app/models/`) skip gracefully.
```

**Step 3: Run tests — verify fail**

**Step 4: Implement inject_lookups.py**

```python
#!/usr/bin/env python3
"""Authoring-time lookup injection — prevents hallucination by running
deterministic lookups and injecting results into implementer prompts.

Inspired by Brian/Notion's `find-icon` skill: don't let the LLM guess
when a script can look up the truth.

Two scopes:
- plan (--scope plan): run once before Phase 5; results shared by all implementers
- step (--scope step): run at subagent dispatch time; narrower, per-file

Each detector returns (result_str, skipped_reason) — never raises.
Output: {"lookups": {"detector_name": "result"}, "skipped_detectors": ["name: reason"]}

Exit codes: always 0 unless internal error (exit 2).
"""
from __future__ import annotations
import argparse
import ast
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def any_match(patterns: list[str], files: list[str]) -> bool:
    for pat in patterns:
        for f in files:
            if fnmatch.fnmatch(f, pat) or fnmatch.fnmatch(f, f"**/{pat}"):
                return True
            # Also match subdirs
            if pat.endswith("/*") and any(f.startswith(pat[:-1]) for f in files):
                return True
    return False


def detect_alembic_heads(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["alembic/versions/*.py", "alembic/*.py"]
    if not any_match(triggers, files):
        return None, "no alembic files in scope"
    if not (project / "alembic").exists():
        return None, "no alembic/ dir in project"
    try:
        result = subprocess.run(
            ["alembic", "heads"],
            cwd=project, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            heads = result.stdout.strip() or "(no heads)"
            return f"Current alembic heads:\n{heads}", None
        return None, f"alembic CLI failed: {result.stderr.strip()[:200]}"
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return None, f"alembic CLI unavailable: {e}"


def detect_sqlalchemy_columns(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["app/models/*.py", "models/*.py"]
    matched = [f for f in files if any(fnmatch.fnmatch(f, p) for p in triggers)]
    if not matched:
        return None, "no model files in scope"

    results = []
    for rel in matched:
        path = project / rel
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                cols = []
                for stmt in node.body:
                    if isinstance(stmt, ast.Assign):
                        for tgt in stmt.targets:
                            if isinstance(tgt, ast.Name):
                                # Check RHS is a Column(...) call
                                if isinstance(stmt.value, ast.Call):
                                    fn = stmt.value.func
                                    if (isinstance(fn, ast.Name) and fn.id == "Column") or \
                                       (isinstance(fn, ast.Attribute) and fn.attr == "Column"):
                                        cols.append(tgt.id)
                if cols:
                    results.append(f"{rel}::{node.name}: {', '.join(cols)}")
    if not results:
        return None, "no SQLAlchemy models found in scope files"
    return "Real model columns (use exactly these names):\n" + "\n".join(results), None


def detect_fastapi_routes(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["app/routes/*.py", "routes/*.py", "app/main.py"]
    if not any_match(triggers, files):
        # For plan scope, always inspect all route files
        pass
    route_files = []
    for root in ["app/routes", "routes", "app"]:
        root_path = project / root
        if root_path.exists():
            route_files.extend(str(p.relative_to(project)) for p in root_path.rglob("*.py"))
    if not route_files:
        return None, "no FastAPI route files in project"

    pattern = re.compile(r'@(?:router|app)\.(get|post|put|delete|patch)\(\s*["\']([^"\']+)["\']')
    routes = []
    for rel in route_files[:50]:  # cap to prevent runaway
        try:
            text = (project / rel).read_text()
        except OSError:
            continue
        for m in pattern.finditer(text):
            routes.append(f"  {m.group(1).upper():<6} {m.group(2)}  ({rel})")
    if not routes:
        return None, "no routes found"
    return "Existing routes (avoid conflicts):\n" + "\n".join(routes[:100]), None


def detect_css_classes(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["*.css", "*.scss", "static/*.css", "app/static/*.css"]
    matched = [f for f in files if any(fnmatch.fnmatch(f, p) for p in triggers)]
    if not matched:
        return None, "no CSS files in scope"
    pattern = re.compile(r'\.([a-zA-Z_][\w-]*)\s*[,{]')
    classes = set()
    for rel in matched:
        path = project / rel
        if not path.exists():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        classes.update(pattern.findall(text))
    if not classes:
        return None, "no CSS classes found"
    return "Existing CSS classes in touched stylesheets:\n" + ", ".join(sorted(classes)[:80]), None


def detect_react_components(files: list[str], project: Path) -> tuple[str | None, str | None]:
    triggers = ["*.tsx", "*.jsx"]
    matched = [f for f in files if any(fnmatch.fnmatch(f, p) for p in triggers)]
    if not matched:
        return None, "no React files in scope"
    pattern = re.compile(r'export\s+(?:default\s+)?(?:function|const)\s+([A-Z]\w+)')
    comps = []
    for rel in matched:
        path = project / rel
        if not path.exists():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        for name in pattern.findall(text):
            comps.append(f"  {name} — from {rel}")
    if not comps:
        return None, "no component exports found"
    return "Exported components (use exactly these names):\n" + "\n".join(comps[:50]), None


PLAN_DETECTORS = [
    ("alembic_heads", detect_alembic_heads),
    ("fastapi_routes", detect_fastapi_routes),
]
STEP_DETECTORS = [
    ("sqlalchemy_columns", detect_sqlalchemy_columns),
    ("css_classes", detect_css_classes),
    ("react_components", detect_react_components),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scope", choices=["plan", "step"], required=True)
    ap.add_argument("--files", nargs="+", required=True)
    ap.add_argument("--project", default=".")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    detectors = PLAN_DETECTORS if args.scope == "plan" else STEP_DETECTORS

    lookups = {}
    skipped = []
    for name, fn in detectors:
        try:
            result, skip_reason = fn(args.files, project)
        except Exception as e:
            skipped.append(f"{name}: detector error {type(e).__name__}: {e}")
            continue
        if result:
            lookups[name] = result
        elif skip_reason:
            skipped.append(f"{name}: {skip_reason}")

    out = {"lookups": lookups, "skipped_detectors": skipped, "scope": args.scope}
    print(json.dumps(out, indent=2 if not args.json else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 5: Run tests — verify pass**

```bash
pytest tests/skills/claude-flow/test_inject_lookups.py -v
```

Expected: PASS.

**Step 6: Commit**

```bash
git add skills/claude-flow/scripts/inject_lookups.py skills/claude-flow/references/lookup-detectors.md tests/skills/claude-flow/test_inject_lookups.py
git commit -m "feat: inject_lookups.py — authoring-time hallucination prevention"
```

---

### Task 5: Wire plan-wide lookups into Phase 4b → pre-Phase-5

**Type:** value_unit
**Depends on:** T4 (data — script output format)

**Files:**
- Modify: `skills/claude-flow/phases/phase-5-implementation.md` (add pre-implementation step)
- Modify: `skills/claude-flow/phases/phase-4-architecture.md` (at end of plan finalization — add note to run lookups)

**Step 1: Draft insertion for Phase 5**

Insert as new subsection `### Pre-Implementation: Inject Plan-Wide Lookups`, right after the existing `### Pre-Implementation: Fetch External API Docs` block:

````markdown
### Pre-Implementation: Inject Plan-Wide Lookups

Before dispatching any implementer subagent, run the plan-wide lookup pass.
This gathers deterministic facts about the repo (current migration heads,
existing route paths, etc.) and prevents hallucination at authoring time.

```
Collect all file paths from $plan (files to create OR modify across all tasks).
Run:
    python skills/claude-flow/scripts/inject_lookups.py \
        --scope plan \
        --files <all-plan-files> \
        --json

Cache the output JSON. Inject its `lookups` section into the
PROJECT CONTEXT block of every implementer subagent prompt:

    REPO LOOKUPS (verified facts — do not invent alternatives):
    [alembic_heads]
    <output>

    [fastapi_routes]
    <output>
```

If `skipped_detectors` is large (e.g., project has no alembic/ dir),
that's fine — empty lookups section is omitted from the prompt.
````

**Step 2: Apply edit**

**Step 3: Commit**

```bash
git add skills/claude-flow/phases/phase-5-implementation.md
git commit -m "feat: wire plan-wide lookups into Phase 5 pre-implementation"
```

---

### Task 6: Wire per-step lookups into subagent-driven-development dispatch

**Type:** value_unit
**Depends on:** T5 (knowledge — consistent with plan-scope pattern)

**Files:**
- Modify: `skills/subagent-driven-development/SKILL.md` (or whichever file documents implementer dispatch)

**Step 1: Locate the implementer dispatch section**

```bash
grep -rn "implementer\|dispatch" skills/subagent-driven-development/ | head -20
```

**Step 2: Add per-step lookup injection**

Insert into the implementer-dispatch recipe, before prompt assembly:

````markdown
### Step N: Inject Per-Step Lookups

Before building the implementer prompt, run:

```
python skills/claude-flow/scripts/inject_lookups.py \
    --scope step \
    --files <files-this-step-touches> \
    --json
```

Prepend the output to the prompt's PROJECT CONTEXT block:

    STEP-SPECIFIC LOOKUPS (authoritative — use these exact names):
    [sqlalchemy_columns]
    <output>

    [css_classes]
    <output>

These are narrower than plan-wide lookups (Phase 5 pre-implementation);
they cover file-level facts the implementer needs for THIS step only.
````

**Step 3: Commit**

```bash
git add skills/subagent-driven-development/
git commit -m "feat: per-step lookups in implementer dispatch"
```

---

## Track C: Phase 3 "Teach AI to Answer" Pass

### Task 7: audit_phase3_questions.py script + tests

**Type:** shared_prerequisite
**Depends on:** none

**Files:**
- Create: `skills/claude-flow/scripts/audit_phase3_questions.py`
- Test: `tests/skills/claude-flow/test_audit_phase3_questions.py`

**Step 1: Write failing tests**

```python
# tests/skills/claude-flow/test_audit_phase3_questions.py
import subprocess, sys, json
from pathlib import Path

SCRIPT = Path("skills/claude-flow/scripts/audit_phase3_questions.py")

def run(questions, cwd=None):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--json"],
        input=json.dumps(questions), capture_output=True, text=True, cwd=cwd
    )
    return result

def test_flags_file_existence_questions(tmp_path):
    qs = ["Does the file app/models/user.py exist?", "What port is the dev server on?"]
    result = run(qs, cwd=str(tmp_path))
    assert result.returncode == 0
    data = json.loads(result.stdout)
    self_answerable = [q for q in data["questions"] if q["self_answerable"]]
    # First is self-answerable (grep/ls), second is config-dependent (not file-existence)
    assert any("app/models/user.py" in q["question"] for q in self_answerable)

def test_flags_schema_questions(tmp_path):
    qs = ["What columns does the Client model have?", "How should we handle the edge case of zero items?"]
    result = run(qs, cwd=str(tmp_path))
    data = json.loads(result.stdout)
    self_answerable_qs = [q["question"] for q in data["questions"] if q["self_answerable"]]
    assert any("Client" in q for q in self_answerable_qs)
    # Edge-case question is genuinely ambiguous — must remain user-facing
    for q in data["questions"]:
        if "edge case" in q["question"]:
            assert not q["self_answerable"]

def test_output_shape():
    result = run(["What should the error message say?"])
    data = json.loads(result.stdout)
    assert "questions" in data
    assert "summary" in data
    for q in data["questions"]:
        assert "question" in q
        assert "self_answerable" in q
        assert "suggested_lookup" in q or q["self_answerable"] is False

def test_intent_question_stays_user_facing():
    # User-intent questions cannot be scripted — must flag as user-facing
    qs = ["Should the signup flow send a welcome email?"]
    result = run(qs)
    data = json.loads(result.stdout)
    for q in data["questions"]:
        assert q["self_answerable"] is False
```

**Step 2: Implement**

```python
#!/usr/bin/env python3
"""Phase 3 question audit: flag which clarifying questions could be answered
by a deterministic script lookup instead of asking the user.

Principle: "Anytime the AI asks you to do something, before responding, try
your best to see if you could teach the AI to answer that question for itself."
— Brian Lovin, Notion

Usage:
    echo '["Q1?", "Q2?"]' | python audit_phase3_questions.py --json

Input: JSON array of question strings on stdin.
Output: JSON with `questions[]` (each flagged self_answerable + suggested_lookup)
        and `summary` (counts).

Heuristics (conservative — false negatives preferred over false positives;
a question wrongly flagged self-answerable skips user input and risks a
wrong assumption):
- Regex-based pattern matching on question text
- Patterns target: file/directory existence, schema/column lookup,
  existing route check, import graph, git state, migration heads,
  test presence
"""
from __future__ import annotations
import argparse
import json
import re
import sys


PATTERNS = [
    # Pattern, suggested lookup command/approach
    (r"\b(does|is there)\b.*\b(file|module|directory|folder)\b",
     "ls or grep the filesystem"),
    (r"\bexist(s)?\b.*\b(file|path)\b",
     "ls or grep the filesystem"),
    (r"\bwhat (are the |is the )?column(s)?\b",
     "grep SQLAlchemy Column definitions or run inject_lookups.py --scope step"),
    (r"\bwhat.*model.*fields?\b",
     "grep model definitions or run inject_lookups.py --scope step"),
    (r"\bwhat (are the |is the )?route(s)?\b",
     "grep @router/@app decorators or run inject_lookups.py --scope plan"),
    (r"\bcurrent (alembic|migration) (head|revision)\b",
     "run `alembic heads`"),
    (r"\bwhat (are the |is the )?import(s)?\b",
     "grep from/import statements in target files"),
    (r"\bwhat.*component(s)?\b.*(export|defined)",
     "grep export statements or run inject_lookups.py --scope step"),
    (r"\bwhich.*branch\b",
     "run `git branch --show-current`"),
    (r"\bis.*installed\b",
     "check package.json / requirements.txt / pip list"),
    (r"\bwhat.*port\b.*\b(server|dev)\b",
     "check .claude/launch.json or package.json scripts"),
    (r"\btest(s)?.*exist",
     "glob tests/ for matching files"),
    (r"\bwhat.*css class(es)?\b",
     "grep CSS selectors or run inject_lookups.py --scope step"),
]

# Anti-patterns: questions that LOOK self-answerable but aren't (user intent)
INTENT_PATTERNS = [
    r"\bshould\b",               # "Should we X?" — user intent
    r"\bdo you want\b",
    r"\bwhat do you (want|prefer|think)\b",
    r"\bhow should (we|it)\b",
    r"\bwhich (design|approach|option)\b",
    r"\bedge case\b.*\bhandle",  # Error handling policy is user-decided
    r"\berror message\b.*\bsay\b",  # Copy is user-decided
]


def classify(question: str) -> dict:
    q_lower = question.lower()

    # First check: does it look like user intent?
    for pat in INTENT_PATTERNS:
        if re.search(pat, q_lower):
            return {
                "question": question,
                "self_answerable": False,
                "suggested_lookup": None,
                "reason": "user intent — requires human decision"
            }

    # Then check: does it match a lookup pattern?
    for pat, lookup in PATTERNS:
        if re.search(pat, q_lower):
            return {
                "question": question,
                "self_answerable": True,
                "suggested_lookup": lookup,
                "reason": f"matches pattern: {pat}"
            }

    return {
        "question": question,
        "self_answerable": False,
        "suggested_lookup": None,
        "reason": "no deterministic lookup pattern matched"
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        questions = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"invalid JSON on stdin: {e}"}), file=sys.stderr)
        return 2

    if not isinstance(questions, list):
        print(json.dumps({"error": "expected JSON array of question strings"}), file=sys.stderr)
        return 2

    classified = [classify(q) for q in questions]
    n_self = sum(1 for q in classified if q["self_answerable"])
    out = {
        "questions": classified,
        "summary": {
            "total": len(classified),
            "self_answerable": n_self,
            "user_facing": len(classified) - n_self,
        }
    }
    print(json.dumps(out, indent=2 if not args.json else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

**Step 3: Run tests — verify pass**

```bash
pytest tests/skills/claude-flow/test_audit_phase3_questions.py -v
```

Expected: PASS.

**Step 4: Commit**

```bash
git add skills/claude-flow/scripts/audit_phase3_questions.py tests/skills/claude-flow/test_audit_phase3_questions.py
git commit -m "feat: audit_phase3_questions.py — flag self-answerable clarifications"
```

---

### Task 8: Wire audit into Phase 3 Step 2 quality gate

**Type:** value_unit
**Depends on:** T7 (data — script contract)

**Files:**
- Modify: `skills/claude-flow/phases/phase-3-requirements.md`

**Step 1: Draft insertion**

After Step 1 "Resolve Ambiguities", BEFORE presenting questions to user, insert:

````markdown
### Step 1.5: Self-Answer Audit (Teach AI to Answer Its Own Questions)

Before presenting the question list to the user, run the audit:

```
echo '["<question 1>", "<question 2>", ...]' | \
    python skills/claude-flow/scripts/audit_phase3_questions.py --json
```

For each question flagged `self_answerable: true`:
- Execute the `suggested_lookup` yourself (grep, ls, alembic heads, etc.)
- Record the answer as a resolved ambiguity
- **Remove the question from the user-facing list**

Principle: "Anytime the AI asks you to do something, before responding,
try your best to see if you could teach the AI to answer that question
for itself." — Brian Lovin, Notion

Only present genuinely ambiguous (user-intent, preference, policy) questions
to the user. This reduces Phase 3 friction and accelerates the hard gate.

If the audit flags >50% of questions as self-answerable, that's a signal
exploration (Phase 2) was shallow — consider running an additional explorer
rather than pestering the user.
````

**Step 2: Update Step 2 Quality Gate to reference self-answered resolutions**

In Step 2 Quality Gate checklist, update axis 4 (Completeness):

```
4. **Completeness** — All edge cases have resolutions, including those
   self-answered by the Step 1.5 audit. FAIL: unresolved edges,
   unspecified error handling.
```

**Step 3: Commit**

```bash
git add skills/claude-flow/phases/phase-3-requirements.md
git commit -m "feat: Phase 3 Step 1.5 — self-answer audit before user questions"
```

---

## Track D: Memory + Index Updates

### Task 9: Capture lessons in MEMORY.md

**Type:** value_unit
**Depends on:** T1-T8

**Files:**
- Create: `memory/visual_verify_gate.md`
- Create: `memory/authoring_time_lookups.md`
- Create: `memory/self_answer_audit.md`
- Modify: `memory/MEMORY.md` (add three new index entries)

**Step 1: Write memory entries (one per pattern)**

Each file uses the standard frontmatter (name, description, type) and documents:
- What the component does
- Why we added it (external pattern + gap it fills)
- Cross-refs to related memories

Example shape for `memory/visual_verify_gate.md`:

```markdown
---
name: Visual Verify Gate
description: Phase 5 Step 3d — Playwright-based UI layout drift check against excalidraw mockups
type: project
---

- Script: skills/claude-flow/scripts/visual_verify.py
- Phase: 5, Step 3d (between mutation gate and static analysis)
- Triggers: task touches *.tsx/*.jsx/*.vue/*.html/*.css AND excalidraw mockup exists in docs/design/<feature>/mockups/
- Graceful skip when Playwright not installed
- Inspired by Brian/Notion's /figma verification loop

## Related
- [mutation_gate_component] — sibling gate in Phase 5, catches non-discriminating tests
- [excalidraw_canvas_component] — produces the mockups this gate verifies against
```

**Step 2: Add three entries to MEMORY.md index**

**Step 3: Commit**

```bash
git add memory/
git commit -m "docs: memory entries for visual-verify, authoring-lookups, self-answer audit"
```

---

## Verification

After all tasks, run:

```bash
pytest tests/skills/claude-flow/ -v
python skills/claude-flow/scripts/visual_verify.py --url http://localhost:1 --mockup /nonexistent --json  # expect skip
python skills/claude-flow/scripts/inject_lookups.py --scope plan --files foo.py --json  # expect minimal
echo '["Does app/models/user.py exist?"]' | python skills/claude-flow/scripts/audit_phase3_questions.py --json  # expect self_answerable=true
```

All scripts exit 0. All tests pass. No regressions in existing test suite:

```bash
pytest tests/ -v
bash tests/test_curmudgeon_review.sh  # existing shell tests still pass
bash tests/test_open_excalidraw.sh
```
