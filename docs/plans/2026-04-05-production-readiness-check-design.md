# Design: Production Readiness Check Skill

**Created:** 2026-04-05 | **Status:** approved

## Problem

claude-flow's Phase 6 review catches code-level security issues (OWASP, injection, XSS, broken auth patterns) but has no gate for infrastructure/ops-level production readiness — MFA, encryption at rest, backup recovery, anomaly detection, incident response plans. These are different layers that require different checking strategies.

## Approach

**Standalone skill** (`skills/production-readiness-check/SKILL.md`) invoked as a 5th parallel reviewer in Phase 6 of `code-creation-workflow`. Hybrid triggering: minimal core checks always run, full category deep-dives expand when file patterns in the diff match.

### Why standalone (not extending security-reviewer)

- Clean separation: code-level OWASP vs infra-level ops
- Can evolve independently
- Can also be invoked manually (`/production-readiness`)
- Doesn't bloat the security reviewer's prompt

## Trigger System

### Minimal Core (Always Runs)

1. **Secrets in code** — hardcoded keys, passwords, tokens, API secrets
2. **HTTPS/TLS enforcement** — `http://` URLs in code, missing HSTS, missing redirects
3. **Security event logging** — new endpoints or auth flows without audit log calls

### Deep-Dive Triggers (File-Pattern Match)

| Diff matches | Expands into |
|---|---|
| `auth/`, `login`, `session`, `jwt`, `token`, `password`, `oauth` | Full Authentication section |
| `models/`, `migrations/`, `schema`, `encrypt`, `pii`, `personal`, `backup` | Full Data Protection section |
| `logging`, `monitor`, `alert`, `metric`, `sentry`, `datadog`, `grafana` | Full Monitoring section |

## Checklist Items

Each item is either **code-checkable** (automated grep/analysis) or **infra-confirmable** (ask user, generate IaC if missing).

### Authentication

| Item | Type | Action |
|---|---|---|
| MFA enabled | Infra-confirm | Ask user; generate IaC snippet (AWS Cognito, Auth0, etc.) |
| Strong password policy | Code-check | Grep for password validation — min length, complexity |
| Session management | Code-check | Check session config — `max_age`, `same_site`, `https_only`, rotation |
| JWT properly secured | Code-check | Check algorithm pinning, expiry, secret from env, no `none` alg |

### Data Protection

| Item | Type | Action |
|---|---|---|
| Encryption at rest | Infra-confirm | Ask user; generate Terraform/CDK for RDS/S3 encryption |
| TLS/HTTPS for all endpoints | Code-check | Grep for `http://` URLs, missing HSTS, redirect config |
| PII anonymization | Code-check | Check for PII fields in logs, API responses, error messages |
| Backup & recovery tested | Infra-confirm | Ask user; generate IaC for backup schedule + recovery runbook stub |

### Monitoring

| Item | Type | Action |
|---|---|---|
| Security event logging | Code-check | Check new endpoints/auth flows have audit log calls |
| Anomaly detection | Infra-confirm | Ask user; generate CloudWatch/Datadog alert config |
| Incident response plan | Infra-confirm | Check for `docs/incident-response.md`; create stub if missing |
| Security audits scheduled | Infra-confirm | Ask user; create `docs/security-audit-schedule.md` stub if missing |

## Flow Within Phase 6

```
Phase 6 launches parallel reviewers:
├── Code Reviewer
├── Silent Failure Hunter
├── Security Reviewer (OWASP/code-level)
├── Test Coverage Analyzer
└── Production Readiness Check (NEW)
        │
        ├── Run minimal core (always)
        ├── Match diff against trigger patterns
        ├── Expand matching sections
        ├── Code-check items: grep/analyze, report pass/fail
        ├── Infra-confirm items: ask user, note gaps
        │
        ▼
    Findings report
        │
        ▼
    Present fix plan to user → await approval → iterate
```

## Fix Iteration Protocol

1. **Report** — Present all findings in scored table format (consistent with existing reviewers)
2. **Plan** — Propose fix plan: code changes + IaC snippets + manual confirmations
3. **Confirm** — User approves plan before any changes are applied
4. **Fix** — Apply code fixes, generate IaC files, create doc stubs
5. **Verify** — Re-run affected checks to confirm fixes resolved the issues

### Output Format

```markdown
### Production Readiness Check

**Triggered sections:** Authentication, Monitoring

| # | Item | Status | Score | Action |
|---|------|--------|-------|--------|
| 1 | JWT secret from env | PASS | — | — |
| 2 | Session https_only | FAIL | 75 | Fix: set `https_only: True` in session config |
| 3 | MFA enabled | UNCONFIRMED | — | User confirmation needed |
| 4 | Security event logging | FAIL | 80 | Fix: add audit log to endpoint |
| 5 | Anomaly detection | UNCONFIRMED | — | Generate CloudWatch alarm config? |

**Proposed fix plan:**
1. Set `https_only: True` in `app/config/session.py:14`
2. Add `logger.info(...)` to `app/routes/users.py:45`
3. Generate `terraform/modules/monitoring/alarms.tf`

Proceed with fixes?
```

## Wiring Changes

Add `production-readiness-check` to the Phase 6 reviewer table in `code-creation-workflow/SKILL.md`:
- Add row to reviewer dispatch table
- Add to the parallel launch block
- ~5 lines total

## Files to Create

1. `skills/production-readiness-check/SKILL.md` — Main skill with checklist, trigger patterns, fix templates, IaC snippet templates
2. Wiring edit to `skills/code-creation-workflow/SKILL.md` Phase 6

## Design Decisions

- **Hybrid triggering over always-all:** Avoids noise on irrelevant PRs while ensuring critical items (secrets, HTTPS, logging) never slip through
- **Confirm before fix:** User always approves the fix plan — no surprise IaC files or code changes
- **Scored findings:** Same 0-100 scoring as existing reviewers for consistency; only report ≥ 60
- **IaC snippets are templates:** Generated for common providers (AWS, GCP) but clearly marked as starting points, not production-ready configs
