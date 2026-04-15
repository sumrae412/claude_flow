---
name: coding-best-practices
description: Comprehensive coding standards for Python, JavaScript, APIs, testing, and performance. Apply when writing code, reviewing PRs, debugging, or designing systems. Covers SQLAlchemy relationships, async patterns, DOM safety, REST design, and optimization techniques.
user-invocable: false
---

# Coding Best Practices

Apply these principles when writing, reviewing, or debugging code across any project.

## Quick Decision Matrix

| Question | Answer |
|----------|--------|
| Write a test? | **Always**, before implementation |
| Use async/await? | **Always** for I/O operations |
| Create migration? | **Always** when changing DB schema |
| Add type hints? | **Always** on function signatures |
| Use service layer? | **Always** for business logic |
| Using external API? | **Always** fetch docs first: `chub get <api-id> --lang py\|js` |
| Cache data? | When frequently accessed, rarely changed |
| Add index? | When queries slow or tables > 1000 rows |
| Add rate limiting? | **Always** for new endpoints |
| Use circuit breaker? | **Always** for external API calls |
| Renaming symbol? | Grep all usages across Python, templates (Jinja), and JS — same attribute name can be wrong in multiple layers silently |
| Finding all usages? | Use Grep tool to find all references |

## Risk Levels for Changes

- **HIGH** (research first): DB types/migrations, event loops, auth, test fixtures
- **MEDIUM**: API changes, service layer, async additions, integrations
- **LOW**: UI templates, CSS, docs, config

## Core Principles

1. **Simple > Clever** - Readable code beats clever code
2. **Test First** - Write tests before implementation
3. **Fail Fast** - Validate early, provide clear errors
4. **DRY** - Extract repeated patterns (but don't over-abstract)
5. **Single Responsibility** - Each function does one thing well

## Single-Roundtrip Aggregate Counts

When a page needs multiple independent count queries, combine them into a single SELECT using `scalar_subquery()`:
```python
q1 = select(func.count(M1.id)).where(...).scalar_subquery()
q2 = select(func.count(M2.id)).where(...).scalar_subquery()
result = await db.execute(select(q1.label("c1"), q2.label("c2")))
row = result.one()
```
This avoids N+1 roundtrips. See `app/services/counts_service.py` for a 7-subquery example.

## Detailed Guidelines

For specific patterns and examples, see:

- [Python Patterns](docs/python-patterns.md) - SQLAlchemy, async, transactions, migrations
- [JavaScript Safety](docs/javascript-safety.md) - DOM, events, WebSocket
- [API Design](docs/api-design.md) - REST, routing, HTTP methods
- [Testing Guide](docs/testing.md) - Test types and when to use them
- [Performance](docs/performance.md) - Caching, circuit breakers, optimization
- [Security](docs/security.md) - OWASP top 10, input validation, secrets

## Shell Scripts That Call External LLM CLIs

Three discipline rules for any bash script that shells out to an external LLM (Codex CLI, Gemini CLI, etc.) or passes user/LLM-generated content through shell:

### 1. Put the prompt in a sibling `.txt` file, not an inline string

Bash single-quoted strings break on apostrophes. A multi-line `PERSONA='You are a staff engineer. You have seen it all. Don\'t...'` appears to work until the next editor adds "don't" or "it's" somewhere and the string closes mid-sentence. Silently. Double-quoted strings break on `$`, `` ` ``, and `"`.

```bash
# BAD — one apostrophe away from silent breakage
PERSONA='You are a staff engineer. You have seen it all. Do not praise. ...'

# GOOD — persona lives in a sibling file, immune to bash quoting
PERSONA_FILE="$SCRIPT_DIR/curmudgeon_persona.txt"
```

Pattern: any LLM prompt longer than a single line or likely to be edited should live in a sibling `.txt` file, `cat`'d into the prompt assembly.

### 2. Pipe large prompts to stdin, not argv

`codex exec "$(cat prompt.txt)"` passes the entire prompt as a single argv. `ARG_MAX` on macOS is ~128KB; large diffs blow past that silently and fail with `E2BIG` or truncate. If the external CLI accepts stdin, prefer it:

```bash
# BAD — prompt as argv; ARG_MAX risk on large diffs
RAW=$(codex exec --quiet "$(cat "$PROMPT_FILE")")

# GOOD — prompt on stdin; no ARG_MAX
RAW=$(codex exec --quiet --output-format json < "$PROMPT_FILE")
```

If the CLI only accepts argv, log a warning and cap the prompt size before handoff.

### 3. Cross the shell → Python boundary with env vars, not interpolation

Passing CLI output into Python via heredoc interpolation (`raw = """$RAW"""`) is shell-injection-vulnerable: if RAW contains `"""`, `` ` ``, or `$(...)`, the shell sees it before Python does. Use a quoted heredoc (`<<'PY'`) and read the value from `os.environ`:

```bash
# BAD — unquoted heredoc interpolates $RAW; quote-bomb in RAW breaks it
python3 <<PY
raw = """$RAW"""
data = json.loads(raw)
PY

# GOOD — quoted heredoc, Python reads from env; injection-safe
RAW=$RAW python3 <<'PY'
import os, json
raw = os.environ.get("RAW", "")
data = json.loads(raw)
PY
```

Adversarial verification: pass a payload containing `"""`, `` `rm -rf /` ``, and `$(whoami)` through the boundary. It should land as literal JSON string content on the Python side.

## Shell Script Cleanup Traps

When a shell script creates a side effect that must be cleaned up (temp file, symlink, background process, PID file), register the `trap` BEFORE the side effect is created — not after.

```bash
# BAD — if ln -sf fails the trap never registers; if ln -sf succeeds but
# a later assertion fails, the symlink leaks.
ln -sf "$FIX/mock-codex" "$FIX/codex"
trap 'rm -f "$FIX/codex"' EXIT

# GOOD — trap registered first; side effect has an unconditional cleanup path
trap 'rm -f "$FIX/codex"' EXIT
ln -sf "$FIX/mock-codex" "$FIX/codex"
```

Same rule for `mktemp`, background `&` jobs, `lockfile`, and anything else that persists past the script's happy path. The invariant is: **from the moment the side effect exists, there is a registered cleanup for it.**

## Type Hint Discipline

**Every function gets type hints** — parameters, return types, and `None` where applicable:

```python
# GOOD - fully annotated
async def get_workflow_by_id(
    db: AsyncSession,
    workflow_id: UUID,
    user_id: UUID,
) -> Optional[WorkflowTemplate]:
    ...

# GOOD - explicit None return
async def delete_workflow(
    db: AsyncSession,
    workflow_id: UUID,
) -> None:
    ...

# BAD - missing annotations
async def get_workflow_by_id(db, workflow_id, user_id):
    ...
```

**Rules:**
- All function parameters: annotated
- All return types: annotated (including `-> None`)
- Use `Optional[X]` or `X | None` for nullable values
- Use `TYPE_CHECKING` block for import-only types to avoid circular imports
- Collection types: `list[Step]`, `dict[str, Any]`, `set[UUID]` (Python 3.9+)

## Pre-Commit Checklist

Before committing code changes:

### Python
- [ ] Type hints on function signatures (params + return)
- [ ] `AsyncMock` for async method mocking
- [ ] `pattern=` not `regex=` in Pydantic v2
- [ ] Service layer for business logic (not in routes)

### JavaScript
- [ ] DOM elements null-checked before use
- [ ] Event handlers accept `event` parameter
- [ ] WebSocket client handles all server message types
- [ ] `Promise.all()` for parallel API calls

### Database
- [ ] Migration created for schema changes
- [ ] `foreign_keys` and `overlaps` for multiple FKs to same table
- [ ] Indexes on frequently queried columns

### API
- [ ] Route has `name=` parameter for `url_for()`
- [ ] HTTP method matches frontend expectations (PATCH vs PUT)
- [ ] Content-Type matches (JSON vs Form data)

## Alembic Migration Heads

Never parse Alembic migration files manually (e.g., with Python scripts reading `down_revision`) to determine heads. The migration chain has complex branches and merges. Use `alembic heads` CLI command, which correctly resolves the DAG. Manual parsing produces false positives.

## CI/CD Script Structure

Scripts in `scripts/` for CI/CD operations follow this structure:

1. **Docstring** with usage examples and exit codes
2. **Result dataclass** for structured output (success, message, error, dry_run, timestamp)
3. **Manager class** with all operations as methods
4. **Dry-run mode** throughout (never modify state if `--dry-run`)
5. **argparse CLI** with `--dry-run`, `--format json|text`, and operation-specific flags
6. **Exit codes**: 0=success, 1=operation failed, 2=invalid arguments

```python
@dataclass
class DeployResult:
    success: bool
    message: str
    dry_run: bool = False
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class DeployManager:
    def __init__(self, dry_run: bool = False, timeout: int = 30):
        self.dry_run = dry_run
        self.timeout = timeout
```

**Examples:** scripts/release.py, scripts/rollback.py, scripts/canary_deploy.py
