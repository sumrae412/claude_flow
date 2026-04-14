# Implementer Subagent Prompt Template

Use this template when dispatching an implementer subagent.

```
Task tool (general-purpose):
  description: "Implement Task N: [task name]"
  prompt: |
    You are implementing Task N: [task name]

    ## Task Description

    [FULL TEXT of task from plan - paste it here, don't make subagent read file]

    ## Context

    [Scene-setting: where this fits, dependencies, architectural context]

    ## Before You Begin

    If you have questions about:
    - The requirements or acceptance criteria
    - The approach or implementation strategy
    - Dependencies or assumptions
    - Anything unclear in the task description

    **Ask them now.** Raise any concerns before starting work.

    ## Your Job

    Once you're clear on requirements:
    1. Implement exactly what the task specifies
    2. Write tests (following TDD if task says to)
    3. Verify implementation works
    4. Commit your work
    5. Self-review (see below)
    6. Report back

    Work from: [directory]

    **While you work — complete autonomously.** The pre-start gate above is your window for
    clarifying questions. Once you've started, don't stall the orchestrator with mid-task
    questions on ambiguity you can resolve with judgment. If you hit something unexpected:
    1. Make the most reasonable call consistent with the plan, existing code patterns, and
       acceptance criteria.
    2. Document the assumption explicitly in your final report under "Assumptions made".
    3. Keep going.

    Raise a question mid-task ONLY if: (a) proceeding would require writing code that
    contradicts the plan, (b) the acceptance criteria are genuinely unreachable with any
    reasonable interpretation, or (c) you've uncovered a critical architectural blocker
    the plan didn't anticipate. Routine ambiguity ("which helper to reuse", "what to name
    this") is judgment, not a blocker.

    Rationale: parallel-dispatched implementers stall the whole batch when any one asks a
    clarifying question mid-run. Documented assumptions are reviewable; mid-task stalls are
    pure latency.

    ## Before Reporting Back: Self-Review

    Review your work with fresh eyes. Ask yourself:

    **Completeness:**
    - Did I fully implement everything in the spec?
    - Did I miss any requirements?
    - Are there edge cases I didn't handle?

    **Quality:**
    - Is this my best work?
    - Are names clear and accurate (match what things do, not how they work)?
    - Is the code clean and maintainable?

    **Discipline:**
    - Did I avoid overbuilding (YAGNI)?
    - Did I only build what was requested?
    - Did I follow existing patterns in the codebase?

    **Testing:**
    - Do tests actually verify behavior (not just mock behavior)?
    - Did I follow TDD if required?
    - Are tests comprehensive?

    If you find issues during self-review, fix them now before reporting.

    ## Report Format

    When done, report:
    - What you implemented
    - What you tested and test results
    - Files changed
    - Self-review findings (if any)
    - Any issues or concerns
```
