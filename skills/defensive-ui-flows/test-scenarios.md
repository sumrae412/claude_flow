# Defensive UI Flows — Pressure Scenarios

> These scenarios test whether an agent naturally avoids the bugs
> documented in evidence.md. Run WITHOUT the skill first (RED phase).

---

## Scenario 1: Double-Submit Guard (Maps to Bug 1)

**Prompt:**
> Write a JavaScript function `submitPayment(amount)` that:
> 1. Shows a loading spinner on the button
> 2. Calls `api.processPayment(amount)` (returns a Promise)
> 3. On success, shows a success message
> 4. On failure, shows an error message
> 5. Prevents double-submission if the user clicks rapidly

**What to watch for:**
- Does the agent add a guard clause (`if (isSubmitting) return`)?
- If so, does the guard show feedback to the user, or return silently?
- Does the agent wrap pre-async code in try-catch?
- Does the agent reset button state in ALL exit paths?

**Failure = silent return from guard with no user feedback**

---

## Scenario 2: Async State Flag (Maps to Bug 2)

**Prompt:**
> Write a JavaScript function `saveAndPublish()` that:
> 1. Sets `_isPublishing = true` and disables the Publish button
> 2. Reads form values from the DOM (title, body, category select)
> 3. Validates the form values (title required, body min 10 chars)
> 4. Calls `api.saveDraft(data)` then `api.publish(draftId)`
> 5. On completion, re-enables the button and shows status

**What to watch for:**
- Is `_isPublishing = true` set before DOM reads that could throw?
- If DOM read throws (element missing), does `_isPublishing` get reset?
- Is there a try-catch around synchronous code between flag-set and promise-start?
- Are ALL exit paths (success, API error, sync error) cleaning up the flag?

**Failure = state flag set before unprotected sync code**

---

## Scenario 3: Modal/Overlay Feedback (Maps to Bug 3)

**Prompt:**
> Build a multi-step checkout modal in JavaScript:
> 1. Step 1: Shipping address form
> 2. Step 2: Payment method
> 3. Step 3: Review & confirm
> Add validation that prevents advancing if required fields are empty.

**What to watch for:**
- Where does the agent show validation errors?
- Does it use an external toast/notification system only?
- Does it add inline error display within the modal itself?
- If using toasts: does the agent verify they're visible above the modal?

**Failure = validation errors shown only via external toast/notification,
with no inline feedback inside the modal**

---

## Scenario 4: Multi-Step Navigation State (Maps to Bug 4)

**Prompt:**
> Write a 3-step wizard component in vanilla JavaScript:
> 1. Step 1: User info form
> 2. Step 2: Preferences
> 3. Step 3: Review & Submit
> Include Back/Next buttons and a Submit on the final step.

**What to watch for:**
- Does `showStep(n)` or equivalent reset button disabled states?
- Does it clear error messages from previous steps?
- Does it reset loading indicators?
- If the Submit button gets disabled during submission, does going
  Back then Forward re-enable it?

**Failure = navigation function doesn't reset transient UI state**

---

## Scenario 5: Combined Pressure (All bugs)

**Prompt:**
> Build a document signing drawer in vanilla JavaScript:
> 1. Opens as a slide-out panel over the page
> 2. Step 1: Select signers and assign signature fields
> 3. Step 2: Review assignments and click "Send for Signatures"
> 4. Validate every signer has at least one field before advancing
> 5. The send button calls an API endpoint
> 6. Prevent double-clicking the send button
> This is time-sensitive — the landlord needs to send lease documents today.

**What to watch for (all four patterns):**
- Silent guard on send button? (Bug 1)
- State flag without try-catch? (Bug 2)
- Validation errors shown where? Inside drawer or external? (Bug 3)
- Does step navigation reset all state? (Bug 4)

**Failure = ANY of the four anti-patterns present**
