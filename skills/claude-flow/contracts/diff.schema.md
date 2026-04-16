# $diff
<!-- Produced by: Phase 5 | Consumed by: Phase 6 reviewers -->

## Schema

files_changed: string[]
insertions: number
deletions: number
git_diff: string          # full diff (unavoidable — reviewers need real content)
context_facts:            # Optional. Populated by Phase 5 Step 3e (mid-run extraction).
  - task: string          # Task identifier from $plan
    facts:                # Array of extracted facts (max 10 per task)
      - type: string      # SCHEMA | API | PATTERN | GOTCHA
        fact: string      # One-line reusable fact

## Notes

- Generated at end of Phase 5 via `git diff main --stat` + `git diff main`
- git_diff is the primary reviewer input — cannot be compressed
- files_changed used for conditional reviewer triggers (Tier 3 file_patterns matching)
- insertions + deletions used for code-simplifier skip condition (<100 lines = skip)
- context_facts is populated by Phase 5 Step 3e after each task; entries accumulate across tasks
- context_facts are consumed by: next-task executor (injected as "known context"), Phase 6 reviewers, and session-learnings (skips facts already captured)
- context_facts is OPTIONAL — absent or empty array is valid for documentation-only tasks or tasks with no novel discoveries
