# Common Mistakes

| Mistake | Fix |
|---------|-----|
| Skipping Phase 0 context loading | Always load project context first |
| Exploring sequentially | Use parallel explorer subagents |
| Coding before clarification | Phase 3 is a hard gate — resolve ambiguities first |
| Single architecture for non-trivial tasks | Present 2 options (simplicity vs separation) |
| Writing tests after code | TDD — test first, then implement |
| Not finishing the branch | Always run Phase 6 to completion |
| Spinning 7 subagents for a small change | Scale agent count to complexity — fast-path and small tasks need 0-1 agents |
| Manufacturing clarification questions | Skip clarification entirely if the request is well-specified |
| Auto-shipping without user review | Always confirm before invoking `/ship` |
| Using claude-flow for bug fixes | Bug reports, regressions, and error investigations route to `/bug-fix` via Phase 1 Discovery Bug Path |
