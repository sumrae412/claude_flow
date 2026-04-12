# $requirements
<!-- Produced by: Phase 3 | Consumed by: Phases 4, 4c, 5, 6 reviewers -->

## Schema

stories:
  - role: string
    want: string
    benefit: string

acceptance_criteria:    # EARS format — these become the Phase 4c coverage checklist
  - id: AC-N
    when: string
    if: string          # optional condition
    then: string

scope:
  in: string[]          # explicitly included
  out: string[]         # explicitly excluded — enforced as scope-creep detection

edge_cases:
  - case: string
    resolution: string

nonfunctional:          # optional
  - type: string        # performance | backward_compat | security
    constraint: string

## Notes

- Populated after user approves requirements in Phase 3
- acceptance_criteria is the primary input for Phase 4c coverage mapping
- scope.out items are enforced in Phase 4c as scope-creep detection
- Phase 6 reviewers receive only acceptance_criteria (not full contract) for payload slimming
