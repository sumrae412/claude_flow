# Defensive Backend Flows — Evidence Log

> To add a new bug, copy the template below and fill it in.
> Then run the update-skill workflow to test and update the skill.

## Quick-Add Template

<!-- Copy everything between the dashes, paste at the end of the Bugs section, and fill in -->
<!--
---

## Bug N: SHORT_NAME (DATE)

**Symptom:** What was observed or what would happen in production.

**Root cause:** What actually went wrong in the code.

**Which rule violated:** [1: Silent Swallow | 2: Catch What You Raise | 3: Copy Before Delete | 4: One Source of Truth | 5: Respect Encapsulation | NEW]

**Code (bad):**
```python
# the broken pattern
```

**Code (fix):**
```python
# the corrected pattern
```

**Pressure scenario prompt:** A generic task prompt that would reproduce this bug.
-->

---

## Bug 1: Migration NULLs Before Copy (2026-03-03)

**Symptom:** Deploying the migration would permanently delete all user OAuth tokens with no way to recover.

**Root cause:** Alembic migration NULLed `users.google_calendar_refresh_token` without first INSERTing/UPDATEing into `integration_connections`. The `downgrade()` was a bare `pass`.

**Which rule violated:** 3: Copy Before Delete

**Code (bad):**
```python
def upgrade() -> None:
    op.execute(text("""
        UPDATE users SET
            google_calendar_token = NULL,
            google_calendar_refresh_token = NULL ...
    """))

def downgrade() -> None:
    pass
```

**Code (fix):**
```python
def upgrade() -> None:
    # Step 1: INSERT new integration_connections rows
    op.execute(text("""
        INSERT INTO integration_connections (...)
        SELECT ... FROM users WHERE refresh_token IS NOT NULL
    """))
    # Step 2: UPDATE existing rows with token data
    op.execute(text("""UPDATE integration_connections ic SET ... FROM users u ..."""))
    # Step 3: NOW safe to NULL
    op.execute(text("""UPDATE users SET google_calendar_token = NULL ..."""))

def downgrade() -> None:
    op.execute(text("""
        UPDATE users u SET refresh_token = ic.refresh_token_encrypted
        FROM integration_connections ic WHERE ...
    """))
```

**Pressure scenario prompt:** "Write an Alembic migration that moves user email preferences from a `users` column into a new `user_preferences` table, then removes the column from `users`."

---

## Bug 2: db.commit() in Services (2026-03-03)

**Symptom:** Partial commits when a multi-step service operation fails halfway. Route-level transaction boundary violated.

**Root cause:** `token_refresh_service.py` and `email.py` called `db.commit()` directly (5+ occurrences) instead of letting routes own transactions.

**Which rule violated:** Project-specific (CourierFlow Boundaries #7). Not in generic skill.

**Pressure scenario prompt:** N/A — project-specific, covered by CLAUDE.md.

---

## Bug 3: Private Method Called Externally (2026-03-03)

**Symptom:** Double `record_error` on permanent token failure — the error count incremented twice per failure.

**Root cause:** `token_refresh_service` called `token_manager._refresh_token()` directly instead of a public API. `_refresh_token` internally calls `record_error`, and the caller also called it, doubling the side effect.

**Which rule violated:** 5: Respect Encapsulation

**Code (bad):**
```python
# token_refresh_service.py
await token_manager._refresh_token(db, connection)
connection.record_success()
connection.status = IntegrationConnectionStatus.CONNECTED
```

**Code (fix):**
```python
# token_manager.py — new public method
async def refresh_connection(self, db, connection):
    try:
        await self._refresh_token(db, connection)
        return True, None
    except TokenExpiredError as exc:
        return False, str(exc)

# token_refresh_service.py — uses public API
success, error = await token_manager.refresh_connection(db, connection)
```

**Pressure scenario prompt:** "Write a service function `refresh_user_session()` that refreshes an OAuth token using an existing `TokenStore` class. The `TokenStore` has a `_do_refresh(conn)` method that handles the HTTP call and updates internal state."

---

## Bug 4: Duplicate Column Definitions (2026-03-03)

**Symptom:** SQLAlchemy model had 3 columns defined twice. Confusing for readers, risk of inconsistent defaults.

**Root cause:** Copy-paste error in `IntegrationConnection` model — `daily_quota_used`, `daily_quota_limit`, `quota_reset_at` appeared in two separate blocks.

**Which rule violated:** 4: One Source of Truth

**Pressure scenario prompt:** N/A — copy-paste error, not reproducible by prompt.

---

## Bug 5: Cache Eviction in Wrong Function (2026-03-03)

**Symptom:** Cache eviction (a write-side concern) ran on every status check (a read-side operation), adding unnecessary overhead and mixing concerns.

**Root cause:** Cache eviction logic was placed in `_google_connected()` (read-only check) instead of `_set_cached_events()` (write operation).

**Which rule violated:** Project-specific (misplaced side effect). Not in generic skill.

---

## Bug 6: QuotaExceededError Not Caught (2026-03-03)

**Symptom:** When Gmail quota was exceeded, `send_email()` raised an unhandled `QuotaExceededError` instead of falling back to SMTP.

**Root cause:** `send_simple_email()` caught `TokenNotFoundError` and `TokenExpiredError` for SMTP fallback but missed `QuotaExceededError`, which `check_gmail_quota()` also raises.

**Which rule violated:** 2: Catch What You Raise

**Code (bad):**
```python
try:
    await token_manager.check_gmail_quota(db, user.id)
except (TokenNotFoundError, TokenExpiredError):
    return await self._send_via_smtp(...)
# QuotaExceededError crashes here
```

**Code (fix):**
```python
try:
    await token_manager.check_gmail_quota(db, user.id)
except (TokenNotFoundError, TokenExpiredError, QuotaExceededError):
    return await self._send_via_smtp(...)
```

**Pressure scenario prompt:** "Write a `send_notification()` function that tries to send via a premium API first. If the API raises `RateLimitError`, `AuthError`, or `QuotaError`, fall back to a basic SMTP sender."

---

## Bug 7: Double record_error (2026-03-03)

**Symptom:** Connection error counter incremented twice per failure, triggering circuit breaker prematurely.

**Root cause:** `_refresh_token` internally calls `record_error` on failure. The caller (`token_refresh_service`) also called `connection.record_error()` in its own `except` block.

**Which rule violated:** 5: Respect Encapsulation (same root cause as Bug 3)

---

## Bug 8: ScopeMismatchError Silently Swallowed (2026-03-03)

**Symptom:** Users logged in without required Drive scopes. No log entry, no status update, no way to diagnose.

**Root cause:** `except ScopeMismatchError: pass` in the Google OAuth callback route.

**Which rule violated:** 1: No Silent Swallows

**Code (bad):**
```python
except ScopeMismatchError:
    pass
```

**Code (fix):**
```python
except ScopeMismatchError as scope_err:
    logger.warning(
        "Google login missing scopes for user %s: %s",
        user.id, scope_err,
    )
    user.gmail_auth_status = "scope_error"
    await db.commit()
```

**Pressure scenario prompt:** "Write an OAuth callback handler that stores the access token and checks if the granted scopes include 'drive.file'. Handle the case where scopes are missing."

---

## Bug 9: Missing Public API (2026-03-03)

**Symptom:** External service had to call `_private` method because no public alternative existed.

**Root cause:** `TokenManager` only had `_refresh_token()` (private). `token_refresh_service` needed to refresh tokens but had no public entry point.

**Which rule violated:** 5: Respect Encapsulation (same family as Bug 3 and 7)

---

## Bug 10: Conflicting Quota Limits (2026-03-03)

**Symptom:** Email service allowed 2000 emails/day while token manager enforced 500. Inconsistent behavior depending on which check ran first.

**Root cause:** `email.py` defined `'per_user_daily': 2000` while `token_manager.py` defined `daily_quota_limit = 500`.

**Which rule violated:** 4: One Source of Truth

**Code (bad):**
```python
# email.py
GMAIL_RATE_LIMITS = {'per_user_daily': 2000}
# token_manager.py
daily_quota_limit = Column(Integer, default=500)
```

**Code (fix):**
```python
# email.py — defer to token_manager as source of truth
GMAIL_RATE_LIMITS = {'per_user_daily': 500}  # token_manager is source of truth
```

**Pressure scenario prompt:** "Write two service modules that both enforce a rate limit. Module A sends messages, Module B tracks quotas. Both need to know the daily limit."

---

## Bug 11: Missing Import for Return Type (2026-03-04)

**Symptom:** `NameError: name 'TenantPanelResponse' is not defined` when `get_tenant_panel_data()` was called at runtime. Module imported fine, function crashed on first invocation.

**Root cause:** `TenantPanelResponse` was used in the method's return type annotation (`-> Optional[TenantPanelResponse]`) but was never imported. Python evaluates type annotations lazily in some contexts, so the import error only surfaces at call time.

**Which rule violated:** NEW — Rule 6: Verify Imports Match Signatures

**Code (bad):**
```python
from app.schemas.tenant_panel import TenantPanelDocument, TenantPanelTenant

async def get_tenant_panel_data(...) -> Optional[TenantPanelResponse]:
    # NameError at runtime
```

**Code (fix):**
```python
from app.schemas.tenant_panel import (
    TenantPanelDocument,
    TenantPanelResponse,
    TenantPanelTenant,
)
```

**Pressure scenario prompt:** "Write a service method `get_dashboard_summary()` that returns a `DashboardResponse` Pydantic model. The model is defined in `app/schemas/dashboard.py` alongside `DashboardCard` and `DashboardAlert`."

---

## Bug 12: DISTINCT + JSON Breaks on Postgres (2026-03-04)

**Symptom:** Document query crashed on PostgreSQL with errors about JSON equality in DISTINCT and ORDER BY columns not matching SELECT DISTINCT list.

**Root cause:** Query used `select(Document).distinct().order_by(Document.created_at.desc())`. The Document model has JSON columns, and Postgres cannot compare JSON for equality (needed by DISTINCT). Additionally, ORDER BY on a column not in SELECT DISTINCT is invalid in Postgres.

**Which rule violated:** NEW — Rule 7: Test Queries Against Real DB Semantics

**Code (bad):**
```python
query = (
    select(Document)
    .join(DocumentSigner)
    .distinct()
    .order_by(Document.created_at.desc())
    .limit(5)
)
```

**Code (fix):**
```python
# Step 1: Get IDs via subquery (no JSON columns)
id_query = (
    select(Document.id, func.max(Document.created_at).label("ts"))
    .outerjoin(DocumentSigner)
    .where(...)
    .group_by(Document.id)
    .order_by(func.max(Document.created_at).desc())
    .limit(5)
)
doc_ids = [row[0] for row in (await db.execute(id_query)).all()]

# Step 2: Fetch full rows with CASE ordering
if doc_ids:
    order = case({did: i for i, did in enumerate(doc_ids)}, value=Document.id)
    docs = await db.execute(
        select(Document).where(Document.id.in_(doc_ids)).order_by(order)
    )
```

**Pressure scenario prompt:** "Write a query that fetches the 5 most recent documents for a user, deduplicating by document ID when the same document appears via multiple signers. The Document model has a JSON `metadata` column."

---

## Bug 13: AttributeError on Non-Existent Model Attribute (2026-03-04)

**Symptom:** `AttributeError: 'Document' object has no attribute 'signed_at'` at runtime when building the tenant panel document list.

**Root cause:** Status date calculation referenced `document.signed_at`, but the `Document` model has no `signed_at` column. The correct fallback chain is `completed_at → sent_at → viewed_at → created_at`.

**Which rule violated:** NEW — Rule 8: Verify Model Attributes Before Access

**Code (bad):**
```python
status_date = document.signed_at or document.created_at
```

**Code (fix):**
```python
status_date = (
    document.completed_at
    or document.sent_at
    or document.viewed_at
    or document.created_at
)
```

**Pressure scenario prompt:** "Write a function that builds a summary card for each document, showing the most recent status change date. Use `signed_at` for completed documents and `created_at` as fallback."

---

## Bug 14: AsyncSession + Google Connection NameError (2026-03-04)

**Symptom:** `NameError` for `AsyncSession` in `calendar.py` type hints; also `_google_connected()` returned `True` for expired/disconnected tokens because it only checked if a connection row existed.

**Root cause:** Two issues in one: (1) `AsyncSession` used in function signature before import, (2) connection check used row existence instead of `status.is_connected` which accounts for token expiry.

**Which rule violated:** 6: Verify Imports Match Signatures

**Code (bad):**
```python
# No import for AsyncSession at top of file
async def _google_connected(db: AsyncSession, user_id: UUID) -> bool:
    conn = await token_manager.get_connection(db, user_id)
    return conn is not None  # True even if token expired!
```

**Code (fix):**
```python
from sqlalchemy.ext.asyncio import AsyncSession

async def _google_connected(db: AsyncSession, user_id: UUID) -> bool:
    status = await token_manager.get_connection_status(db, user_id)
    return status.is_connected  # Checks actual token validity
```

**Pressure scenario prompt:** "Write a helper function `is_google_connected(db, user_id)` that checks if a user has a valid Google connection. Use the `AsyncSession` type hint."

---

## Bug 15: Late Import NameError in Email Retry (2026-03-04)

**Symptom:** `NameError: name 'token_manager' is not defined` in `_send_email_with_retry` — the singleton was referenced before its late import.

**Root cause:** `token_manager` was used in the function body before the `from app.services.token_manager import token_manager` line that appeared later in the function.

**Which rule violated:** 6: Verify Imports Match Signatures (late-import variant)

**Code (bad):**
```python
async def _send_email_with_retry(self, ...):
    conn = await token_manager.get_connection(...)  # NameError
    # ... later in the function ...
    from app.services.token_manager import token_manager
```

**Code (fix):**
```python
async def _send_email_with_retry(self, ...):
    from app.services.token_manager import (
        TokenExpiredError, TokenNotFoundError, token_manager,
    )
    conn = await token_manager.get_connection(...)
```

**Pressure scenario prompt:** "Write an email send function with retry logic that uses a `token_manager` singleton to check Gmail quota before sending."

---

## Bug 16: Incomplete Permanent Error Codes (2026-03-04)

**Symptom:** OAuth refresh with `invalid_client` or `unauthorized_client` errors retried forever instead of being treated as permanent failures. The token was never marked as failed.

**Root cause:** `PERMANENT_ERRORS` set only contained `"invalid_grant"`. The `invalid_client` and `unauthorized_client` error codes — which also indicate unrecoverable token issues — were missing.

**Which rule violated:** 2: Catch What You Raise (error-code set variant)

**Code (bad):**
```python
PERMANENT_ERRORS = {"invalid_grant"}
# invalid_client → retried 5 times, then generic failure
# unauthorized_client → retried 5 times, then generic failure
```

**Code (fix):**
```python
PERMANENT_ERRORS = {"invalid_grant", "invalid_client", "unauthorized_client"}
```

**Pressure scenario prompt:** "Write an OAuth token refresh function that handles permanent errors differently from transient errors. Use Google's OAuth error codes."

---

## Bug 17: SMS Failure Aborts Disconnect Flow (2026-03-04)

**Symptom:** When SMS notification failed during Google disconnect, the entire disconnect operation was rolled back. User remained "connected" in a broken state.

**Root cause:** `_send_disconnect_sms()` was called without a try-catch wrapper in the disconnect flow. Any SMS failure (Twilio down, no phone number, rate limit) propagated up and rolled back the DB transaction that had already marked the connection as disconnected.

**Which rule violated:** NEW — Rule 9: Auxiliary Side-Effects Must Not Abort Primary Flow

**Code (bad):**
```python
async def disconnect(self, db, user_id):
    conn.status = "disconnected"
    await db.flush()
    await self._create_alert(db, user_id)
    await self._send_disconnect_sms(db, user_id)  # failure = rollback
```

**Code (fix):**
```python
async def _send_disconnect_sms(self, db, user_id):
    try:
        # ... send SMS ...
    except Exception as exc:
        logger.warning("Disconnect SMS failed for %s: %s", user_id, exc)
```

**Pressure scenario prompt:** "Write a `disconnect_service()` function that revokes an OAuth token, creates an in-app alert, and sends an SMS notification to the user."

---

## Bug 18: pytest_plugins in Non-Root conftest (2026-03-04)

**Symptom:** pytest collection errors when `pytest_plugins` was defined in a subdirectory conftest. Recent pytest versions reject this.

**Root cause:** `pytest_plugins = ["tests.e2e.fixtures.conftest_mocks"]` was placed in `tests/e2e/conftest.py` instead of the root `conftest.py`. pytest requires plugin registration at the root level.

**Which rule violated:** 4: One Source of Truth (test plugin registration must be centralized)

**Code (bad):**
```python
# tests/e2e/conftest.py — WRONG location
pytest_plugins = ["tests.e2e.fixtures.conftest_mocks"]
```

**Code (fix):**
```python
# conftest.py (ROOT) — CORRECT location
"""Top-level pytest configuration.
pytest_plugins must be defined at the repository root."""
pytest_plugins = ["tests.e2e.fixtures.conftest_mocks"]
```

**Pressure scenario prompt:** "Set up a test fixture that's shared across multiple test subdirectories using pytest_plugins."

---

## Bug 19: 2FA Missing API Methods (2026-03-04)

**Symptom:** Tests failed with `AttributeError` — `TwoFAService` had no `generate_email_verification_code()` method, and `TwoFAEmailService` class didn't exist.

**Root cause:** Tests were written against an expected API contract, but the service implementation didn't expose the expected methods/classes. The service had internal equivalents but no matching public interface.

**Which rule violated:** 8: Verify Model Attributes Before Access (API contract variant — verify methods exist before testing them)

**Code (bad):**
```python
# twofa.py — missing method
class TwoFAService:
    def generate_verification_code(self) -> str: ...
    # No generate_email_verification_code()
# No TwoFAEmailService class at all
```

**Code (fix):**
```python
# twofa.py — complete API
class TwoFAService:
    def generate_verification_code(self) -> str: ...
    def generate_email_verification_code(self) -> str:
        return self.generate_verification_code()

class TwoFAEmailService:
    def generate_email_verification_code(self) -> str:
        return "".join(secrets.choice("0123456789") for _ in range(6))
```

**Pressure scenario prompt:** "Write unit tests for a 2FA email verification service. The service should generate 6-digit codes and verify them."

---

## Bug 20: Google OAuth Scope Mismatch (2026-03-04)

**Symptom:** Adding `drive.file` scope to `REQUIRED_GOOGLE_SCOPES` in `token_manager.py` didn't propagate to `calendar_service.py`, which had its own hardcoded scope list. Users got `ScopeMismatchError` on Drive operations.

**Root cause:** `calendar_service.py` hardcoded its own scope list instead of importing `REQUIRED_GOOGLE_SCOPES` from `token_manager.py`.

**Which rule violated:** 4: One Source of Truth

**Code (bad):**
```python
# calendar_service.py — hardcoded scopes
flow = Flow.from_client_config(
    config,
    scopes=["calendar", "gmail.send", "openid"],  # missing drive.file!
)
```

**Code (fix):**
```python
# calendar_service.py — imports canonical source
from app.services.token_manager import REQUIRED_GOOGLE_SCOPES
flow = Flow.from_client_config(
    config,
    scopes=sorted(REQUIRED_GOOGLE_SCOPES),
)
```

**Pressure scenario prompt:** "Add Google Drive file access scope to your OAuth flow. The app already uses Google Calendar and Gmail scopes."

---

## Bug 21: Onboarding Legacy Route Regressions (2026-03-04)

**Symptom:** After refactoring onboarding to step-based URLs (`/onboarding/step/2`), old URLs like `/onboarding/calendar` returned 404s. Bookmarked links and cached redirects broke.

**Root cause:** Route refactor replaced old URL patterns without backward-compatible redirects.

**Which rule violated:** Project-specific — backward compatibility for refactored routes.

**Code (bad):**
```python
# Old route removed entirely
# @router.get("/calendar") — GONE, returns 404
```

**Code (fix):**
```python
@router.get("/calendar", response_class=RedirectResponse)
async def onboarding_calendar(
    current_user: User = Depends(get_current_active_user),
):
    """Legacy redirect for calendar step."""
    return RedirectResponse(
        url="/onboarding/step/2", status_code=status.HTTP_302_FOUND
    )
```

**Pressure scenario prompt:** "Refactor the onboarding wizard from named routes (/onboarding/calendar, /onboarding/properties) to numbered steps (/onboarding/step/1, /onboarding/step/2)."

---

## Bug 22: Document Sends Not in Recent Activity (2026-03-04)

**Symptom:** Landlord sent documents to tenants but the home feed showed no record of it. No confirmation the action happened.

**Root cause:** The `send_document()` route completed the send but never created an `ActionLog` entry. The action was invisible on the dashboard.

**Which rule violated:** NEW — Rule 10: User-Facing Actions Must Create Audit Trails

**Code (bad):**
```python
async def send_document(db, document, tenant, user):
    await deliver(document, tenant)
    document.status = "sent"
    await db.flush()
    return {"success": True}  # No ActionLog!
```

**Code (fix):**
```python
async def send_document(db, document, tenant, user):
    await deliver(document, tenant)
    document.status = "sent"
    db.add(ActionLog(
        user_id=user.id,
        action_type=ActionLogType.DOCUMENT_SENT,
        title=f"Sent document to {tenant.full_name}",
        level=ActionLogLevel.INFO,
    ))
    await db.flush()
    return {"success": True}
```

**Pressure scenario prompt:** "Add a 'Send Document' feature that emails a PDF to a tenant. The landlord should see confirmation on their dashboard."

---

## Bug 23: Tenant Contact Updates Not in Recent Activity (2026-03-04)

**Symptom:** Tenant updated contact preferences via magic link, but landlord had no visibility — no dashboard entry, no notification.

**Root cause:** `process_contact_preferences()` updated the tenant record but created no `ActionLog` entry.

**Which rule violated:** 10: User-Facing Actions Must Create Audit Trails

**Code (bad):**
```python
async def process_contact_preferences(self, token, preferences):
    tenant.preferred_contact_channel = channel
    tenant.contact_preferences_updated_at = datetime.now(timezone.utc)
    return {"success": True}  # Landlord sees nothing
```

**Code (fix):**
```python
async def process_contact_preferences(self, token, preferences):
    tenant.preferred_contact_channel = channel
    tenant.contact_preferences_updated_at = datetime.now(timezone.utc)
    db.add(ActionLog(
        user_id=tenant.household.user_id,
        action_type=ActionLogType.TENANT_UPDATED,
        title=f"{tenant.full_name} updated contact preferences",
        level=ActionLogLevel.INFO,
    ))
    return {"success": True}
```

**Pressure scenario prompt:** "Build a tenant self-service page where tenants can update their contact preferences. The landlord should see these changes on their dashboard."

---

## Bug 24: Home Feed Excluding Error Logs (2026-03-04)

**Symptom:** Workflow execution failures (SMS not sent, email bounced) never appeared on the landlord's home feed. Critical errors were invisible.

**Root cause:** `get_recent_activity()` defaulted `include_errors=False`, and the dashboard caller used the default. ERROR-level logs were silently filtered out.

**Which rule violated:** NEW — Rule 11: Error-Level Logs Must Surface to Users

**Code (bad):**
```python
# logging_service.py
async def get_recent_activity(db, user_id, include_errors=False):
    if not include_errors:
        conditions.append(ActionLog.level != ActionLogLevel.ERROR)

# dashboard_service.py — uses default (errors hidden)
activity = await get_recent_activity(db, user_id)
```

**Code (fix):**
```python
# dashboard_service.py — explicitly includes errors
activity = await get_recent_activity(
    db, user_id, include_errors=True,
)
```

**Pressure scenario prompt:** "Build a dashboard home feed that shows the user's recent activity. Include a function parameter to filter by log level."

---

## Bug 25: Stale AI Endpoints in Email Composer (2026-03-04)

**Symptom:** Email compose template referenced `/ai/improve` and `/ai/generate` endpoints that didn't exist in the router, causing 404s when users tried AI features.

**Root cause:** Frontend JS hardcoded endpoint paths that were never created or were moved during refactoring. No integration test verified the endpoints existed.

**Which rule violated:** 4: One Source of Truth (frontend and backend endpoint paths must agree)

**Pressure scenario prompt:** "Add AI-powered writing assistance to an email compose page. Wire up 'Improve' and 'Generate' buttons to backend AI endpoints."

---

## Bug 26: Onboarding complete_step Missing Return (2026-03-04)

**Symptom:** After `await db.commit()`, the onboarding step-complete handler returned nothing. Frontend got no JSON (no `next_route`), so the "Continue" button couldn't redirect.

**Root cause:** Route handler had no `return` statement after the database commit. FastAPI returned `null` instead of the expected `{success, next_step, next_route}` response.

**Which rule violated:** Project-specific — every route handler must return an explicit response body.

**Code (bad):**
```python
@router.post("/complete_step")
async def complete_step(body: StepCompleteBody, db=Depends(get_db)):
    step.completed = True
    await db.commit()
    # No return — frontend gets null
```

**Code (fix):**
```python
@router.post("/complete_step")
async def complete_step(body: StepCompleteBody, db=Depends(get_db)):
    step.completed = True
    await db.commit()
    return {
        "success": True,
        "next_step": step.order + 1,
        "next_route": f"/onboarding/step/{step.order + 1}",
        "completed": True,
    }
```

**Pressure scenario prompt:** "Write an endpoint that marks a wizard step as complete and returns the next step URL for the frontend to navigate to."

---

## Bug 27: Inline ActionLog Imports in Route Functions (2026-03-04)

**Symptom:** Multiple functions in `documents.py` had identical `from app.models.action_log import ...` blocks scattered inside function bodies, violating conventions and risking NameError if an import was accidentally placed after first use.

**Root cause:** When ActionLog entries were added incrementally to different route handlers, each got its own inline import instead of a single top-level import.

**Which rule violated:** 6: Verify Imports Match Signatures (convention: imports belong at file top)

**Pressure scenario prompt:** "Add ActionLog entries to three different route handlers in an existing file. Each handler needs ActionLog, ActionLogLevel, and ActionLogType."

---

## Bug 28: Circuit Breaker Was a No-Op Stub (2026-03-04)

**Symptom:** OpenAI service kept hammering a down API. Circuit breaker existed in code but never tripped because `is_open()` always returned `False` and `record_failure()` was a no-op.

**Root cause:** Circuit breaker class was implemented as a skeleton with placeholder methods that did nothing. It passed code review because the interface *looked* correct.

**Which rule violated:** NEW pattern — no-op stubs give false confidence. A safety mechanism that doesn't work is worse than none (people rely on it).

**Code (bad):**
```python
class CircuitBreaker:
    def is_open(self) -> bool:
        return False  # Always allows requests!
    def record_failure(self) -> None:
        pass  # No-op!
```

**Code (fix):**
```python
class CircuitBreaker:
    def __init__(self, threshold=3, timeout=60):
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
        self.last_failure_time = None

    def can_proceed(self) -> bool:
        if self.state == CircuitBreakerState.OPEN:
            elapsed = (now() - self.last_failure_time).total_seconds()
            if elapsed < self.timeout:
                return False
            self.state = CircuitBreakerState.HALF_OPEN
        return True

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = now()
        if self.failure_count >= self.threshold:
            self.state = CircuitBreakerState.OPEN
```

**Pressure scenario prompt:** "Add a circuit breaker to an external API client that stops making requests after 3 consecutive failures."

---

## Bug 29: AI Audit Metadata Leaked PII (2026-03-04)

**Symptom:** AI audit logs stored raw metadata dictionaries containing email addresses, phone numbers, and API key fragments.

**Root cause:** `extra_data["metadata"] = metadata` persisted the raw dict without scrubbing. Metadata came from user prompts and API responses, which can contain PII.

**Which rule violated:** NEW — sensitive data must be scrubbed before audit persistence.

**Code (bad):**
```python
if metadata:
    extra_data["metadata"] = metadata  # Raw, unsanitized
```

**Code (fix):**
```python
SENSITIVE_KEYS = {"api_key", "token", "secret", "password"}

def _sanitize_metadata(value):
    if isinstance(value, dict):
        return {
            k: "[REDACTED]" if any(m in k.lower() for m in SENSITIVE_KEYS)
            else _sanitize_metadata(v)
            for k, v in value.items()
        }
    return value

extra_data["metadata"] = _sanitize_metadata(metadata)
```

**Pressure scenario prompt:** "Add audit logging to an AI endpoint that stores the request metadata (model, prompt length, user context) for debugging."

---

## Bug 30: OAuth Error Messages Leaked Internals (2026-03-04)

**Symptom:** OAuth callback failure redirected users to `/calendar?error=true&message=<raw exception string>` — exposing file paths, tracebacks, and internal error details in the URL bar.

**Root cause:** `quote_plus(str(e)[:200])` was used as the error message in the redirect URL. Also contained `print()` debug statements and `traceback.format_exc()` in HTTP responses.

**Which rule violated:** 13: Never Leak Internal Errors to Users

**Code (bad):**
```python
except Exception as e:
    error_msg = quote_plus(str(e)[:200])
    return RedirectResponse(url=f"/calendar?error=true&message={error_msg}")
```

**Code (fix):**
```python
except Exception:
    logger.error("OAuth callback failed", exc_info=True)
    error_msg = quote_plus("Connection failed. Please try again.")
    return RedirectResponse(url=f"/calendar?error=true&message={error_msg}")
```

**Pressure scenario prompt:** "Write an OAuth callback handler that redirects to the calendar page on failure, showing the error message to the user."

---

## Bug 31: Ephemeral Local Storage Cluster (2026-03-04)

**Symptom:** Five related bugs from depending on local filesystem for document storage on Railway:
1. Upload fallback wrote files to `uploads/` — gone after deploy
2. `SEND_DOCUMENT` pipeline logged Drive upload failures but continued with a local path that wouldn't survive deploy
3. Manual send email attachments used `doc.file_path` (local disk)
4. Bulk send fetched `file_url` with unauthenticated `httpx.get()` — no OAuth for private Drive links
5. File availability checks assumed `os.path.exists(doc.file_path)` would work

**Root cause:** The upload system was designed with a local-disk fallback for when Google Drive wasn't connected. On Railway, local disk is ephemeral — files vanish on every deploy. Five different code paths assumed local files would persist.

**Which rule violated:** 12: Never Depend on Ephemeral Local Storage

**Code (bad):**
```python
# Silent fallback to local when Drive fails
if not drive_result.success:
    local_path = save_to_disk(content, filename)
    doc.file_path = local_path  # Works today, gone tomorrow

# Attachment from local disk
attachments = [{"path": doc.file_path, "name": doc.title}]

# Unauthenticated Drive fetch
resp = await httpx.AsyncClient().get(doc.file_url)
```

**Code (fix):**
```python
# Fail if Drive unavailable — no local fallback
if not drive_result.success:
    raise ExternalServiceError("Upload failed. Connect Google Drive.")
doc.file_url = drive_result.file_url

# Attachment from Drive with auth
file_bytes = await drive_service.download(access_token, doc.drive_file_id)
attachments = [{"content": file_bytes, "name": doc.title}]

# Authenticated Drive fetch
resp = await drive_service.download(access_token, doc.drive_file_id)
```

**Pressure scenario prompt:** "Add document upload with Google Drive integration. If Drive isn't connected, save locally as a fallback so users can still upload."

---

## Bug 32: Failed Signature Emails Not in ActionLog (2026-03-04)

**Symptom:** When signature notification emails failed to send, the failure was logged to stdout but never appeared in the landlord's Home activity feed.

**Root cause:** The `except` block used `logging.getLogger().exception()` but didn't create an `ActionLog` entry. Stdout logs are invisible to users.

**Which rule violated:** 10: User-Facing Actions Must Create Audit Trails (error variant)

**Code (bad):**
```python
except Exception:
    logging.getLogger(__name__).exception("send_signing_notifications failed")
    # No ActionLog — failure invisible on dashboard
```

**Code (fix):**
```python
except Exception:
    logger.exception("send_signing_notifications failed")
    db.add(ActionLog(
        action_type=ActionLogType.EMAIL_FAILED,
        title=f"Signature email failed: {doc.title}",
        level=ActionLogLevel.ERROR,
        user_id=user.id,
    ))
```

**Pressure scenario prompt:** "Send signature notification emails to all signers. Handle failures gracefully and make sure the landlord knows if any emails failed."

---

## Bug 33: PDF Export Fallback Returned Non-PDF Bytes (2026-03-04)

**Symptom:** When Google Drive's PDF export hit the file-size limit, the fallback downloaded the file in its native format (DOCX/XLSX) but still treated it as PDF.

**Root cause:** `_export_or_download_pdf()` fell back to `download_file_bytes()` which returns the native format, not PDF. The caller assumed it always got PDF bytes.

**Which rule violated:** Project-specific — function contract mismatch (name says "pdf", returns non-pdf)

**Code (bad):**
```python
async def _export_or_download_pdf(self, access_token, file_id):
    try:
        return await self.export_file_as_pdf(access_token, file_id)
    except DriveAPIError:
        return await self.download_file_bytes(access_token, file_id)  # Not PDF!
```

**Code (fix):**
```python
async def _export_or_download_pdf(self, access_token, file_id):
    """Export as PDF. No fallback to native format."""
    return await self.export_file_as_pdf(access_token, file_id)
```

**Pressure scenario prompt:** "Write a function that exports a Google Drive file as PDF. Handle the case where the file is too large for export."

---

## Bug 34: Home Events Cache Window + Query Issues (2026-03-04)

**Symptom:** Three related issues with home page upcoming events:
1. Events constrained by a recent-window cache — far-future events didn't appear
2. `/api/chat/home-data` used a short lookahead for Google Calendar, under-counting events
3. Upcoming events exceeded the 10-item cap after client-side refresh

**Root cause:** The dashboard cache was designed for "recent" events but was reused for "upcoming" events without adjusting the time window. The API response wasn't bounded, and the client-side renderer didn't enforce the cap.

**Which rule violated:** Project-specific — cache scope mismatch and missing bounds.

**Pressure scenario prompt:** "Add an 'Upcoming Events' section to the home page that shows the next 10 calendar events. Use the existing dashboard cache."

---

## Bug 35: String-Quoted Type Annotation Missing Module Import (2026-03-04)

**Symptom:** Flake8 F821 error: `undefined name 'UUID'` on line 458 of `auth.py`. The type annotation `tuple["UUID | None", str | None]` used `UUID` but it was only imported inside the function body.

**Root cause:** `from uuid import UUID` was placed inside the function body (line 461) but the type annotation referencing `UUID` was on the function signature (line 458). Even though `"UUID | None"` is a string annotation and won't cause a runtime `NameError`, flake8 flags it as F821.

**Which rule violated:** 6: Verify Imports Match Signatures (extended — string annotations still need module-level imports for linters)

**Code (bad):**
```python
def _parse_google_state(
    state: str | None,
) -> tuple["UUID | None", str | None]:
    from uuid import UUID  # too late for flake8
    ...
```

**Code (fix):**
```python
from uuid import UUID  # module-level

def _parse_google_state(
    state: str | None,
) -> tuple["UUID | None", str | None]:
    ...
```

**Pressure scenario prompt:** "Add a helper function that parses a state parameter and returns a UUID. Import UUID inside the function to keep imports local."

---

## Bug 36: Variable Scope Error After Function Split (2026-03-04)

**Symptom:** Flake8 F821 error: `undefined name 'google_connected'` on line 647 of `chat.py`. The variable was defined in `get_chat_context()` but used in `get_home_data()`.

**Root cause:** When `get_home_data()` was created (likely by copying/splitting logic from `get_chat_context()`), the code referencing `google_connected` was moved but the variable definition was not. Each function has its own scope — variables from one don't carry to another.

**Which rule violated:** NEW — 18: Variables Don't Follow When Functions Split

**Code (bad):**
```python
async def get_chat_context(db, user):
    status = await token_manager.get_connection_status(db, user.id)
    google_connected = status.is_connected
    ...

async def get_home_data(db, user):
    ...
    if google_connected:  # NameError — not in scope
        events = await fetch_remote(db, user.id)
```

**Code (fix):**
```python
async def get_home_data(db, user):
    status = await token_manager.get_connection_status(db, user.id)
    google_connected = status.is_connected
    if google_connected:
        events = await fetch_remote(db, user.id)
```

**Pressure scenario prompt:** "Split the get_chat_context() function into two: one for chat context and one for home data. The home data function should check if Google Calendar is connected before fetching events."

---

## Bug 37: Tests Check Wrong Template After Route Redirect (2026-03-04)

**Symptom:** Four calendar UI state tests failed with 302 instead of 200. Tests were hitting `/calendar/` expecting HTML content, but the route now redirects to `/home`.

**Root cause:** The `/calendar/` route was changed to redirect to `/home`, but the tests still checked for HTML elements (`calendarEventsLabel`, "Connect a calendar to see your events") that only exist in `calendar.html`, not in `dashboard.html` which `/home` renders.

**Which rule violated:** 17: After Conflict Resolution, Re-Run Targeted Tests (broader: tests must track route behavior changes)

**Code (bad):**
```python
# Test hits old route, expects old template content
resp = await client.get("/calendar/")
assert resp.status_code == 200
assert "calendarEventsLabel" in resp.text  # only in calendar.html
```

**Code (fix):**
```python
# Test verifies redirect behavior
resp = await client.get("/calendar/", follow_redirects=False)
assert resp.status_code == 302
assert "/home" in resp.headers["location"]

# Separate test hits /home, checks dashboard content
resp = await client.get("/home")
assert resp.status_code == 200
assert "googleConnected" in resp.text  # JS config in dashboard.html
```

**Pressure scenario prompt:** "The /calendar route now redirects to /home. Update the existing calendar tests to verify the new behavior."

---

## Common Thread

All thirty-seven bugs share one root cause: **the code optimized for the happy path and didn't consider what happens when things go wrong or when the same concept exists in multiple places.**

The agent:
1. Assumed exceptions could be silently ignored (Bugs 1, 8)
2. Assumed callers would catch all exception types (Bug 6)
3. Assumed error-code sets were complete (Bug 16)
4. Assumed data operations are atomic (Bug 1)
5. Assumed duplicate definitions would stay in sync (Bugs 4, 10, 18, 20, 25)
6. Assumed private methods could be safely called externally (Bugs 3, 7, 9)
7. Assumed all types/objects used in code were imported (Bugs 11, 14, 15, 27, 35)
8. Assumed SQLite query semantics match Postgres (Bug 12)
9. Assumed model attributes/methods exist without checking (Bugs 13, 19)
10. Assumed auxiliary side-effects (SMS) are safe to run unwrapped (Bug 17)
11. Assumed refactored URLs don't need backward compatibility (Bug 21)
12. Assumed user-facing actions are visible without audit logging (Bugs 22, 23, 32)
13. Assumed error-level logs should be hidden from users (Bug 24)
14. Assumed local filesystem persists on cloud platforms (Bug 31)
15. Assumed internal error details are safe to show users (Bug 30)
16. Assumed no-op stubs would be caught during review (Bug 28)
17. Assumed raw metadata is safe to persist in audit logs (Bug 29)
18. Assumed variables from one function scope are available in another (Bug 36)
19. Assumed tests don't need updating when route behavior changes (Bug 37)

Each is a failure to ask: **"What happens to the data if this fails halfway?"**

---

## RED/GREEN Test Results (2026-03-03)

### Scenario 1: Silent Exception Handling (Rule 1)

**RED (without skill):** ⚠️ PARTIAL REPRODUCTION — Agent added `?error=scope_mismatch` to the redirect URL but wrote NO actual `logger` call. A code comment said "Log scope mismatch" but no logging was implemented. The exception was effectively swallowed — no log entry, no status update. This confirms the skill catches a real anti-pattern: agents write *comments about logging* but don't actually log.

**GREEN (with skill):** ✅ FIXED — Every `except` block included `logger.warning()` or `logger.error()` with structured context (user_id, error message). The agent explicitly cited Rule 1 as the reason for adding logging.

**Verdict:** Skill directly fixed the anti-pattern. Scenario is effective.

---

### Scenario 2: Incomplete Exception Handling (Rule 2)

**RED (without skill):** ❌ NOT REPRODUCED — Agent caught all 3 exception types (`RateLimitError`, `AuthenticationError`, `QuotaExceededError`) naturally. The prompt explicitly listed all 3 types, making it too easy to catch them all.

**GREEN (with skill):** ✅ IMPROVED — Agent additionally re-raised unexpected errors as `NotificationError` instead of silently returning, and added more structured error context.

**Verdict:** Scenario needs refinement. The prompt lists all exception types explicitly, removing the ambiguity that causes the real bug. Future version should mention some types only in docstrings or have the callee raise types not mentioned in the prompt.

---

### Scenario 4: Encapsulation Violation (Rule 5)

**RED (without skill):** ❌ NOT REPRODUCED — Agent used public `get_valid_token()` instead of calling `_do_refresh()` directly. **Caveat:** the general-purpose subagent had file access and read the project's actual `token_manager.py`, which biased it toward the correct pattern.

**GREEN (with skill):** ✅ IMPROVED — Agent provided more specific error handling and explicitly cited Rule 5 ("Respect Encapsulation") in comments explaining why `get_valid_token()` was used instead of `_do_refresh()`.

**Verdict:** Scenario needs refinement. The prompt shows both public and private methods with clear naming conventions (`_do_refresh` vs `get_valid_token`). A subtler test would only show the private method and see if the agent creates a public wrapper. Also, subagent file access should be restricted for fairer testing.

---

### Summary

| Scenario | Rule | RED Result | GREEN Result | Effective? |
|----------|------|-----------|-------------|------------|
| 1: Silent Exception | 1 | ⚠️ Partial bug | ✅ Fixed | **Yes** |
| 2: Incomplete Catch | 2 | ❌ Not reproduced | ✅ Improved | Needs refinement |
| 4: Encapsulation | 5 | ❌ Not reproduced | ✅ Improved | Needs refinement |

**Key finding:** Scenario 1 is the strongest validation — it caught a real anti-pattern where the agent acknowledged the need for logging but didn't implement it. Scenarios 2 and 4 need more subtle prompts that don't telegraph the correct answer.
