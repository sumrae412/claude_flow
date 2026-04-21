# Progressive Disclosure Audit — 2026-04-21

Scanned `/Users/summerrae/.claude/skills` (69 SKILL.md files, worktree snapshots excluded).

**Thresholds:**
- `critical` ≥ 800 lines — refactor now
- `high` ≥ 500 lines — refactor soon
- `candidate` ≥ 300 lines — consider splitting

## Refactor candidates (0)

_None — all skills under the threshold or already split._

## Already split (34)

`migration-architect`, `product-sprint`, `information-security-manager-iso27001`, `soc2-compliance`, `startup-planner`, `dependency-auditor`, `rag-architect`, `fda-consultant-specialist`, `coding-best-practices`, `synthetic-persona`, `gdpr-dsgvo-expert`, `personal-coach`, `skill-security-auditor`, `claude-flow`, `jd-screener`, `resume-tailor`, `typography`, `defensive-backend-flows`, `design-audit`, `vanity-engineering-review`, `session-learnings`, `excalidraw-canvas`, `research`, `personas`, `debate-team`, `user-stories`, `defensive-ui-flows`, `cleanup`, `excalidraw`, `playwright-test`, `production-readiness-check`, `skill-discovery`, `sc-marketing-scripts`, `code-creation-workflow`

## Recommended split pattern

Extract phase/reference content into sibling files, leave a thin router:

```
skill-name/
  SKILL.md           # router (~150 lines / ~1K tokens)
  phases/            # phase-specific content, loaded on demand
  references/        # lookup tables, patterns, edge cases
```

Partition a monolithic SKILL.md without loading it into context:

```bash
sed -n 'M,Np' src/SKILL.md > references/patterns.md
```

See MEMORY entries `progressive_disclosure.md` and `token_efficiency_overhaul.md`.
