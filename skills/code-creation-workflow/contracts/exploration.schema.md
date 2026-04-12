# $exploration
<!-- Produced by: Phase 2 | Consumed by: Phases 3, 4, advisor prompts -->

## Schema

key_files:
  - path: string        # file path
    role: string        # 1-line role (e.g., "tenant CRUD service")

patterns:               # 3-5 discovered conventions
  - name: string
    example_file: string

integration_points:     # systems this feature touches
  - system: string
    interface: string   # function/endpoint name

concerns: string[]      # open questions for Phase 3

confidence: verified | inferred | assumed   # from research team if used

## Notes

- Populated by executor at end of Phase 2
- For full/complex path with research team: confidence scores come from synthesis
- Persists after phase-2-exploration.md is unloaded — this is the surviving artifact
- Target size: 100-200 tokens when populated
