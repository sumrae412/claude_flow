# Performance Patterns

## Performance Targets

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| API response | < 100ms | 100-200ms | > 200ms |
| DB query (simple) | < 50ms | 50-100ms | > 100ms |
| DB query (complex) | < 200ms | 200-500ms | > 500ms |
| Page load | < 1s | 1-2s | > 2s |
| External API call | < 500ms | 500ms-1s | > 1s |

---

## N+1 Query Prevention

The most common performance killer. Use `GROUP BY` + `CASE` instead of loops:

```python
# BAD - N+1 queries (one query per user)
async def get_stats_slow(db, user_ids):
    stats = {}
    for user_id in user_ids:
        count = await db.execute(
            select(func.count(Task.id)).where(Task.user_id == user_id)
        )
        stats[user_id] = count.scalar()
    return stats

# GOOD - Single query with GROUP BY
async def get_stats_fast(db, user_ids):
    result = await db.execute(
        select(
            Task.user_id,
            func.count(Task.id).label("total"),
            func.sum(case((Task.status == "completed", 1), else_=0)).label("completed")
        )
        .where(Task.user_id.in_(user_ids))
        .group_by(Task.user_id)
    )
    return {row.user_id: {"total": row.total, "completed": row.completed}
            for row in result}
```

### Use selectinload for Relationships

```python
# BAD - Lazy loading causes N+1
users = await db.execute(select(User))
for user in users:
    print(user.tasks)  # Each access triggers a query!

# GOOD - Eager loading
users = await db.execute(
    select(User).options(selectinload(User.tasks))
)
for user in users:
    print(user.tasks)  # Already loaded
```

---

## Caching Patterns

### Redis Caching with TTL

```python
import json
from typing import Optional, TypeVar, Callable
from functools import wraps

T = TypeVar('T')

class CacheService:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_or_set(
        self,
        key: str,
        fetch_fn: Callable[[], T],
        ttl_seconds: int = 300
    ) -> T:
        """Get from cache or fetch and cache."""
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)

        value = await fetch_fn()
        await self.redis.setex(key, ttl_seconds, json.dumps(value))
        return value

    async def invalidate(self, pattern: str):
        """Invalidate cache keys matching pattern."""
        keys = await self.redis.keys(pattern)
        if keys:
            await self.redis.delete(*keys)

# Usage
stats = await cache.get_or_set(
    f"user:{user_id}:stats",
    lambda: calculate_user_stats(db, user_id),
    ttl_seconds=300
)
```

### Cache Stampede Protection

Prevent multiple requests from simultaneously rebuilding cache:

```python
import asyncio

class StampedeProtectedCache:
    def __init__(self, redis_client):
        self.redis = redis_client
        self._locks = {}

    async def get_or_set_protected(
        self,
        key: str,
        fetch_fn: Callable,
        ttl_seconds: int = 300
    ):
        # Try cache first
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)

        # Acquire distributed lock
        lock_key = f"lock:{key}"
        acquired = await self.redis.set(lock_key, "1", nx=True, ex=30)

        if not acquired:
            # Another process is rebuilding, wait and retry
            await asyncio.sleep(0.1)
            return await self.get_or_set_protected(key, fetch_fn, ttl_seconds)

        try:
            value = await fetch_fn()
            await self.redis.setex(key, ttl_seconds, json.dumps(value))
            return value
        finally:
            await self.redis.delete(lock_key)
```

---

## Circuit Breaker Pattern

Prevent cascading failures from external service outages:

```python
import time
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_max_calls: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_max_calls = half_open_max_calls

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
            else:
                raise CircuitOpenError("Circuit breaker is open")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.half_open_calls += 1
            if self.half_open_calls >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN

# Usage
email_circuit = CircuitBreaker(failure_threshold=5, timeout_seconds=60)

async def send_email(to, subject, body):
    return await email_circuit.call(email_service.send, to, subject, body)
```

---

## Rate Limiting Guidelines

| Endpoint Type | Limit | Examples |
|--------------|-------|----------|
| Read (list/get) | 100/min | GET /clients, GET /tasks |
| Write (create/update) | 30/min | POST /clients, PUT /tasks |
| Delete | 10-20/min | DELETE /clients |
| Heavy operations | 5-10/min | Bulk imports, reports |
| External API calls | 10/min | Google, CRM sync |

```python
from fastapi import Request, HTTPException
from collections import defaultdict
import time

class RateLimiter:
    def __init__(self):
        self.requests = defaultdict(list)

    def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int = 60
    ) -> bool:
        now = time.time()
        window_start = now - window_seconds

        # Clean old requests
        self.requests[key] = [
            t for t in self.requests[key] if t > window_start
        ]

        if len(self.requests[key]) >= limit:
            return False

        self.requests[key].append(now)
        return True

rate_limiter = RateLimiter()

async def rate_limit_dependency(request: Request):
    user_id = request.state.user.id
    if not rate_limiter.check_rate_limit(f"user:{user_id}", limit=100):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
```

---

## Connection Pooling

### HTTP Client Pooling

```python
import httpx

class ExternalAPIClient:
    _client: httpx.AsyncClient = None

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        if cls._client is None:
            cls._client = httpx.AsyncClient(
                limits=httpx.Limits(
                    max_connections=100,
                    max_keepalive_connections=20
                ),
                timeout=httpx.Timeout(30.0),
                http2=True  # Enable HTTP/2 multiplexing
            )
        return cls._client

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.aclose()
            cls._client = None

# Usage
client = await ExternalAPIClient.get_client()
response = await client.get("https://api.example.com/data")
```

### Database Connection Pooling

```python
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,          # Maintained connections
    max_overflow=20,       # Extra connections when needed
    pool_timeout=30,       # Wait time for connection
    pool_pre_ping=True,    # Check connection health
    pool_recycle=3600,     # Recycle connections hourly
)
```

---

## Batch Processing

For bulk operations, process in batches:

```python
async def import_records(db: AsyncSession, records: List[dict]):
    BATCH_SIZE = 100

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]

        for record_data in batch:
            db.add(Record(**record_data))

        await db.commit()

        # Optional: yield progress
        yield {"processed": min(i + BATCH_SIZE, len(records)), "total": len(records)}
```

---

## Database Optimization

### Partial Indexes

Index only the data you query most:

```python
# Only index active records
Index("ix_tasks_active_user", Task.user_id,
      postgresql_where=(Task.status == "active"))

# Only index recent records
Index("ix_logs_recent", Log.created_at,
      postgresql_where=(Log.created_at > func.now() - text("interval '30 days'")))
```

### Row-Level Locking

Prevent race conditions on critical updates:

```python
async def update_balance(db: AsyncSession, account_id: UUID, amount: Decimal):
    # Lock the row for update
    result = await db.execute(
        select(Account)
        .where(Account.id == account_id)
        .with_for_update()
    )
    account = result.scalar_one()

    account.balance += amount
    await db.commit()
```

---

## Parallel Execution

Use `asyncio.gather` for independent operations:

```python
async def load_dashboard(user_id: UUID) -> DashboardData:
    # Run all queries in parallel
    stats, notifications, recent_activity, preferences = await asyncio.gather(
        get_user_stats(user_id),
        get_notifications(user_id),
        get_recent_activity(user_id),
        get_user_preferences(user_id),
    )

    return DashboardData(
        stats=stats,
        notifications=notifications,
        recent_activity=recent_activity,
        preferences=preferences,
    )
    # 4 queries in ~max(query_times) instead of sum(query_times)
```
