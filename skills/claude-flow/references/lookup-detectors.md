# Lookup Detector Registry

Deterministic authoring-time lookups that prevent hallucination. Consumed by
`skills/claude-flow/scripts/inject_lookups.py`.

Principle (Brian Lovin, Notion): *"Anytime the AI asks you to do something,
before responding, try your best to see if you could teach the AI to answer
that question for itself."*

Same pattern applied to authoring: before letting the implementer invent a
column name, route path, or component name, have a script look up the real one.

## Scopes

- **plan** — run once, before Phase 5 dispatches implementers. Output shared
  across all implementer subagents. Good for facts that span the whole plan
  (alembic heads, existing routes, global state).
- **step** — run at each subagent dispatch. Narrower file list, more specific
  output. Good for file-level facts (columns on the touched model,
  CSS classes in the touched stylesheet, components exported from the
  touched TSX file).

## Detectors

| Detector | Scope | Triggers | What it answers |
|----------|-------|----------|-----------------|
| `alembic_heads` | plan | `alembic/versions/*.py`, `alembic/*.py` | Current migration heads (prevents guessing `down_revision`) |
| `fastapi_routes` | plan | `app/routes/*.py`, `routes/*.py`, `app/main.py` | Existing registered routes (prevents duplicates/conflicts) |
| `sqlalchemy_columns` | step | `app/models/*.py`, `models/*.py` | Real column names on touched models (prevents `.is_primary` vs `.is_primary_contact`) |
| `css_classes` | step | `*.css`, `*.scss`, `static/*.css`, `app/static/*.css` | Classes defined in touched stylesheets (prevents inventing class names) |
| `react_components` | step | `*.tsx`, `*.jsx` | Component names exported from touched files (prevents wrong imports) |

## Graceful skip

Every detector returns `(result, skip_reason)`. If the detector doesn't apply
(no `alembic/` dir in project, no model files in scope, CLI unavailable), it
returns `(None, "reason")` and the script lists it under `skipped_detectors`.

No detector should ever raise — unhandled exceptions are caught at the top
level and surfaced as skip entries.

## Adding a detector

1. Write a function `detect_<name>(files, project) -> tuple[str|None, str|None]`
2. Register it in `PLAN_DETECTORS` or `STEP_DETECTORS`
3. Add a row to the table above
4. Add a test in `tests/skills/claude-flow/test_inject_lookups.py`
