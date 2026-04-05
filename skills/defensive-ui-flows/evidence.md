# Defensive UI Flows — Evidence Log

> To add a new bug, copy the template below and fill it in.
> Then run `/update-defensive-ui` to test and update the skill.

## Quick-Add Template

<!-- Copy everything between the dashes, paste at the end of the Bugs section, and fill in -->
<!--
---

## Bug N: SHORT_NAME (DATE)

**Symptom:** What the user reported.

**Root cause:** What actually went wrong in the code.

**Which rule violated:** [1: Silent Guard | 2: Stuck Flag | 3: Overlay Feedback | 4: Navigation Reset | NEW]

**Code (bad):**
```javascript
// the broken pattern
```

**Code (fix):**
```javascript
// the corrected pattern
```

**Pressure scenario prompt:** A generic task prompt that would reproduce this bug.
-->

---

## Bug 1: Silent Guard Clause (2026-03-03)

**Symptom:** "Send for Signatures" button does nothing on click.

**Root cause:** `_isSending` boolean guard returned silently:
```javascript
// BAD — user sees nothing
function sendForSignatures() {
    if (_isSending) return;
    // ...
}
```

**What agent did wrong:** Wrote a guard clause that silently exits with no user feedback. The user clicked repeatedly, assumed the feature was broken.

**Fix pattern:**
```javascript
// GOOD — user sees feedback
function sendForSignatures() {
    if (_isSending) {
        showToast('Already sending — please wait.', true);
        return;
    }
    // ...
}
```

**Pressure scenario:** "Add a rate-limit guard to prevent double-submit on a payment button."

---

## Bug 2: Stuck State Flag (2026-03-03)

**Symptom:** After one failed send attempt, the Send button permanently stops working — even on retry.

**Root cause:** `_isSending = true` was set before synchronous code that could throw. The throw skipped the cleanup in the `.catch()` handler because it happened before the promise chain started.

```javascript
// BAD — sync throw leaves flag stuck
_isSending = true;
setSendButtonBusy(true);

// This line can throw if element doesn't exist
var codeEl = document.getElementById('drawerAccessCode' + index);
codeEl.value.trim();  // TypeError if codeEl is null

// Promise chain never starts, .catch() never runs
core.saveSigners().then(...)
    .catch(function() { _isSending = false; });
```

**Fix pattern:**
```javascript
// GOOD — wrap sync code in try-catch
_isSending = true;
setSendButtonBusy(true);
try {
    // sync code that might throw
    var codeEl = document.getElementById('drawerAccessCode' + index);
    var codeVal = codeEl && codeEl.value ? codeEl.value.trim() : '';
} catch (syncErr) {
    console.error('sync error:', syncErr);
    _isSending = false;
    setSendButtonBusy(false);
    showToast('Unexpected error.', true);
    return;
}
// NOW start promise chain
core.saveSigners().then(...)
```

**Pressure scenario:** "Add a loading spinner to an async form submit that calls an API."

---

## Bug 3: Toast Hidden Behind Overlay (2026-03-03)

**Symptom:** Validation fires correctly, toast notification fires correctly, but user reports "nothing happens" — error message is invisible.

**Root cause:** Toast container at `z-index: 1200` should render above the drawer at `z-index: 1050`, but in practice the toast was not visible to the user. Possible causes: stacking context isolation, toast positioned outside viewport, or drawer backdrop intercepting focus.

**What agent did wrong:** Relied solely on an external notification system (toasts) for feedback inside an overlay UI (drawer). Never verified that the toast was actually visible when the drawer was open.

**Fix pattern:** Add inline feedback element directly inside the overlay:
```html
<div class="drawer-status" id="drawerStatus"
     role="alert" aria-live="polite"
     style="display:none;"></div>
```
```javascript
function showDrawerStatus(message, isError) {
    var el = document.getElementById('drawerStatus');
    if (!el) return;
    el.textContent = message;
    el.className = 'drawer-status ' +
        (isError ? 'is-error' : 'is-success');
    el.style.display = '';
}
```

**Pressure scenario:** "Add form validation to a modal dialog. Show errors when required fields are missing."

---

## Bug 4: Button Disabled State Not Reset (2026-03-03)

**Symptom:** After navigating back from Review step to Signers step, the "Continue to Review" button is permanently disabled.

**Root cause:** `_nextBtn.disabled = true` was set during the send flow, but `setPanel()` — the function that handles step navigation — never reset it.

**Fix pattern:** Reset ALL transient state in navigation functions:
```javascript
function setPanel(stepIndex) {
    // Reset button states
    if (_nextBtn) {
        _nextBtn.disabled = false;
        _nextBtn.textContent = '';
        // ... set correct text for this step
    }
    // Reset inline errors
    clearDrawerStatus();
    // Show/hide panels
    _panels.forEach(function(panel, i) {
        panel.classList.toggle('is-active', i === stepIndex + 1);
    });
}
```

**Pressure scenario:** "Build a wizard with Back/Next buttons and a final Submit step."

---

## Bug 7: Viewport Culling Hid Workflow Steps (2026-03-04)

**Symptom:** Some workflow steps didn't render in the vertical timeline. Steps were present in the data but invisible.

**Root cause:** `getVisibleStepsForViewport` was filtering steps based on scroll position. Steps outside the current viewport were excluded from the render list — but the timeline wasn't tall enough to scroll, so hidden steps could never become visible.

**Which rule violated:** Not a direct rule violation — a performance optimization that broke correctness. Related to Rule 4 (state management) in that render state diverged from data state.

**Code (bad):**
```javascript
getVisibleStepsForViewport() {
    var scrollTop = this.$el.scrollTop;
    var viewportH = this.$el.clientHeight;
    return this.steps.filter(function(s) {
        return s.y >= scrollTop - 200 && s.y <= scrollTop + viewportH + 200;
    });
}
```

**Code (fix):**
```javascript
getVisibleStepsForViewport() {
    // Vertical timeline: always show all steps (no culling)
    return this.steps;
}
```

**Pressure scenario:** "Add performance optimizations to a scrollable list component. Only render visible items."

---

## Bug 8: Home Events Not Clickable (2026-03-04)

**Symptom:** Upcoming events on the home dashboard had no interactivity — clicking did nothing. Users expected events to navigate to the calendar.

**Root cause:** Event items were rendered as `<div>` elements with no click handler or link. Both the server-rendered Jinja template and the JS-refreshed version had the same issue.

**Which rule violated:** Rule 1 (Guard Clauses Must Give Feedback) — broader principle: every user-facing UI element that looks interactive must BE interactive.

**Code (bad):**
```html
<div class="home-event-item">
    <span class="event-title">Move-In: Unit 2B</span>
</div>
```

**Code (fix):**
```html
<a href="/calendar?event={{ event.id }}" class="home-event-item home-event-item-link">
    <span class="event-title">Move-In: Unit 2B</span>
</a>
```

**Pressure scenario:** "Add an upcoming events feed to a dashboard page. Show the next 5 events with date and title."

---

## Bug 9: Duplicate Google Calendar Text (2026-03-04)

**Symptom:** Event detail modal showed Google Calendar description text twice — once in the description field and again in a dedicated Google Calendar block.

**Root cause:** The modal template rendered `event.description` in the body AND separately extracted Google Calendar metadata from the same description. When the description contained calendar-formatted text, it appeared in both places.

**Which rule violated:** Rule 4 (Multi-Step UI State Reset) — broader: when two UI sections derive from the same data, one must suppress the other.

**Pressure scenario:** "Show event details in a modal. Include both the description and a link to the Google Calendar event."

---

## Bug 10: Workflow Builder Canvas Layout (2026-03-04)

**Symptom:** Workflow builder canvas was constrained to 672px max-width. Empty state had excessive spacing. AI sidebar textarea was too tall, pushing content below the fold.

**Root cause:** Multiple CSS layout issues: canvas container had `max-width: 672px`, empty state had oversized padding, and the AI textarea used `flex: 1` which expanded to fill available space.

**Which rule violated:** Not a defensive-flow rule — CSS layout correctness. Documented for completeness.

**Code (bad):**
```css
.builder-canvas { max-width: 672px; }
.ai-sidebar-textarea { flex: 1; min-height: 200px; }
```

**Code (fix):**
```css
.builder-canvas { max-width: none; width: 100%; }
.ai-sidebar-textarea { flex: 0 0 auto; min-height: 100px; resize: vertical; }
```

---

## Bug 11: Iframe Preview Fails for Protected Files (2026-03-04)

**Symptom:** PDF preview in document detail panel and signing setup showed blank/error. Worked for public files but failed for any file requiring auth.

**Root cause:** Preview used `<iframe src="/api/documents/ID/preview">`. Iframes cannot send auth headers (credentials, CSRF tokens). The server returned 401/403. Also, Google Drive URLs have `X-Frame-Options: deny`, so even raw Drive URLs failed.

**Which rule violated:** Rule 10 (API Fetches in Overlays Must Send Auth Headers)

**Code (bad):**
```javascript
// iframe can't send auth headers
previewFrame.src = '/api/documents/' + id + '/preview';
// Also bad: raw Google Drive URL blocked by X-Frame-Options
previewFrame.src = driveFileUrl;
```

**Code (fix):**
```javascript
// Backend proxy route fetches via Drive API with user's OAuth token
// Returns same-origin content that iframe can display
previewFrame.src = '/documents/' + id + '/download?proxy=true';
```

**Learned from:** `documents.html` — PDF preview failed silently. `signing-setup-core.js` — signing preview also failed. Fix: backend proxy route that fetches via Drive API with user's OAuth token and streams back.

---

## Bug 12: Upload Flow Missing Dependency Check (2026-03-04)

**Symptom:** User opened upload modal, filled out all fields, clicked Upload — THEN got "Google Drive not connected" error. Wasted effort.

**Root cause:** Upload modal opened without checking if Google Drive was connected. The dependency check only happened at upload time, after the user had already filled the form.

**Which rule violated:** Rule 11 (Pre-Check Dependencies Before Destructive Actions)

**Code (bad):**
```javascript
function openUploadModal() {
    uploadModal.show();  // No dependency check
}
// User fills form... clicks Upload...
async function handleUpload(file) {
    var result = await fetch('/api/documents/upload', { body: formData });
    // 500 error: Drive not connected — too late!
}
```

**Code (fix):**
```javascript
async function openUploadModal() {
    var status = await fetch('/api/drive-status', { credentials: 'same-origin' });
    var data = await status.json();
    if (!data.connected) {
        showToast('Connect Google Drive in Settings to upload files.', true);
        return;
    }
    uploadModal.show();
}
```

**Learned from:** `documents.html` — Upload modal had no pre-check for Drive connectivity. Also: `/api/drive-status` endpoint was added specifically for this check.

---

## Bug 13: Non-PDF Upload Validation Mismatch (2026-03-04)

**Symptom:** Documents page file input had `accept="application/pdf,.pdf"` but backend accepted Word docs, images, and other formats. Help text said "PDF, Word, images" but the browser only offered PDFs in the file picker.

**Root cause:** Frontend `accept` attribute, help text, and backend `ALLOWED_EXTENSIONS` set all disagreed. The HTML was PDF-only, the backend accepted 20+ formats, and the help text listed a third set.

**Which rule violated:** Rule 9 (Form Accept Attributes Must Match API Validation)

**Code (bad):**
```html
<input type="file" accept="application/pdf,.pdf">
<!-- No help text showing what's accepted -->
```

**Code (fix):**
```html
<input type="file" accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.jpg,.jpeg,.png,.gif,.txt,.rtf,.csv">
<div class="form-text">Accepted: PDF, Word, Excel, PowerPoint, images, text (max 10MB)</div>
```

---

## Bug 14: Signer Prefill Missing Tenants (2026-03-04)

**Symptom:** Signing setup only showed some tenants for a property. Tenants who existed as `Client` records (not `HouseholdMember`) were missing from the signer dropdown.

**Root cause:** The `/signing-setup` endpoint only queried `HouseholdMember` table. Tenants could also be stored in the `Client` table with `household_id` linking them to a property. The query needed to UNION both sources, deduplicating by email.

**Which rule violated:** Backend Rule 8 (Verify Model Attributes Before Access) — broader: verify the complete data model before building a query. One table doesn't mean one source.

**Code (bad):**
```python
# Only queries HouseholdMember — misses Client-table tenants
members = await db.execute(
    select(HouseholdMember).where(
        HouseholdMember.household_id == doc.property_id
    )
)
```

**Code (fix):**
```python
# Query HouseholdMember first, then also check Client table
members = await db.execute(
    select(HouseholdMember).where(...)
)
for member in members:
    seen_emails.add(member.email.lower())
    suggested_signers.append(...)

# Also check Client records linked to this property
clients = await db.execute(
    select(Client).where(
        Client.household_id == doc.property_id,
        Client.user_id == user.id,
    )
)
for client in clients:
    if client.email.lower() in seen_emails:
        continue  # Dedup by email
    suggested_signers.append(...)
```

**Learned from:** `documents.py` signing-setup endpoint — tenants stored only in Client table were invisible in signing drawer.

---

## Bug 15: Upcoming Events String Compare Instead of Datetime (2026-03-04)

**Symptom:** Home dashboard upcoming events filter showed stale or wrong events. Events near midnight or across timezone boundaries appeared/disappeared incorrectly.

**Root cause:** The filter compared ISO strings lexicographically (`e.get("start_time", "") >= now_iso`) instead of parsing to real `datetime` objects. String comparison breaks when timezone offsets differ (e.g., `+00:00` vs `-05:00` vs `Z`), producing wrong sort order and incorrect future/past classification.

**Which rule violated:** Not a direct UI-flow rule — data type correctness. Comparing date strings instead of datetimes is a silent logic bug.

**Code (bad):**
```python
now_iso = datetime.now(timezone.utc).isoformat()
future_events = [
    _format_event_for_display(e, tz_name)
    for e in events
    if e.get("start_time", "") >= now_iso
][:10]
```

**Code (fix):**
```python
now_utc = datetime.now(timezone.utc)
future_events = []
for event in events:
    start_str = event.get("start_time")
    if not start_str:
        continue
    try:
        start_dt = datetime.fromisoformat(
            start_str.replace("Z", "+00:00")
        )
    except ValueError:
        continue
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if start_dt < now_utc:
        continue
    future_events.append(
        _format_event_for_display(event, tz_name)
    )
future_events = future_events[:10]
```

**Learned from:** `dashboard_service.py` — upcoming events filter used string compare. Tests added in `test_dashboard_service.py` to prevent regression.

---

## Bug 16: Upload Action No-Op on Click Path (2026-03-04)

**Symptom:** Clicking "Upload & Create Document" did nothing. No error, no feedback — the button appeared to work but the upload never fired.

**Root cause:** The upload logic was bound to a button `click` handler, but the button lived inside a `<form>`. Depending on how the user triggered it (click vs Enter vs form submit), the handler might not fire. The click handler also didn't call `preventDefault()`, so the form could submit-and-reload before the async upload started.

**Which rule violated:** Rule 1 (Guard Clauses Must Give Feedback) + Rule 2 (State Flags Need Try-Catch) — broader: actions triggered by form buttons must bind to `submit` event on the form, not `click` on the button.

**Code (bad):**
```javascript
// Click handler on button inside a form — unreliable
uploadBtn.addEventListener('click', function() {
    var file = fileInput.files[0];
    if (!file) return;  // silent guard
    uploadFile(file);
});
```

**Code (fix):**
```javascript
// Bind to form submit — reliable regardless of trigger method
uploadForm.addEventListener('submit', function(e) {
    e.preventDefault();
    var file = fileInput.files[0];
    if (!file) {
        showToast('Please select a file first.', true);
        return;
    }
    uploadFile(file);
});
```

**Learned from:** `documents.html` — upload button click handler was unreliable. Switching to form `submit` event ensured the action fires consistently.

---

## Bug 17: UI State Tests Check Wrong Template After Redirect (2026-03-04)

**Symptom:** Four calendar UI state consistency tests failed with HTTP 302 instead of 200. Tests were hitting `/calendar/` and asserting on `calendarEventsLabel` and "Connect a calendar to see your events" — elements from `calendar.html`.

**Root cause:** The `/calendar/` route was changed to redirect to `/home`, which renders `dashboard.html`. The tests still asserted on elements unique to `calendar.html`. The first fix attempt naively changed the URL to `/home` but kept the same assertions — which still failed because those elements don't exist in `dashboard.html`.

**Which rule violated:** Rule 19 (Primary Views Must Surface Data Source Status) — broader: when a route redirects, tests must assert on the redirect target's actual content, not the old template's elements.

**Code (bad):**
```javascript
// Test hits route that now redirects, asserts on old template's elements
resp = await client.get("/calendar/");
assert resp.status_code == 200;  // Actually 302
assert "calendarEventsLabel" in resp.text;  // Only in calendar.html
```

**Code (fix):**
```javascript
// Separate test for redirect behavior
resp = await client.get("/calendar/", follow_redirects=False);
assert resp.status_code == 302;

// State test hits the actual destination, asserts on its content
resp = await client.get("/home");
assert "googleConnected" in resp.text;  // JS config in dashboard.html
```

**Learned from:** `test_api_calendar.py` — `TestCalendarEventsBadgeState` class had 4 tests checking `calendar.html` elements, but `/calendar/` now redirects to `/home` → `dashboard.html`.

---

## Common Thread

All 17 bugs share one root cause: **the agent optimized for the happy path and didn't think about what the user sees when something goes wrong** — or when the data model is more complex than assumed.

The agent:
1. Assumed guard clauses don't need feedback (Bug 1)
2. Assumed promise `.catch()` covers all errors (Bug 2)
3. Assumed external notification systems always work (Bug 3)
4. Assumed UI state only needs to be set, not reset (Bug 4)
5. Assumed performance optimizations don't break correctness (Bug 7)
6. Assumed list items don't need to be interactive (Bug 8)
7. Assumed iframes can send auth headers (Bug 11)
8. Assumed dependencies are available at action time (Bug 12)
9. Assumed frontend accept attrs match backend validation (Bug 13)
10. Assumed one table contains all records of a type (Bug 14)
11. Assumed string comparison works for datetimes across timezones (Bug 15)
12. Assumed button click == form submit (Bug 16)
13. Assumed tests checking old template elements still valid after route redirect (Bug 17)

Each is a failure to ask: **"What does the user see if this fails?"** or **"Is this the complete picture?"**

---

## Baseline Test Results (RED Phase — 2026-03-03)

### Scenario 1: Double-Submit Guard → **Bug 1 CONFIRMED**

Agent (haiku, no skill) wrote:
```javascript
if (paymentInProgress) {
    return;  // ← SILENT. No feedback.
}
```
- Guard clause returns silently — user sees nothing ✅ BUG REPRODUCED
- No try-catch around pre-async sync code (Bug 2 partial)
- Did use `.finally()` for cleanup — good practice naturally applied
- Did NOT show feedback when guard blocks

### Scenario 3: Checkout Modal → **Bug 3 NOT triggered, Bug 4 PARTIAL**

Agent (haiku, no skill) wrote inline errors inside the modal:
```javascript
showError(message) {
    const errorEl = this.modal.querySelector('[data-error-message]');
    // ...
}
```
- Used inline error element inside the modal ✅ GOOD (Bug 3 not triggered)
- `updateUI()` clears errors on navigation ✅ GOOD
- BUT `updateUI()` does NOT reset `nextBtn.disabled` ⚠️ Bug 4 partial
- `handleConfirm()` doesn't disable button during async work ⚠️ Bug 2 partial

**Key insight on Bug 3:** When building a modal FROM SCRATCH, agents naturally
use inline errors. Bug 3 manifests when ADDING validation to an EXISTING overlay
that already has an external notification system (like toasts). The agent reuses
the existing pattern instead of questioning whether it's visible.

**Refined scenario needed:** "An existing app uses `window.showToast()` for all
notifications. Add required-field validation to an existing modal dialog.
Show errors when fields are empty."

---

## GREEN Phase Results (WITH Skill — 2026-03-03)

### Scenario 1 (Double-Submit Guard): **PASSED ✅**

Agent (haiku, WITH skill injected) wrote:
```javascript
if (btn.disabled) {
    showNotification('Payment is already processing. Please wait.', 'error');
    return;
}
```
- Guard clause shows feedback ✅ (was silent without skill)
- Added try-catch around pre-promise validation ✅
- Resets button state in both .then() and .catch() ✅
- Saves originalText to restore button text ✅

**Comparison:**
| Behavior | WITHOUT Skill | WITH Skill |
|----------|--------------|------------|
| Guard clause | Silent `return` | Shows notification + `return` |
| Pre-async try-catch | None | Yes, wraps validation |
| Button state cleanup | `.finally()` only | Both `.then()` and `.catch()` |

**Verdict:** Skill directly fixed the confirmed Bug 1 anti-pattern.

---

## Known Loopholes for Future REFACTOR Iterations

### Loophole 1: Bug 3 (Overlay Feedback) not triggered by "build from scratch" prompts
- When building a modal from scratch, agents naturally use inline errors
- Bug 3 only manifests when ADDING validation to an EXISTING overlay that uses toasts
- **Next test:** Provide existing code with `showToast()` and ask agent to add validation to a modal
- Status: **UNTESTED** — needs a more realistic scenario

### Loophole 2: Bug 4 (Navigation Reset) only partially triggered
- Agent's `updateUI()` DID clear errors but did NOT reset `nextBtn.disabled`
- Skill may need stronger emphasis on "reset ALL transient state including disabled"
- Status: **PARTIAL** — skill addresses it but hasn't been retested

### Loophole 3: Combined scenario (Bug 5) not tested
- The Scenario 5 (full signing drawer) hasn't been run yet
- This is the most realistic test — all four bugs in one flow
- Status: **UNTESTED** — save for next session

### Loophole 5: Bug 5 — Undefined CSS Design Token (2026-03-04)

**Symptom:** Slideout panel rendered with no shadow, making it look flat/unfinished.

**Root cause:** CSS referenced `--ds-shadow-elevated` which doesn't exist in `_variables.css`. Without a fallback value, the `box-shadow` property silently evaluates to nothing.

**Which rule violated:** NEW — Rule 8: Verify Design System Tokens Exist

**Code (bad):**
```css
.slideout-panel {
    box-shadow: var(--ds-shadow-elevated);
}
```

**Code (fix):**
```css
.slideout-panel {
    box-shadow: var(--ds-shadow-modal);
}
```

**Pressure scenario prompt:** "Style a slide-out panel component using the project's design system CSS variables. Add shadow, background, and border-radius."

---

### Loophole 4: Word count (608 words) exceeds guideline
- Writing-skills guide says < 500 words for non-frequently-loaded skills
- Current skill is 608 words — could trim examples
- Status: **LOW PRIORITY** — skill is effective, trim later if needed

### Loophole 6: Bug 6 — Form Accept/Validation Contract Mismatch (2026-03-04)

**Symptom:** Documents page accept attribute restricted to PDF-only, but tenant upload page accepted Word/images. Help text on tenant page said "PDF, Word, images" but documents page had no help text matching its PDF-only restriction.

**Root cause:** Two different templates for file upload had inconsistent `accept` attributes and help text. Neither was verified against the backend validation.

**Which rule violated:** NEW — Rule 9: Form Accept Attributes Must Match API Validation

**Code (bad):**
```html
<!-- documents.html — PDF only, no help text -->
<input type="file" accept="application/pdf,.pdf">

<!-- tenant upload — accepts everything, mismatched text -->
<input type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png">
<div class="form-text">Accepted formats: PDF, Word, images (max 10MB)</div>
```

**Code (fix):**
```html
<!-- Each page's accept + help text + backend validation must agree -->
<input type="file" accept=".pdf,.doc,.docx,.jpg,.jpeg,.png">
<div class="form-text">Accepted formats: PDF, Word, images (max 10MB)</div>
```

**Pressure scenario prompt:** "Add a file upload feature to a document management page. The app already has an upload on the tenant portal page."

---

### Future evidence to collect
- Any new bugs found in future sessions that fit these patterns
- Edge cases: what about `async/await` vs Promise chains?
- Framework-specific: does this apply to React/Vue or only vanilla JS?
- File upload contract mismatches across different pages (partially addressed by Bug 13)
- Auth-header patterns for non-iframe fetches (fetch + credentials vs blob URL)
- Pre-check dependency patterns beyond Google Drive (Twilio, OpenAI, etc.)
