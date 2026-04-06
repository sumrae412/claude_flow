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
| Skipping symbolic verification "to save time" | Verification catches constraint violations before they compound; skipping saves seconds but costs rework in Phase 6. Always run at least hard checks |
| Embedding everything into RAG vector store | Only embed experiential data (findings, failed approaches, discoveries, review patterns). Embedding raw code or config bloats the store and degrades retrieval quality |
| Running controlled skip experiments on HIGH value agents | Controlled skips are only for MODERATE and LOW value agents. Skipping HIGH value agents risks session quality for minimal learning signal |
| Enabling federation push without explicit user opt-in | Federation is off by default. Never auto-enable. User must set `federation.enabled: true` and `federation.push: true` in config |
| Ignoring constraint violations because tests pass | Tests verify behavior; constraints verify conventions and safety rules. A passing test with a bare `except Exception:` is still a constraint violation that must be fixed |
| Building skill/workflow improvements into the active project repo | Confirm target repo in Phase 0. Skill work goes to claude_flow, not the open project |
| Deferring registry/telemetry setup "until there's enough data" | You cannot accumulate data without collection running. Start recording from session 1 with uniform priors (alpha=1, beta=1) |
| Hardcoding model IDs without verification | Model IDs change across versions (e.g., `claude-sonnet-4-5-20250514` does not exist; correct is `claude-sonnet-4-20250514`). When generating code that references model IDs, verify the exact string against the API or docs first |
