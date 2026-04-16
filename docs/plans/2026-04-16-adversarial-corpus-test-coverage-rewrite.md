# Plan: Rewrite test-file calibration cases as production-code variants

**Status:** Drafted 2026-04-16. Pending execution after PR #39 merges.
**Estimated effort:** 1-2 hours. No LLM spend.
**Blast radius:** Local only — claude_flow corpus + tests. No production behavior change.

## Why

The first calibration dry run (PR #39, mean agreement 49.17%) surfaced a corpus-design issue: cases 16, 17, 18 are all *test-file* diffs (`tests/test_payment_service.py`, `tests/test_user_signup.py`, `tests/test_invariants.py`).

The adversarial-breaker persona doesn't know to score test files differently from production code, so it rates them on `input_validation`/`concurrency_safety`/etc. — criteria that don't apply the same way to test code. The result: 17%, 33%, 17% per-case agreement on cases 16-18, dragging the overall mean down.

Two ways to fix the corpus side of this:

1. **Drop the test cases entirely.** Reduces corpus to 17, falls below `sample_size: 20` declared in registry. Loses test_coverage_gaps coverage altogether.
2. **Rewrite as production-code variants.** Same target criterion (`test_coverage_gaps`) but the diff is production code with planted test gaps. Keeps corpus at 20, keeps coverage of all 6 criteria.

This plan does (2). Persona softening to handle test files differently is a separate concern — see `2026-04-16-adversarial-persona-softening.md`.

## Cases to replace

### case-16-mock-canned-data → case-16-untested-edge-branch

**Old:** Test file mocks Stripe, never exercises real failure paths.
**New idea:** Production function with a new error branch added but no corresponding test added in the same diff. The diff is a production file (`app/services/payment_service.py`), and the test_coverage_gap is "new branch shipped without test coverage."

```python
def charge_user(user_id: int, amount: int):
    user = db.query(User).get(user_id)
    if user.account_locked:  # NEW BRANCH — no test for locked-account path
        raise AccountLockedError(user_id)
    return stripe.Charge.create(amount=amount, customer=user.stripe_id)
```

Expected scores:
- `input_validation`: 6 (no negative amount check)
- `error_handling`: 5 (Stripe errors not caught)
- `concurrency_safety`: 7
- `data_consistency`: 7
- `failure_modes`: 5 (Stripe down → 500)
- `test_coverage_gaps`: 3 (new branch, no test)

### case-17-happy-path-only → case-17-feature-without-tests

**Old:** Test file with only happy-path assertion.
**New idea:** Production diff that adds a new feature (e.g. password reset flow) with NO accompanying test file changes. The diff is `app/routes/password_reset.py` only. No `tests/` files in the diff.

Expected scores:
- `input_validation`: 5 (token format unchecked)
- `error_handling`: 5 (DB errors ungraceful)
- `concurrency_safety`: 6 (single-use token but no atomic claim)
- `data_consistency`: 6
- `failure_modes`: 5
- `test_coverage_gaps`: 3 (zero tests for new endpoint)

### case-18-test-name-lies → case-18-untested-invariant-claim

**Old:** Test claims to verify invariant but body checks nothing about it.
**New idea:** Production code with a docstring claiming an invariant ("ensures Client and HouseholdMember stay in sync") but no test in the diff that exercises the invariant.

```python
def create_household_member(db, household_id: int, name: str, email: str) -> HouseholdMember:
    """Create a household member.

    Invariant: also creates corresponding Client record so the tenants
    listing query (which joins through Client) finds this member.
    """
    member = HouseholdMember(household_id=household_id, name=name, email=email)
    db.add(member)
    # NOTE: No Client.create() here, despite the docstring claim
    db.commit()
    return member
```

Expected scores:
- `input_validation`: 5 (no email format check)
- `error_handling`: 5 (no rollback)
- `concurrency_safety`: 7
- `data_consistency`: 2 (invariant claim is FALSE — Client not created)
- `failure_modes`: 5
- `test_coverage_gaps`: 3 (no test exercises the claimed invariant)

Note: this case has a low `data_consistency` score too because the planted bug touches both criteria.

## Steps

1. Write new diff.patch + expected.json for cases 16, 17, 18 (replace existing files).
2. Update `tests/fixtures/adversarial_breaker/calibration_corpus/README.md` to describe the corpus shape (still 20 cases, still 3-per-criterion + 2 clean — just no longer "tests of tests").
3. Run `pytest tests/test_calibrate_adversarial_breaker.py -v` — corpus integration test should still pass with the rewrites.
4. Optionally run `make calibrate-adversarial-dry` (~$0.20) to see if the production-code rewrites land closer to my human labels. **Skip if waiting on the persona-softening plan to land first** (cheaper to recalibrate once after both changes).
5. Open PR. Reference PR #39 in the body.

## Decision points

**Should this PR land before or after the persona-softening PR?**

- **Before:** Cleaner separation. Each PR has a single concern. Two calibration runs (~$0.40).
- **After (or bundled):** One calibration run. Riskier to review (two changes interleaved).

Recommendation: **before**, separate PRs. Corpus changes are self-contained; persona softening is the production-affecting change that deserves its own scrutiny.

## Verification

- 33 unit tests still pass.
- Manual review of new diff.patch + expected.json files for realism.
- Optional dry calibration run to confirm new cases score within the band the rewrite is aiming for.

## Out of scope

- Persona changes (separate plan).
- Calibration script changes (the script is correct; the inputs are what need adjustment).
- Lowering `score_threshold` or `min_agreement` in the registry — those are reviewer-design decisions, not corpus fixes.
