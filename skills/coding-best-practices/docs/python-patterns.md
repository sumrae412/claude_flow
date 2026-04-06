# Python Patterns

## SQLAlchemy Relationships (CRITICAL)

### The #1 Production Crash: AmbiguousForeignKeysError

Happens when a model has multiple foreign keys to the same table without proper `foreign_keys` and `overlaps` parameters.

### Rules for Multiple Foreign Keys

**Rule 1**: Specify `foreign_keys` on BOTH child and parent sides
**Rule 2**: Add `overlaps` on ALL sides
**Rule 3**: Test with `configure_mappers()`

```python
# Child model
class WorkflowInstance(Base):
    user_id = Column(GUID(), ForeignKey("users.id"))
    paused_by_user_id = Column(GUID(), ForeignKey("users.id"))

    user = relationship("User", foreign_keys=[user_id],
                       back_populates="workflow_instances", overlaps="paused_by")
    paused_by = relationship("User", foreign_keys=[paused_by_user_id],
                            overlaps="user,workflow_instances")

# Parent model - MUST have foreign_keys AND overlaps
class User(Base):
    workflow_instances = relationship("WorkflowInstance",
                                     foreign_keys="[WorkflowInstance.user_id]",  # String format on parent
                                     back_populates="user", overlaps="paused_by")
```

### Required Test

```python
def test_sqlalchemy_mapper_configuration():
    from sqlalchemy.orm import configure_mappers
    configure_mappers()  # Catches AmbiguousForeignKeysError before production!
```

### Error Quick Reference

| Error | Fix |
|-------|-----|
| `AmbiguousForeignKeysError` | Add `overlaps` to ALL relationships |
| `Could not determine join condition` | Add `foreign_keys=[column]` |
| `Back-reference conflicts` | Add `overlaps` to parent side |

---

## Guard Clauses & Early Returns

Handle errors and edge cases at the top of functions — never nest happy-path logic inside conditionals:

```python
# GOOD - guard clauses, flat structure
async def activate_workflow(
    db: AsyncSession, workflow_id: UUID, user_id: UUID
) -> WorkflowTemplate:
    workflow = await get_workflow(db, workflow_id)
    if not workflow:
        raise not_found("Workflow not found")
    if workflow.user_id != user_id:
        raise forbidden("Not your workflow")
    if workflow.state == WorkflowState.ARCHIVED:
        raise bad_request("Cannot activate archived workflow")
    if not workflow.steps:
        raise bad_request("Workflow has no steps")

    workflow.state = WorkflowState.PUBLISHED
    await db.flush()
    return workflow

# BAD - nested conditionals, hard to follow
async def activate_workflow(db, workflow_id, user_id):
    workflow = await get_workflow(db, workflow_id)
    if workflow:
        if workflow.user_id == user_id:
            if workflow.state != WorkflowState.ARCHIVED:
                if workflow.steps:
                    workflow.state = WorkflowState.PUBLISHED
                    await db.flush()
                    return workflow
                else:
                    raise bad_request("No steps")
            else:
                raise bad_request("Archived")
        else:
            raise forbidden("Not yours")
    else:
        raise not_found("Not found")
```

**Rules:**
- Validate inputs at function entry, return/raise immediately on failure
- Happy path runs at the shallowest indentation level
- Each guard handles exactly one concern
- Order guards: existence → authorization → state validity → business rules

---

## Async Patterns

### Always Use Async for I/O

```python
# GOOD - async for database operations
async def get_user(db: AsyncSession, user_id: UUID) -> Optional[User]:
    result = await db.execute(
        select(User).where(User.id == user_id)
        .options(selectinload(User.teams))
    )
    return result.scalar_one_or_none()
    # Caveat: scalar_one_or_none() is only safe when the query's WHERE clause
    # is backed by a unique DB constraint (PK, unique index). For non-unique
    # columns (email, phone, name), use scalars().first() instead —
    # scalar_one_or_none() raises MultipleResultsFound when duplicates appear.

# GOOD - async for external API calls
async def fetch_calendar_events(client: httpx.AsyncClient, token: str):
    response = await client.get("/events", headers={"Authorization": f"Bearer {token}"})
    return response.json()
```

### Async Mocking in Tests

```python
from unittest.mock import AsyncMock

# CORRECT - use AsyncMock for async methods
mock_service = AsyncMock()
mock_service.get_user.return_value = user_fixture

# Also ensure pytest.ini has:
# asyncio_mode = auto
```

---

## Transaction Safety

```python
from contextlib import asynccontextmanager

# Atomic transaction with auto-commit/rollback
async with transaction_scope(db) as session:
    await update_record(session, record_id, data)
    await create_audit_log(session, log_data)
    # Both succeed or both fail

# Nested transaction (savepoint) for partial rollback
async with transaction_scope(db) as session:
    await create_parent(session, parent_data)
    try:
        async with nested_transaction_scope(session):
            await risky_child_operation(session)
    except Exception:
        pass  # Only nested transaction rolled back, parent still committed
```

---

## Service Layer Pattern

Business logic belongs in services, not routes:

```python
# services/user_service.py
async def get_user_with_permissions(
    db: AsyncSession,
    user_id: UUID,
    requesting_user_id: UUID
) -> Optional[User]:
    """Get user if requester has permission to view."""
    user = await db.execute(
        select(User).where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = user.scalar_one_or_none()

    if not user:
        return None

    # Business logic: permission check
    if not await can_view_user(db, requesting_user_id, user_id):
        raise PermissionDenied("Cannot view this user")

    return user

# routes/users.py - thin route layer
@router.get("/{user_id}")
async def get_user_endpoint(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    user = await user_service.get_user_with_permissions(db, user_id, current_user.id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user
```

---

## Pydantic v2 Patterns

```python
from pydantic import BaseModel, Field

# CORRECT - use pattern=, not regex=
class UserCreate(BaseModel):
    email: str = Field(pattern=r'^[\w\.-]+@[\w\.-]+\.\w+$')
    phone: str = Field(pattern=r'^\+?1?\d{9,15}$')

# CORRECT - use model_config, not Config class
class UserResponse(BaseModel):
    model_config = {"from_attributes": True}  # Replaces orm_mode=True

    id: UUID
    email: str
```

---

## Common Troubleshooting

**Event loop errors in tests**: Check `pytest.ini` has `asyncio_mode = auto`

**Import errors**: `export PYTHONPATH="${PYTHONPATH}:$(pwd)"`

**Circular imports**: Use `TYPE_CHECKING` block for type hints only:
```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.user import User  # Only for type hints
```

**Slow queries**: Add indexes, use `selectinload()`, cache with Redis

---

## Database Migrations (Alembic)

### Golden Rules

1. **Always create a migration** when changing the database schema
2. **Test both upgrade AND downgrade** before deploying
3. **Never edit a migration** that's been deployed to production
4. **One logical change per migration** - easier to debug and rollback

### Creating Migrations

```bash
# Auto-generate from model changes
alembic revision --autogenerate -m "add user preferences table"

# Create empty migration for manual SQL
alembic revision -m "add partial index on active users"
```

### Migration Template

```python
"""add user preferences table

Revision ID: abc123
Revises: xyz789
Create Date: 2024-01-15
"""
from alembic import op
import sqlalchemy as sa

revision = 'abc123'
down_revision = 'xyz789'

def upgrade():
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('theme', sa.String(50), default='light'),
        sa.Column('notifications_enabled', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_user_preferences_user_id', 'user_preferences', ['user_id'])

def downgrade():
    op.drop_index('ix_user_preferences_user_id')
    op.drop_table('user_preferences')
```

### Safe Column Operations

```python
# Adding nullable column (safe)
def upgrade():
    op.add_column('users', sa.Column('middle_name', sa.String(100), nullable=True))

# Adding non-nullable column (requires default or backfill)
def upgrade():
    # Step 1: Add as nullable
    op.add_column('users', sa.Column('status', sa.String(20), nullable=True))

    # Step 2: Backfill existing rows
    op.execute("UPDATE users SET status = 'active' WHERE status IS NULL")

    # Step 3: Make non-nullable
    op.alter_column('users', 'status', nullable=False)

# Renaming column
def upgrade():
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('name', new_column_name='full_name')
```

### Dangerous Operations (Require Care)

| Operation | Risk | Safe Approach |
|-----------|------|---------------|
| Drop column | Data loss | Backup first, deploy in off-hours |
| Drop table | Data loss | Rename to `_deprecated_` first, drop later |
| Change column type | Data corruption | Create new column, migrate data, drop old |
| Add NOT NULL | Fails if nulls exist | Backfill first, then add constraint |
| Add unique constraint | Fails if duplicates | Clean duplicates first |

### Testing Migrations

```python
def test_migration_upgrade_downgrade(alembic_runner):
    """Ensure migrations can go up and down cleanly."""
    # Start fresh
    alembic_runner.migrate_down_to("base")

    # Upgrade to head
    alembic_runner.migrate_up_to("head")

    # Downgrade all the way
    alembic_runner.migrate_down_to("base")

    # Upgrade again (catches issues with downgrade)
    alembic_runner.migrate_up_to("head")

def test_migration_data_integrity(db, alembic_runner):
    """Test that migrations preserve existing data."""
    # Create test data at old schema
    alembic_runner.migrate_up_to("previous_revision")
    create_test_data(db)

    # Upgrade
    alembic_runner.migrate_up_to("head")

    # Verify data still accessible
    assert get_test_data(db) is not None
```

### Migration Pre-Deploy Checklist

- [ ] `alembic upgrade head` succeeds locally
- [ ] `alembic downgrade -1` succeeds locally
- [ ] No data loss in downgrade (or documented as breaking)
- [ ] Large tables: migration runs in < 30 seconds
- [ ] Indexes created CONCURRENTLY for large tables (Postgres)
- [ ] Foreign keys have appropriate ON DELETE behavior

---

## Dependency Version Coupling

When pinning a package version, check whether it has transitive version constraints that affect other packages. Async wrappers (`aioboto3`, `aiobotocore`) commonly constrain the sync library version (`boto3`, `botocore`).

```python
# BAD - upgrade boto3 independently, breaks aiobotocore
boto3==1.42.59
aioboto3==12.3.0  # requires botocore<1.34.35

# GOOD - pin boto3 within aiobotocore's constraint
boto3==1.34.34  # aioboto3 -> aiobotocore -> botocore<1.34.35
aioboto3==12.3.0
```

**Check:** `pip install --dry-run` or read the chain of `install_requires` constraints before upgrading.

**Learned from:** `requirements.txt` — `boto3==1.42.59` broke install because `aiobotocore==2.11.2` requires `botocore<1.34.35`.

---

## Feature Flag Pattern

Database-backed feature flags with multiple targeting strategies:

```python
class FlagType(str, enum.Enum):
    BOOLEAN = "boolean"        # Simple on/off
    PERCENTAGE = "percentage"  # Hash-based rollout
    USER_LIST = "user_list"    # Explicit user IDs

# Deterministic percentage bucketing (same user always gets same result)
def _percent_enabled(user_id: str, flag_name: str, percent: int) -> bool:
    token = f"{user_id}:{flag_name}".encode("utf-8")
    bucket = int(hashlib.sha256(token).hexdigest()[:8], 16) % 100
    return bucket < percent
```

**Key points:**
- Use SHA-256 hash of `user_id + flag_name` for even distribution
- Store `allowed_user_ids` as JSON array for USER_LIST type
- Default `enabled=False` for new flags (safety)
- Batch-load flags to avoid N+1 queries in `get_all_flags_for_user`

---

## Defensive Numeric Boundaries

When computing ratios, rates, or normalized scores from user-supplied or event data, always clamp to the valid range with `min()`/`max()`:

```python
# WRONG - can exceed 1.0 when numerator > denominator
rate = fixed_count / total_count

# CORRECT - clamped to valid range
rate = min(fixed_count / total_count, 1.0)
signal = max(0.0, min((found - false_pos) / found, 1.0))
```

Unclamped ratios that exceed their logical bounds corrupt any downstream ranking or comparison that depends on them. The bug produces plausible-looking results until the corruption is large enough to notice.

---

## Type-Dispatch Over Hardcoded Keys

When generalizing a function from one entity type to N types with different schemas, replace every hardcoded field reference with a dispatch map:

```python
# WRONG - hardcoded key from original type, crashes for new types
def avg_score(v):
    return v["metrics"]["f1_sum"] / v["metrics"]["sessions"]

# CORRECT - dispatch map for per-type primary metric
_PRIMARY_METRIC = {
    "explorer": "f1_sum",
    "architect": "score_sum",
    "reviewer": "score_sum",
}

def avg_score(v, agent_type):
    key = _PRIMARY_METRIC.get(agent_type, "f1_sum")
    s = v["metrics"]["sessions"]
    return v["metrics"].get(key, 0) / s if s > 0 else 0.0
```

Grep for all field-name literals from the original type when generalizing — they are all candidates for breakage. The bug is delayed: it only surfaces when the new types accumulate enough data to trigger the code path that references the old key.
