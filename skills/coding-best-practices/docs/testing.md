# Testing Guidelines

## Test Type Matrix

| Test Type | Required | When to Write |
|-----------|----------|---------------|
| Unit tests | Always | Service functions, utilities, helpers |
| Constraint tests | If DB constraints | Unique constraints, foreign keys |
| Enum round-trip | If using enums | Store `enum.value`, not `enum.name` |
| Migration tests | If DB changes | Test upgrade AND downgrade |
| API endpoint tests | Always | CRUD operations, auth flows |
| Edge case tests | Always | Nulls, empties, boundaries |
| Integration tests | For critical paths | Multi-service workflows |

---

## Required Tests by Change Type

### Database Changes

```python
# 1. Test SQLAlchemy mapper configuration
def test_sqlalchemy_mapper_configuration():
    from sqlalchemy.orm import configure_mappers
    configure_mappers()  # Catches AmbiguousForeignKeysError!

# 2. Test unique constraints
async def test_duplicate_email_rejected(db):
    await create_user(db, email="test@example.com")
    with pytest.raises(IntegrityError):
        await create_user(db, email="test@example.com")

# 3. Test enum persistence
async def test_status_enum_roundtrip(db):
    record = await create_record(db, status=Status.ACTIVE)
    await db.refresh(record)
    assert record.status == Status.ACTIVE
    assert record.status.value == "active"  # Not "ACTIVE"

# 4. Test migrations
def test_migration_upgrade_downgrade(alembic_runner):
    alembic_runner.migrate_up_to("head")
    alembic_runner.migrate_down_to("base")
    alembic_runner.migrate_up_to("head")
```

### API Endpoints

```python
# Test all CRUD operations
async def test_create_resource(client, auth_headers):
    response = await client.post(
        "/api/resources",
        json={"name": "Test"},
        headers=auth_headers
    )
    assert response.status_code == 201
    assert response.json()["name"] == "Test"

async def test_create_resource_unauthorized(client):
    response = await client.post("/api/resources", json={"name": "Test"})
    assert response.status_code == 401

async def test_get_resource_not_found(client, auth_headers):
    response = await client.get(
        f"/api/resources/{uuid4()}",
        headers=auth_headers
    )
    assert response.status_code == 404
```

### Service Layer

```python
async def test_service_function(db):
    # Arrange
    user = await create_test_user(db)

    # Act
    result = await service.process_data(db, user.id, input_data)

    # Assert
    assert result.status == "completed"
    assert result.user_id == user.id
```

---

## Test Factories

Use factories to create test data consistently:

```python
# tests/utils/factories.py
class UserFactory:
    @staticmethod
    async def create(db: AsyncSession, **overrides) -> User:
        defaults = {
            "email": f"test-{uuid4()}@example.com",
            "name": "Test User",
            "is_active": True,
        }
        user = User(**{**defaults, **overrides})
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

class ResourceFactory:
    @staticmethod
    async def create(db: AsyncSession, user_id: UUID, **overrides) -> Resource:
        defaults = {
            "user_id": user_id,
            "name": f"Resource {uuid4().hex[:8]}",
            "status": "active",
        }
        resource = Resource(**{**defaults, **overrides})
        db.add(resource)
        await db.commit()
        await db.refresh(resource)
        return resource

# Usage in tests
async def test_something(db):
    user = await UserFactory.create(db)
    resource = await ResourceFactory.create(db, user.id, name="Custom Name")
```

---

## Async Testing Setup

```ini
# pytest.ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_functions = test_*
```

```python
# conftest.py
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

@pytest.fixture
async def db():
    """Provide a clean database session for each test."""
    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        yield session
        await session.rollback()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

@pytest.fixture
async def client(db):
    """Provide a test client with database override."""
    app.dependency_overrides[get_db] = lambda: db
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
```

---

## Mocking Async Services

```python
from unittest.mock import AsyncMock, patch

async def test_with_mocked_service():
    mock_service = AsyncMock()
    mock_service.fetch_data.return_value = {"key": "value"}

    with patch("app.services.external_service", mock_service):
        result = await function_under_test()

    mock_service.fetch_data.assert_called_once_with(expected_args)
    assert result == expected_result

# Mock specific method
async def test_partial_mock(db):
    with patch.object(UserService, "send_email", new_callable=AsyncMock) as mock_email:
        mock_email.return_value = True
        await UserService.create_user(db, user_data)
        mock_email.assert_called_once()
```

### Mock Settings Alongside API Clients

When testing services that create API clients from settings (OpenAI, Twilio, etc.),
mock both the client class AND the settings object. If settings aren't mocked, the
real `settings.api_key` is `None` and the client constructor may fail before your
mock takes effect.

```python
# BAD — only mocks the client class, settings.api_key is None
with patch("app.services.ai.llm_fallback.AsyncOpenAI") as mock_cls:
    mock_cls.return_value = mock_client
    result = await get_completion("prompt")  # may fail on settings

# GOOD — mock settings AND client class together
with (
    patch("app.services.ai.llm_fallback.settings") as mock_settings,
    patch("app.services.ai.llm_fallback.AsyncOpenAI") as mock_cls,
):
    mock_settings.openai_api_key = "test-key"
    mock_settings.openai_model = "gpt-4o-mini"
    mock_cls.return_value = mock_client
    result = await get_completion("prompt")  # works
```

**Learned from:** `test_llm_fallback.py` — test only mocked `AsyncOpenAI` but not
`settings`. The real settings had `openai_api_key = None`, causing test failure.

---

## Edge Cases to Always Test

### Enum and allowlist tests use production sources

- **Enum validator tests:** Use the enum value actually used in production for the test (e.g. `ClientType.RENTER` for "renter"), not a different enum (e.g. `ACTIVE` for "active") so the test validates the real conversion.
- **Allowlist/filter tests:** Import and assert against the same constant the route/service uses (e.g. `_VALID_STATUS_FILTERS` from `app.routes.tenants`) so the test cannot drift from the implementation.
- **Exception-path tests:** When testing a fallback triggered by an exception, raise the same exception type the code catches (e.g. `SQLAlchemyError`), not a generic `Exception`, so the catch block is actually exercised.

**Learned from:** `test_tenants_standalone.py` — ClientType test used "active" → ACTIVE; status filter tests used a local set instead of `_VALID_STATUS_FILTERS`; fallback test raised generic Exception so the SQLAlchemyError catch was not hit.

```python
# Null/None handling
async def test_handles_none_input(db):
    result = await service.process(db, None)
    assert result is None  # or appropriate default

# Empty collections
async def test_handles_empty_list(db):
    result = await service.process_items(db, [])
    assert result == []

# Boundary values
async def test_pagination_boundary(db):
    # First page
    result = await service.list_items(db, page=1, limit=10)
    assert len(result) <= 10

    # Zero/negative page
    with pytest.raises(ValueError):
        await service.list_items(db, page=0, limit=10)

# Unicode and special characters
async def test_unicode_in_name(db):
    user = await UserFactory.create(db, name="José García 日本語")
    assert user.name == "José García 日本語"

# Concurrent access
async def test_concurrent_updates(db):
    resource = await ResourceFactory.create(db)

    async def update_resource():
        await service.increment_counter(db, resource.id)

    await asyncio.gather(*[update_resource() for _ in range(10)])

    await db.refresh(resource)
    assert resource.counter == 10
```

---

## Golden Path Tests

For critical workflows, maintain "golden path" tests that must always pass:

```python
class TestGoldenPaths:
    """Critical workflows that must never break."""

    async def test_user_registration_flow(self, client, db):
        """Complete user registration -> login -> profile access."""
        # Register
        response = await client.post("/auth/register", json=user_data)
        assert response.status_code == 201

        # Login
        response = await client.post("/auth/login", json=login_data)
        assert response.status_code == 200
        token = response.json()["access_token"]

        # Access profile
        response = await client.get(
            "/users/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        assert response.json()["email"] == user_data["email"]

    async def test_resource_crud_flow(self, client, auth_headers, db):
        """Complete CRUD cycle for a resource."""
        # Create
        response = await client.post("/resources", json=data, headers=auth_headers)
        resource_id = response.json()["id"]

        # Read
        response = await client.get(f"/resources/{resource_id}", headers=auth_headers)
        assert response.status_code == 200

        # Update
        response = await client.put(
            f"/resources/{resource_id}",
            json=updated_data,
            headers=auth_headers
        )
        assert response.status_code == 200

        # Delete
        response = await client.delete(f"/resources/{resource_id}", headers=auth_headers)
        assert response.status_code == 204

        # Verify deleted
        response = await client.get(f"/resources/{resource_id}", headers=auth_headers)
        assert response.status_code == 404
```
