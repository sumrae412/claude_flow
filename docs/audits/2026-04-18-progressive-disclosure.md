# Progressive Disclosure Audit — 2026-04-18

**Follow-up:** [Progressive Disclosure Audit — 2026-04-21](2026-04-21-progressive-disclosure.md) (re-run after refactors)

Scanned `/Users/summerrae/claude_code/claude-skills` (69 SKILL.md files, worktree snapshots excluded).

**Thresholds:**
- `critical` ≥ 800 lines — refactor now
- `high` ≥ 500 lines — refactor soon
- `candidate` ≥ 300 lines — consider splitting

## Refactor candidates (8)

| Severity | Lines | Skill | Path |
|----------|-------|-------|------|
| candidate | 494 | `production-readiness-check` | `/Users/summerrae/claude_code/claude-skills/production-readiness-check/SKILL.md` |
| candidate | 408 | `session-learnings` | `/Users/summerrae/claude_code/claude-skills/session-learnings/SKILL.md` |
| candidate | 388 | `user-stories` | `/Users/summerrae/claude_code/claude-skills/user-stories/SKILL.md` |
| candidate | 379 | `cleanup` | `/Users/summerrae/claude_code/claude-skills/cleanup/SKILL.md` |
| candidate | 350 | `research` | `/Users/summerrae/claude_code/claude-skills/research/SKILL.md` |
| candidate | 345 | `playwright-test` | `/Users/summerrae/claude_code/claude-skills/playwright-test/SKILL.md` |
| candidate | 313 | `debate-team` | `/Users/summerrae/claude_code/claude-skills/debate-team/SKILL.md` |
| candidate | 308 | `sc-marketing-scripts` | `/Users/summerrae/claude_code/claude-skills/sc-marketing-scripts/SKILL.md` |

## Already split (27)

`migration-architect`, `product-sprint`, `information-security-manager-iso27001`, `soc2-compliance`, `startup-planner`, `dependency-auditor`, `rag-architect`, `fda-consultant-specialist`, `coding-best-practices`, `synthetic-persona`, `gdpr-dsgvo-expert`, `patent-drafting`, `personal-coach`, `skill-security-auditor`, `claude-flow`, `jd-screener`, `resume-tailor`, `typography`, `defensive-backend-flows`, `design-audit`, `vanity-engineering-review`, `excalidraw-canvas`, `personas`, `defensive-ui-flows`, `excalidraw`, `skill-discovery`, `code-creation-workflow`

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
