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
