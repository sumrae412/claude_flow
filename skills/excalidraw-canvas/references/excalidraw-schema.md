# Excalidraw Schema (Compact Subset)

Excalidraw's full JSON schema has dozens of element types and hundreds of optional properties. LLMs generating free-form `.excalidraw` JSON reliably hallucinate fields, misuse binding refs, and produce files that load but render wrong. This document defines the subset the `excalidraw-canvas` skill is allowed to emit — tight enough to generate correctly, broad enough to express UI mockups and architecture diagrams.

Files written with this subset load in excalidraw.com and the VS Code Excalidraw extension without warnings.

---

## Top-Level Envelope

Every `.excalidraw` file is a JSON object with these five keys:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [],
  "appState": { "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

- `type` — always the literal string `"excalidraw"`.
- `version` — always `2`. This is the file-format version, not a semantic version.
- `source` — the URL the file came from. Use `"https://excalidraw.com"` for generated files; this is what the VS Code extension writes.
- `elements` — array of element objects (see below). Order matters only for z-index (later = on top).
- `appState` — object. `viewBackgroundColor` (hex string) is the only field this skill sets. Defaults to white.
- `files` — object. Used for embedded images and libraries. This skill writes `{}`.

---

## Supported Element Types

Every element object shares a required base: `id` (unique string per file), `type`, and positioning fields. Colors are hex strings (`"#000000"`) or the literal `"transparent"`.

### rectangle

```json
{
  "id": "r1",
  "type": "rectangle",
  "x": 100, "y": 100,
  "width": 200, "height": 60,
  "strokeColor": "#000000",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "groupIds": []
}
```

Fields: `id`, `type`, `x`, `y`, `width`, `height`, `strokeColor`, `backgroundColor` required. `fillStyle` (`"solid"` / `"hachure"` / `"cross-hatch"`, default `"hachure"`) and `groupIds` (array of strings, default `[]`) optional.

### ellipse

Same fields as `rectangle`, `type: "ellipse"`. Rendered as an axis-aligned ellipse inscribed in the bounding box.

### text

```json
{
  "id": "t1",
  "type": "text",
  "x": 120, "y": 120,
  "text": "Login",
  "fontSize": 20,
  "fontFamily": 1,
  "strokeColor": "#000000",
  "width": 60, "height": 24
}
```

Fields: `id`, `type`, `x`, `y`, `text` required. `fontSize` (number, default `20`), `fontFamily` (integer: `1` hand-drawn, `2` normal, `3` code; default `1`), `strokeColor` (default `"#000000"`), and `width`/`height` (hints; the editor recomputes on load, but include them so placement looks right before first load) optional.

### arrow

```json
{
  "id": "a1",
  "type": "arrow",
  "x": 300, "y": 130,
  "width": 100, "height": 0,
  "points": [[0, 0], [100, 0]],
  "strokeColor": "#000000"
}
```

Fields: `id`, `type`, `x`, `y`, `width`, `height`, `points` required. `points` is a list of `[dx, dy]` pairs relative to `(x, y)` — the first is always `[0, 0]`, the last equals `[width, height]`. `startBinding` / `endBinding` (objects with `elementId` and `focus`/`gap` numbers) are optional and only used when the arrow visually attaches to another element; omit unless needed.

### line

Same shape as `arrow`, `type: "line"`, no arrowheads. Use for dividers and layout guides.

---

## Grouping

`groupIds` on any element is an array of group-id strings. Elements sharing a `groupIds` entry move together in the editor. Use one group per logical UI component (card, form, button group) so the user can drag a whole unit without picking each shape.

---

## Minimal Valid File

Smallest file that loads cleanly (copied from `tests/fixtures/excalidraw/simple.excalidraw`):

```json
{"type":"excalidraw","version":2,"source":"https://excalidraw.com","elements":[{"type":"rectangle","x":0,"y":0,"width":100,"height":50,"id":"a","strokeColor":"#000","backgroundColor":"transparent","fillStyle":"solid"}],"appState":{"viewBackgroundColor":"#fff"},"files":{}}
```

Use this as a sanity template: if your generation can't at least produce this, something upstream is wrong.

---

## Richer Example: Login Screen Mockup

A four-element login screen (title, username field, password field, submit button), each in its own group, rendered left-aligned inside an 800-wide canvas:

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [
    {
      "id": "title",
      "type": "text",
      "x": 100, "y": 80,
      "text": "Sign in",
      "fontSize": 32,
      "fontFamily": 1,
      "strokeColor": "#000000",
      "width": 120, "height": 40,
      "groupIds": ["header"]
    },
    {
      "id": "user-box",
      "type": "rectangle",
      "x": 100, "y": 160,
      "width": 280, "height": 40,
      "strokeColor": "#555555",
      "backgroundColor": "transparent",
      "fillStyle": "solid",
      "groupIds": ["username-field"]
    },
    {
      "id": "user-label",
      "type": "text",
      "x": 108, "y": 170,
      "text": "Username",
      "fontSize": 16,
      "fontFamily": 1,
      "strokeColor": "#888888",
      "width": 80, "height": 20,
      "groupIds": ["username-field"]
    },
    {
      "id": "pass-box",
      "type": "rectangle",
      "x": 100, "y": 220,
      "width": 280, "height": 40,
      "strokeColor": "#555555",
      "backgroundColor": "transparent",
      "fillStyle": "solid",
      "groupIds": ["password-field"]
    },
    {
      "id": "pass-label",
      "type": "text",
      "x": 108, "y": 230,
      "text": "Password",
      "fontSize": 16,
      "fontFamily": 1,
      "strokeColor": "#888888",
      "width": 80, "height": 20,
      "groupIds": ["password-field"]
    },
    {
      "id": "submit-btn",
      "type": "rectangle",
      "x": 100, "y": 290,
      "width": 120, "height": 44,
      "strokeColor": "#1971c2",
      "backgroundColor": "#1971c2",
      "fillStyle": "solid",
      "groupIds": ["submit"]
    },
    {
      "id": "submit-label",
      "type": "text",
      "x": 135, "y": 301,
      "text": "Sign in",
      "fontSize": 18,
      "fontFamily": 1,
      "strokeColor": "#ffffff",
      "width": 60, "height": 22,
      "groupIds": ["submit"]
    }
  ],
  "appState": { "viewBackgroundColor": "#ffffff" },
  "files": {}
}
```

Notes on this example:
- Each logical component (title, username, password, submit) has its own `groupIds` entry so the user can drag the whole unit when editing.
- Labels are positioned inside their field rectangles (not bound via `startBinding`) — keeps the JSON simple and lets the user re-layout freely.
- The submit button uses a filled rectangle plus a white text label — no dedicated "button" element type exists in the subset.

---

## Validation Checklist

Before writing any `.excalidraw` file, verify:

- [ ] File parses as JSON (`json.loads(text)` succeeds).
- [ ] Top-level has exactly `type`, `version`, `source`, `elements`, `appState`, `files`.
- [ ] `type` is `"excalidraw"` and `version` is `2` (integer, not string).
- [ ] Every element has a unique `id` within the file.
- [ ] Every element's `type` is one of: `rectangle`, `ellipse`, `text`, `arrow`, `line`.
- [ ] Every element has `x` and `y` as numbers.
- [ ] `rectangle` / `ellipse` have `width`, `height`, `strokeColor`, `backgroundColor`.
- [ ] `text` has a non-empty `text` string.
- [ ] `arrow` / `line` have `points` with at least two entries; last entry equals `[width, height]`.
- [ ] No colors except hex strings (`"#rrggbb"` or `"#rgb"`) or the literal `"transparent"`.

If any check fails, regenerate rather than patching by hand — partial fixes tend to leave the element set inconsistent.
