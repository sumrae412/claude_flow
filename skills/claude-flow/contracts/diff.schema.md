# $diff
<!-- Produced by: Phase 5 | Consumed by: Phase 6 reviewers -->

## Schema

files_changed: string[]
insertions: number
deletions: number
git_diff: string          # full diff (unavoidable — reviewers need real content)

## Notes

- Generated at end of Phase 5 via `git diff main --stat` + `git diff main`
- git_diff is the primary reviewer input — cannot be compressed
- files_changed used for conditional reviewer triggers (Tier 3 file_patterns matching)
- insertions + deletions used for code-simplifier skip condition (<100 lines = skip)
