# $plan
<!-- Produced by: Phase 4b | Consumed by: Phases 4c, 4d, 5, 6 reviewers -->

## Schema

steps:
  - id: N
    description: string
    files: string[]       # exact paths to create/modify
    type: value_unit | shared_prerequisite | adr
    depends_on:
      - step: N
        type: data | build | knowledge
    test_requirements: string
    status: pending | complete

## Notes

- Populated after user approves plan in Phase 4b (post-advisor stress-test)
- Phase 4c verifies file paths and function references against codebase
- Phase 5 dispatches based on dependency types: data/build = sequential, knowledge = parallelizable
- Phase 6 reviewers receive only step id + files list (not full descriptions) for payload slimming
- status updated during Phase 5 as steps complete
