# Phase 4d: Acceptance Test Skeleton Generation

<!-- Loaded: after Phase 4c (full path only) | Dropped: after skeletons written -->

<SKIP-CONDITION>
Skip for Fast path, Clone path, and Lite path. Only run on Full workflow where the plan has explicit acceptance criteria.
</SKIP-CONDITION>

Before Phase 5 TDD begins, generate test skeletons from the approved plan's acceptance criteria. This pre-seeds the Red phase of TDD — implementers start with a clear contract instead of writing tests from scratch.

---

## How It Works

```
1. Extract testable acceptance criteria from the approved plan:
   - Each plan step's "test requirements" section
   - Edge cases resolved in Phase 3 ($requirements)
   - Any "verify that X" statements in the plan

2. For each criterion, generate a skeleton:

   def test_<criterion_slug>():
       """AC: <acceptance criterion text from plan>"""
       # Phase 5 will implement this test
       raise NotImplementedError("Skeleton from Phase 4d — implement in Phase 5")

3. Group skeletons by the test file they belong to:
   - Match to existing test files when the plan modifies existing code
   - Create new test files when the plan creates new modules

4. Write skeleton files to the test directory
   - Use the project's existing test structure and naming conventions
   - Import the modules referenced in the plan (even if they don't exist yet)
```

---

## What Phase 5 Does With Skeletons

Phase 5 TDD treats each skeleton as a pre-seeded Red test:
1. **Fill in** the skeleton with concrete assertions (the Red test)
2. **Implement** to make it pass (Green)
3. **Refactor** as needed
4. **Delete** any skeleton that turns out to be redundant or incorrectly scoped

The skeletons are a starting point, not a constraint. Phase 5 can modify, split, or remove them as understanding deepens during implementation.

---

## Why Pre-Generate

- **Coverage contract:** The plan says "test X" — now there's an actual test stub enforcing that. Harder to accidentally skip.
- **Faster Red phase:** Writing the test function signature, docstring, and imports is mechanical work. Pre-generating it lets Phase 5 focus on the interesting part (what to assert).
- **Review signal:** Phase 6 reviewers can check whether every skeleton was either implemented or explicitly deleted with justification.
