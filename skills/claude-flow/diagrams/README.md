# claude-flow Diagrams

Mermaid-rendered architecture references for claude-flow. **Lazy-loaded** — not resident in the router.

## When to load

Load a diagram via the Read tool when you need to reason about workflow structure:

| Diagram | Load when |
|---------|-----------|
| `triage-paths.mmd` | Choosing between fast/lite/clone/plan/explore/full/bug-fix/audit paths in Phase 1 |
| `phase-lifecycle.mmd` | Explaining load-on-demand/drop behavior to users or debugging context bloat |
| `contract-flow.mmd` | Tracing how `$exploration` → `$requirements` → `$plan` → `$diff` → `$assessment` move between phases |

## Why Mermaid

Prose descriptions of flows drift from the code that enforces them. A diagram is dense (flowchart nodes + edges compress to a few hundred tokens), visually parseable in any Markdown renderer, and diffable in git. Inspired by the "documentation as AI-consumable context" pattern — optimize for model parsing, not human narrative.

## How to render

- GitHub renders Mermaid natively in `.md` files (the `.mmd` source is also parseable; just paste into any Mermaid live-editor)
- Claude reads the raw source directly via Read tool
- To render locally: `npx -y @mermaid-js/mermaid-cli -i triage-paths.mmd -o triage-paths.svg`

## Source of truth

These diagrams reflect the behavior encoded in:
- `SKILL.md` (Path Decision section)
- `phases/phase-1-discovery.md`
- `contracts/*.schema.md`

When any of those change, update the matching diagram in the same PR. Out-of-sync diagrams are worse than no diagrams.
