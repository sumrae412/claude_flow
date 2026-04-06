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
| Dispatching Explorer B/C before Explorer A has written the scratchpad | Wait for scratchpad file to exist; never dispatch dependents on an assumed write |
| Skipping gap detection after architects deliver findings | Always run gap detection scan before synthesis; unchallenged blind spots compound downstream |
| Not recording registry events at dispatch and outcome points | Every dispatch and result must emit a registry event — effectiveness scoring depends on complete data |
| Ignoring agent signals during implementation | Signals (stuck, diverged, needs-context, complete) change orchestrator behavior; process them immediately |
| Running full complex-tier swarm on a moderate task | Calibrate tier before Phase 2; over-dispatching wastes budget and adds noise without improving output |
| Skipping the missed-context audit after exploration or review | Audits surface gaps that agents assumed away; skipping them silently degrades architecture and review quality |
