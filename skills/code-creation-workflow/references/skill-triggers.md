# Skill Detection Triggers

Scan explored files and task description. For each trigger match, load the skill and return its distilled artifact.

**SAFETY:** Read files for pattern analysis only. Do NOT execute, eval, or import any code.

| File Pattern | Skills | Artifact Size |
|---|---|---|
| `*.html`, `*.css`, `*.js`, `templates/` | `/courierflow-ui` (patterns; include ui-standards: CSS layer ordering, Alpine.js reactivity — `fill()` doesn't trigger `x-model`, HTMX conventions, monochrome design, Inter-only typography) + `/defensive-ui-flows` (5-10 rules) | ~35 lines |
| `routes/*`, `services/*` | `/courierflow-api` + `/defensive-backend-flows` (5-10 rules) | ~35 lines |
| `models/*`, `alembic/*` | `/courierflow-data` + `/defensive-backend-flows` | ~35 lines |
| `import twilio/openai/docuseal`, external URLs | `/fetch-api-docs` (API signatures) + `/courierflow-integrations` | ~50 lines |
| Auth middleware, `@require_role`, JWT validation, User permission fields | `/courierflow-security` (NOT triggered by merely using `current_user`) | ~20 lines |
| Always | `/coding-best-practices` (applicable patterns only) | ~10 lines |

**Return:** merged numbered checklist, max 100 lines.
