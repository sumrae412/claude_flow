# Defensive Backend Flows — Pressure Scenarios

> These scenarios test whether an agent naturally avoids the bugs
> documented in evidence.md. Run WITHOUT the skill first (RED phase).

---

## Scenario 1: Silent Exception Handling (Maps to Bug 8 — Rule 1)

**Prompt:**
> Write a Python OAuth callback handler function `handle_oauth_callback(code, state, db)` that:
> 1. Exchanges the auth code for tokens using `oauth_client.exchange_code(code)`
> 2. Stores the access token and refresh token on the user record
> 3. Checks if the granted scopes include 'drive.file' using `validate_scopes(token_data)`
> 4. `validate_scopes()` raises `ScopeMismatchError` if scopes are missing
> 5. The function should handle errors gracefully and always redirect the user to '/dashboard'

**What to watch for:**
- Does the agent write `except ScopeMismatchError: pass`?
- Does the `except` block log the error or update a status field?
- Is there any indication to the user/system that scopes are missing?

**Failure = exception caught with no logging, no status update, no re-raise**

---

## Scenario 2: Incomplete Exception Handling (Maps to Bug 6 — Rule 2)

**Prompt:**
> Write a Python function `send_notification(user, message, db)` that:
> 1. First tries to send via a premium API: `premium_api.send(user, message)`
> 2. The premium API can raise: `RateLimitError`, `AuthenticationError`, or `QuotaExceededError`
> 3. If the premium API fails for any of those reasons, fall back to `basic_smtp.send(user, message)`
> 4. Log which method was used
> 5. Return a dict with 'method' ('premium' or 'smtp') and 'success' (bool)

**What to watch for:**
- Does the agent catch ALL THREE exception types in the fallback?
- Or does it miss one (commonly `QuotaExceededError`)?
- Does it use a generic `except Exception` (too broad) instead of specific types?

**Failure = one or more specific exception types missing from the except clause, causing unhandled crash instead of fallback**

---

## Scenario 3: Data Migration Safety (Maps to Bug 1 — Rule 3)

**Prompt:**
> Write an Alembic migration that moves user notification preferences from the `users` table
> (columns: `email_notifications`, `sms_notifications`, `notification_frequency`)
> into a new `notification_preferences` table with columns:
> `id`, `user_id`, `channel` (email/sms), `enabled`, `frequency`.
> After migrating the data, remove the old columns from `users`.
> Include both `upgrade()` and `downgrade()` functions.

**What to watch for:**
- Does the migration create the new table and INSERT data BEFORE altering/dropping the old columns?
- Or does it drop/alter the columns first (data loss)?
- Does `downgrade()` actually reverse the operation or is it `pass`/empty?
- Is the data copy a single atomic operation or could it partially fail?

**Failure = columns dropped/NULLed before data is copied to new table, OR downgrade is empty**

---

## Scenario 4: Encapsulation Violation (Maps to Bugs 3, 7 — Rule 5)

**Prompt:**
> You have an existing `TokenStore` class (shown below). Write a `refresh_user_session()`
> service function that refreshes the user's OAuth token.
>
> ```python
> class TokenStore:
>     async def _do_refresh(self, db, connection):
>         """Internal: refresh token via HTTP, update connection fields."""
>         resp = await self._http_client.post('/oauth/token', ...)
>         connection.access_token = resp['access_token']
>         connection.expires_at = datetime.now() + timedelta(seconds=resp['expires_in'])
>         connection.record_success()
>         await db.flush()
>
>     async def get_valid_token(self, db, user_id):
>         """Public: get a valid token, refreshing if needed."""
>         conn = await self._get_connection(db, user_id)
>         if conn.is_expired:
>             await self._do_refresh(db, conn)
>         return conn.access_token
> ```
>
> Your function should refresh the token and handle errors.
> Return a tuple of (success: bool, error: Optional[str]).

**What to watch for:**
- Does the agent call `token_store._do_refresh()` directly?
- Or does it use `token_store.get_valid_token()` or suggest adding a public method?
- If it calls `_do_refresh`, does it also manually update `connection.record_success()` — causing a double side-effect?

**Failure = calling `_do_refresh()` directly from outside the class**

---

## Scenario 5: Combined Pressure (Rules 1, 2, 5)

**Prompt:**
> Write a Python service function `process_payment(user_id, amount, db)` that:
> 1. Looks up the user's payment connection using `payment_store.get_connection(db, user_id)`
> 2. Validates the connection is active (raises `ConnectionInactiveError` if not)
> 3. Checks the daily spending limit using `payment_store.check_limit(db, user_id)`
>    - This can raise `LimitExceededError` or `ConnectionNotFoundError`
> 4. Charges the payment using `payment_store._charge(db, connection, amount)`
>    - Note: `_charge` is the internal method that handles the actual API call
>    - It internally records success/failure on the connection
> 5. If any payment-related error occurs, fall back to `backup_processor.charge(user_id, amount)`
> 6. Return a dict with 'processor' ('primary' or 'backup'), 'success', and 'transaction_id'
>
> Handle all errors gracefully. This is critical path code.

**What to watch for (all three patterns):**
- Does it catch ALL exception types from `check_limit`? (Rule 2)
- Does it call `_charge` directly? (Rule 5)
- Does any `except` block silently pass without logging? (Rule 1)

**Failure = ANY of the three anti-patterns present**
