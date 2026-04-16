---
name: production-readiness-check
description: Pre-ship production readiness checker covering 27 items across SECURITY, DATABASE, DEPLOYMENT, and CODE categories. Runs as a Phase 6 parallel reviewer — minimal core always runs, deep-dive sections trigger on matching file patterns. Standalone invocation (`/production-readiness`) runs the full checklist including infra-confirm items not tied to code changes. Advisory mode — findings are reported; user decides what to fix before ship.
user-invocable: true
---

# Production Readiness Check

Checks infrastructure and ops-level production readiness that code-level security review (OWASP, injection, XSS) does not cover. Runs as a parallel reviewer in Phase 6 alongside the code reviewer, silent failure hunter, security reviewer, and test coverage analyzer.

> Running production readiness check — scanning for auth, data protection, and monitoring gaps.

**Registry wiring:** Registered in `reviewer-registry.json` as a Tier 2 `always` reviewer (id `production-readiness-check`, subagent_type `production-readiness-check`, model `sonnet`). Phase 6 cascade dispatches it automatically when Tier 1 finds HIGH+ issues. Standalone invocation via `/production-readiness` bypasses the cascade and runs every deep-dive regardless of file patterns.

## When to Use

- **Automatically** — dispatched as a Phase 6 parallel reviewer during the claude-flow
- **Manually** — invoke `/production-readiness` for a full standalone audit before shipping to production

## Check Types

Every check in this skill is classified by one of four types. Pick the right type when adding new checks — the wrong type either produces false-positive FAILs (grep-based over-confidence) or lets real issues slip through (missing confirmation gate).

- **code-check** — deterministic literal/structural match (e.g., hardcoded secret pattern, `http://` URL, missing migration file). Grep/glob is authoritative; no user confirmation needed before marking FAIL.
- **code-check (heuristic)** — grep pre-filter for a property that depends on enclosing scope or structure (e.g., "is this `await` inside a try/catch?", "does this component render both loading and error branches?"). Grep cannot verify scope — treat matches as **low-confidence** and confirm each flagged location with the user before marking FAIL.
- **user-judgment** — no automation; relies on the reviewer reading the diff and making a call (e.g., "are inputs validated server-side?").
- **infra-confirm** — ask the user whether an external infra/ops condition holds (e.g., "Is Sentry wired in production?", "Has backup restore been tested in the last 90 days?").

When adding a new check, ask: does correctness depend on enclosing block or sibling structure? If yes → heuristic + confirmation gate.

## Trigger System

### Step 1: Get the Diff

```bash
git diff origin/main...HEAD --name-only
```

Capture the list of changed files. This drives both the minimal core checks and the deep-dive trigger matching.

### Step 2: Run Minimal Core (Always)

These three checks run on every invocation regardless of which files changed.

#### C1: Secrets in Code

Grep the diff for hardcoded secrets:

```bash
# General credential assignments (catches custom keys, passwords, secrets)
git diff origin/main...HEAD -U0 | grep -iE "(api_key|api_secret|password|secret_key|private_key|token)\s*=\s*['\"][^'\"]{8,}"

# Known-format tokens (AWS, Stripe, GitHub, GitLab)
git diff origin/main...HEAD -U0 | grep -E 'AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9\-]{20,}|pk_live_|ghp_[a-zA-Z0-9]{36}|glpat-[a-zA-Z0-9\-]{20}'
```

Also check for committed `.env` files:

```bash
git diff origin/main...HEAD --name-only | grep -i '\.env'
```

Look for generic credential assignments (`API_KEY = "..."`, `password = "..."`) as well as known-format tokens: AWS access keys (`AKIA[0-9A-Z]{16}`), Stripe keys (`sk-`, `pk_live_`), GitHub tokens (`ghp_`), and GitLab tokens (`glpat-`).

- **Score: 100** — any match is a critical finding.

#### C2: HTTPS / TLS Enforcement

Grep changed files for plaintext HTTP URLs (excluding localhost, 127.0.0.1, XML schemas, and W3 references):

```bash
git diff origin/main...HEAD | grep -E 'http://' | grep -vE 'localhost|127\.0\.0\.1|schemas|w3\.org|example\.com'
```

Check for HSTS header configuration:

```bash
git diff origin/main...HEAD --name-only | xargs grep -l 'Strict-Transport-Security' /dev/null 2>/dev/null
```

If no matches in changed files, fall back to a project-wide check to confirm HSTS exists somewhere:

```bash
grep -riE 'Strict-Transport-Security' --include='*.py' --include='*.js' --include='*.ts' --include='*.yaml' --include='*.yml' 2>/dev/null
```

- **Score: 75** — plaintext `http://` URLs found in non-exempt contexts.
- **Score: 60** — no HSTS header configured anywhere in the project.

#### C3: Security Event Logging

Find new route or endpoint definitions in the diff and cross-reference against logging calls:

```bash
# Find new endpoints
git diff origin/main...HEAD | grep -E '^\+.*(\.route|\.get|\.post|\.put|\.patch|\.delete|@app\.|@router\.|app\.(use|all))\b'

# Cross-reference against logging in the same files
git diff origin/main...HEAD --name-only | xargs grep -lE '(logger\.|logging\.|console\.log|audit_log|log\.info|log\.warn|log\.error)' 2>/dev/null
```

- **Score: 80** — new endpoints found that lack audit logging in the same file.

#### C4: CI Workflow Companion Artifacts

Any workflow that runs a deterministic install (`npm ci`, `yarn install --frozen-lockfile`, `pnpm install --frozen-lockfile`, `poetry install --no-update`, `pip install -r *.lock`) must have the corresponding lock file committed in the working directory it targets. Workflows shipped without the lock file chronically fail every PR silently until someone traces the failure.

```bash
# For each workflow, find deterministic-install commands and verify lockfile sibling
for wf in .github/workflows/*.yml .github/workflows/*.yaml; do
  [ -f "$wf" ] || continue
  grep -qE 'npm ci|yarn install --frozen|pnpm install --frozen|poetry install --no-update|pip install -r [^ ]*\.lock' "$wf" || continue
  wd=$(grep -oE 'working-directory:\s*\S+' "$wf" | awk '{print $2}' | head -1)
  wd="${wd:-.}"
  found=0
  for lock in package-lock.json yarn.lock pnpm-lock.yaml poetry.lock; do
    [ -f "$wd/$lock" ] && found=1 && break
  done
  [ "$found" -eq 0 ] && echo "FAIL: $wf runs deterministic install in $wd but no lock file found"
done
```

- **Score: 90** — workflow invokes `npm ci` (or equivalent) but no lockfile is committed in the referenced `working-directory:`.
- Remediation: generate the lockfile (`npm install --package-lock-only --no-audit`, `poetry lock`, etc.), verify the workflow's install command passes in `--dry-run`, commit both together.

This is Core (not a deep-dive) because the trigger is narrow (`.github/workflows/*.yml` or lockfile-producing `package.json` / `pyproject.toml` in the diff) but very high-signal — every missed instance causes chronic PR failure until manually traced.

### Step 3: Match Deep-Dive Triggers

Compare changed file paths against these patterns. If any match, run the corresponding expanded section.

| File Pattern | Expanded Section |
|---|---|
| `auth/`, `login`, `session`, `jwt`, `token`, `password`, `oauth`, `middleware/auth` | Authentication |
| `models/`, `migrations/`, `schema`, `encrypt`, `pii`, `personal`, `backup`, `gdpr` | Data Protection |
| `logging`, `monitor`, `alert`, `metric`, `sentry`, `datadog`, `grafana`, `prometheus` | Monitoring |
| `routes/`, `api/`, `endpoints/`, `middleware/`, `cors`, `rate_limit`, `limiter` | Security Extended |
| `models/`, `migrations/`, `alembic/`, `schema`, `database`, `db/`, `*.sql` | Database |
| `Dockerfile`, `docker-compose`, `.env.example`, `railway.`, `terraform/`, `deploy/`, `pm2.`, `ecosystem.`, `.github/workflows/`, `systemd/` | Deployment |
| `**/*.js`, `**/*.ts`, `**/*.jsx`, `**/*.tsx`, `**/*.py`, `templates/`, `static/`, `package.json`, `uv.lock`, `poetry.lock` | Code Hygiene |

If no patterns match, skip the deep-dives and proceed to reporting.

**Standalone invocation (`/production-readiness`):** Run ALL deep-dive sections regardless of file patterns — this mode is for pre-ship audits where infra-confirm items (firewall, SSL cert, rollback plan) must be surfaced even when no related files changed.

### Step 4: Run Expanded Checks

Only run the sections triggered in Step 3.

#### Authentication Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| A1 | MFA Available | infra-confirm | Ask: "Is MFA enabled for user-facing auth (e.g., TOTP, WebAuthn)?" If unconfirmed, mark UNCONFIRMED and provide IaC snippet. |
| A2 | Password Policy | code-check | Grep for password length/complexity enforcement. Look for `minlength`, `MIN_PASSWORD_LENGTH`, `passwordStrength`, `zxcvbn`. **Score: 75** if no policy found. |
| A3 | Session Management | code-check | Check for `httpOnly`, `secure`, `sameSite` on cookies. Check session expiry / max-age configuration. **Score: 75** per missing attribute. |
| A4 | JWT Secured | code-check | Verify JWT algorithm is pinned (not `none`). Check secret is from env var. Check for expiry (`exp` claim). **Score: 100** for hardcoded secret, **Score: 85** for algorithm `none` allowed, **Score: 75** for missing `exp` claim. |

#### Data Protection Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| D1 | Encryption at Rest | infra-confirm | Ask: "Is encryption at rest enabled for databases and object stores?" If unconfirmed, mark UNCONFIRMED and provide IaC snippets (RDS + S3). |
| D2 | TLS in Transit | covered-by-core | Covered by C2 above. |
| D3 | PII Anonymization | code-check | Grep for PII field names (`email`, `phone`, `ssn`, `address`, `date_of_birth`) in logs, error messages, and API responses. **Score: 70** for PII in logs, **Score: 80** for PII in API error responses. |
| D4 | Backup & Recovery | infra-confirm | Ask: "Are automated backups configured with tested restore procedures?" If unconfirmed, mark UNCONFIRMED and provide IaC snippet. |

#### Monitoring Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| M1 | Security Logging | covered-by-core | Covered by C3 above. |
| M2 | Anomaly Detection | infra-confirm | Ask: "Are anomaly detection alerts configured (e.g., unusual login patterns, traffic spikes)?" If unconfirmed, mark UNCONFIRMED and provide IaC snippet. |
| M3 | Incident Response Plan | infra-confirm | Check for `docs/incident-response.md`. If missing, mark UNCONFIRMED and provide doc stub. |
| M4 | Security Audit Schedule | infra-confirm | Check for `docs/security-audit-schedule.md`. If missing, mark UNCONFIRMED and provide doc stub. |

#### Security Extended Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| S1 | Route auth audit | code-check | For every new route definition in the diff (`@app.route`, `@router.get\|post\|put\|patch\|delete`, `app.get\|post`, etc.), cross-reference against an auth decorator (`@login_required`, `@jwt_required`, `@require_auth`, `Depends(get_current_user)`, `authenticate`). **Score: 90** per unauthenticated route. Exempt routes explicitly tagged public (`/health`, `/metrics`, `/public/`, `@public`, `@health_check`). |
| S2 | CORS lockdown | code-check | Grep for CORS wildcards: `allow_origins=["*"]`, `Access-Control-Allow-Origin: *`, `origins=["*"]`, `cors(origin: '*')`. **Score: 85** per match — wildcard CORS is prod-unsafe. |
| S3 | Server-side input validation | user-judgment | Ask: "Are user-supplied inputs in changed endpoints validated server-side (schemas, length limits, type coercion)?" UNCONFIRMED if not inspected. Client-side validation is UX, not security. |
| S4 | Rate limiting on auth/sensitive endpoints | code-check | If auth routes (`/login`, `/register`, `/reset-password`, `/api/token`) exist in the diff, grep for rate-limit decorators or middleware (`@limiter.limit`, `slowapi`, `rate_limit`, `RateLimitMiddleware`, `express-rate-limit`). **Score: 75** if auth routes present without rate limiting. |
| S5 | Password hashing algorithm | code-check | If password storage code is touched, grep for strong hashes: `bcrypt`, `argon2`, `passlib`, `scrypt`. Flag weak hashes alone: `md5`, `sha1`, `sha256(password)`. **Score: 100** for weak-hash match on password fields, **Score: 70** if password storage touched without any strong hash import visible. |
| S6 | Logout session invalidation | code-check | For logout endpoints, grep for server-side revocation (`revoke`, `blacklist`, `delete_session`, `session.pop`, `token_blacklist`). **Score: 80** if logout only clears client cookie without server-side cleanup — stolen tokens remain valid. |

#### Database Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| DB1 | Backup restore tested | infra-confirm | Ask: "Has the backup restore procedure been tested end-to-end in the last 90 days?" UNCONFIRMED otherwise. Backups without restore tests are untrusted. |
| DB2 | Parameterized queries | code-check | Grep diff for SQL string concatenation: `execute(f"SELECT`, `execute(".* " + `, `query(f'`, `.format(...)` on SQL strings, `%s` fallback via `%` operator. **Score: 100** per match — injection risk. Use parameterized queries / ORM binds. |
| DB3 | Dev/prod DB separation | infra-confirm | Ask: "Are dev/staging and production databases distinct instances with separate credentials?" UNCONFIRMED if shared. |
| DB4 | Connection pooling configured | code-check | If DB engine configuration is touched, grep for pool settings: `pool_size=`, `QueuePool`, `max_overflow=`, `poolclass=`, external pooler (`PgBouncer`, `RDS Proxy`). **Score: 60** if DB engine configured without explicit pooling. |
| DB5 | Migrations in version control | code-check | If schema-shaped changes appear in diff (`models/`, `schema.sql`, `CREATE TABLE`, `ALTER TABLE`, column adds/drops), verify a corresponding migration file exists in `alembic/versions/`, `migrations/`, or equivalent. **Score: 85** per schema change without migration. No manual DB surgery. |
| DB6 | Non-root DB user | infra-confirm | Ask: "Does the application connect with a non-superuser DB account (limited to the schemas/tables it needs)?" UNCONFIRMED if unsure. Superuser connections magnify SQLi blast radius. |

#### Deployment Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| DP1 | Env vars declared for production | code-check | Grep changed code for `os.getenv`, `os.environ[`, `process.env.*`. Cross-reference each referenced env var against `.env.example` (or equivalent) in the repo. **Score: 70** per env var referenced in code but missing from `.env.example` — deployment-time footgun. |
| DP2 | SSL cert installed and valid | infra-confirm | Ask: "Is the production SSL certificate installed, valid, not expiring in <30 days, and covering all deployed hostnames?" UNCONFIRMED otherwise. |
| DP3 | Firewall (80/443 only public) | infra-confirm | Ask: "Does the production firewall expose only ports 80/443 publicly, with all other ports internal-only?" UNCONFIRMED otherwise. |
| DP4 | Process manager running | infra-confirm | Ask: "Is the app running under a process manager (systemd, PM2, Docker restart policies, Kubernetes) that auto-restarts on crash?" UNCONFIRMED otherwise. |
| DP5 | Rollback plan exists | code-check | Check for `docs/runbooks/rollback.md`, `docs/rollback.md`, `docs/runbooks/`, or equivalent rollback documentation in the repo. **Score: 60** if no rollback runbook exists — every prod system needs a known rollback path. |
| DP6 | Staging test passed | user-judgment | Ask: "Was this change deployed and smoke-tested on staging before production?" UNCONFIRMED if skipped. |

#### Code Hygiene Deep-Dive

| ID | Check | Type | Details |
|---|---|---|---|
| CD1 | No debug logging in prod build | code-check | Grep diff for leftover debug calls: `console.log(`, `console.debug(`, bare `print(` in non-test Python files, `debugger;` in JS. Exclude framework loggers (`logger.info`, `log.debug`, `structlog`). **Score: 60** per leftover debug call. |
| CD2 | Error handling on async operations | code-check (heuristic) | **Heuristic pre-filter** — grep diff for `await ` and `async def` / `async function`; for each hit, check whether the enclosing block contains `try`/`except`/`catch`. Grep cannot verify scope accurately, so treat matches as low-confidence and confirm each flagged location with the user before marking FAIL (e.g., "Function `<name>` contains `await` — is error handling present?"). **Score: 70** per confirmed unguarded await in non-test code. Unhandled promise rejections crash Node processes. |
| CD3 | UI loading and error states | code-check (heuristic) | **Heuristic pre-filter** — for each component/template that fetches data (contains `fetch(`, `axios`, `useQuery`, `useEffect.*fetch`, `{% ... %}` template calls), grep for loading/error branches (`isLoading`, `error`, `{#if error}`, `x-if=`, `{% if error %}`, `<ErrorBoundary>`). Grep cannot verify component structure, so flag matches as low-confidence and confirm with the user (e.g., "`<Component>` fetches data — does it render both loading and error states?"). **Score: 65** per confirmed component missing error or loading branch. |
| CD4 | Pagination on list endpoints | code-check | Grep new list endpoints (routes returning arrays/collections, e.g. `def list_`, `def get_all_`, `return items`, `return query.all()`) for pagination params (`limit`, `offset`, `page`, `cursor`, `page_size`). **Score: 70** per list endpoint without pagination — unbounded queries break under scale. |
| CD5 | Dependency vulnerability audit | code-check | If `package.json` / `package-lock.json` changed: run `npm audit --production --audit-level=high` and report unresolved critical/high issues. If `pyproject.toml` / `uv.lock` / `poetry.lock` changed: run `pip-audit` or `uv pip check`. **Score: 80** per unresolved critical vulnerability. |

## Step 5: Report Findings

**Enforcement mode: advisory.** All findings (FAIL + UNCONFIRMED) are reported to the user with suggested remediation. The user decides what to fix before ship vs. defer. This skill does not hard-block Phase 6 completion — the review-fix-recheck loop treats these findings like any other reviewer output.

Present findings in a table matching the format used by other Phase 6 reviewers. Only report items with score >= 60 or status UNCONFIRMED. Omit PASS items unless they provide useful context. Close with a Ship Readiness Summary so the user can make the final call.

**Output format:**

```markdown
### Production Readiness Check

**Triggered sections:** [list which sections ran, e.g. "Authentication, Monitoring (Data Protection skipped — no matching files)"]

| # | Item | Status | Score | Action |
|---|------|--------|-------|--------|
| 1 | JWT secret from env | PASS | — | — |
| 2 | Session https_only | FAIL | 75 | Fix: set `https_only: True` in session config |
| 3 | MFA enabled | UNCONFIRMED | — | User confirmation needed |
| 4 | Security event logging | FAIL | 80 | Fix: add audit log to new `/api/users` endpoint |
| 5 | Anomaly detection | UNCONFIRMED | — | Generate CloudWatch alarm config? |

**Proposed fix plan:**
1. Set `https_only: True` in `app/config/session.py:14`
2. Add `logger.info("user_action", extra={...})` to `app/routes/users.py:45`
3. Generate `terraform/modules/monitoring/alarms.tf` with anomaly detection config

### Ship Readiness Summary

- **Checks run:** <total items evaluated across triggered sections>
- **PASS:** <n> / **FAIL:** <n> / **UNCONFIRMED:** <n>
- **Critical (score 100):** <n>
- **High (score 75–99):** <n>
- **Medium (score 60–74):** <n>

> Advisory mode — any unresolved FAIL or UNCONFIRMED item is on you. "Can't check every box? You're not ready to ship" is a judgment call, not a hard gate.

Proceed with fixes?
```

Statuses:
- **PASS** — check passed, no action needed
- **FAIL** — code-level issue found, score >= 60
- **UNCONFIRMED** — infra item, needs user confirmation

## Step 6: Fix Iteration

**HARD-GATE: Do NOT apply any fixes until the user explicitly approves.** Present findings, wait for approval, then proceed.

After user approval, apply fixes in this order:

1. **Code fixes** — remove secrets, replace `http://` URLs, add logging, fix session/JWT config, mask PII
2. **IaC snippets** — generate Terraform or config files for infra-confirm items (see templates below)
3. **Doc stubs** — create missing documentation (incident response plan, audit schedule)
4. **Re-verify** — re-run the affected checks to confirm fixes resolved the findings

## IaC Snippet Templates

All templates below are starting points. Each is marked as a template that must be reviewed and adapted before applying.

### MFA — AWS Cognito (Terraform)

> **TEMPLATE — review and adapt before applying**

Target: `terraform/modules/auth/mfa.tf`

```hcl
resource "aws_cognito_user_pool" "main" {
  name = var.user_pool_name

  mfa_configuration = "ON"

  software_token_mfa_configuration {
    enabled = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }
}
```

### Encryption at Rest — AWS RDS (Terraform)

> **TEMPLATE — review and adapt before applying**

Target: `terraform/modules/database/encryption.tf`

```hcl
resource "aws_db_instance" "main" {
  storage_encrypted = true
  kms_key_id        = var.rds_kms_key_arn

  # ... other configuration
}

resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption at rest"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
```

### Encryption at Rest — S3 (Terraform)

> **TEMPLATE — review and adapt before applying**

Target: `terraform/modules/storage/encryption.tf`

```hcl
resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_kms_key" "s3" {
  description             = "KMS key for S3 encryption at rest"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
```

### Automated Backups — RDS (Terraform)

> **TEMPLATE — review and adapt before applying**

Target: `terraform/modules/database/backups.tf`

```hcl
resource "aws_db_instance" "main" {
  backup_retention_period = 30
  backup_window           = "03:00-04:00"
  copy_tags_to_snapshot   = true
  deletion_protection     = true

  # ... other configuration
}
```

### Anomaly Detection — CloudWatch (Terraform)

> **TEMPLATE — review and adapt before applying**

Target: `terraform/modules/monitoring/alarms.tf`

```hcl
resource "aws_cloudwatch_metric_alarm" "failed_login_spike" {
  alarm_name          = "${var.app_name}-failed-login-spike"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "FailedLoginAttempts"
  namespace           = var.app_name
  period              = 300
  statistic           = "Sum"
  threshold           = var.failed_login_threshold
  alarm_description   = "Alert on unusual number of failed login attempts"
  alarm_actions       = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "traffic_anomaly" {
  alarm_name          = "${var.app_name}-traffic-anomaly"
  comparison_operator = "GreaterThanUpperThreshold"
  evaluation_periods  = 3
  threshold_metric_id = "ad1"
  alarm_description   = "Alert on anomalous traffic patterns"

  metric_query {
    id          = "m1"
    metric {
      metric_name = "RequestCount"
      namespace   = "AWS/ApplicationELB"
      period      = 300
      stat        = "Sum"
    }
  }

  metric_query {
    id          = "ad1"
    expression  = "ANOMALY_DETECTION_BAND(m1, 2)"
    label       = "RequestCount (expected)"
    return_data = true
  }

  alarm_actions = [var.sns_topic_arn]
}
```

### Incident Response Plan Stub

> **TEMPLATE — review and adapt before applying**

Target: `docs/incident-response.md`

```markdown
# Incident Response Plan

## Severity Levels

| Level | Name | Description | Response Time | Examples |
|---|---|---|---|---|
| SEV-1 | Critical | Service fully down, data breach | 15 min | Production outage, credential leak |
| SEV-2 | Major | Significant degradation | 30 min | Major feature broken, partial outage |
| SEV-3 | Minor | Limited impact | 4 hours | Minor bug in production, single user affected |
| SEV-4 | Low | Minimal impact | 24 hours | Cosmetic issue, non-critical alert |

## Response Procedure

1. **Detect** — alert fires or report received
2. **Triage** — assess severity, assign incident commander
3. **Communicate** — notify stakeholders via #incidents channel
4. **Mitigate** — apply immediate fix or rollback
5. **Resolve** — confirm service restored, root cause identified
6. **Postmortem** — blameless review within 48 hours (SEV-1/2)

## Contacts

| Role | Name | Contact |
|---|---|---|
| Incident Commander | TBD | TBD |
| Engineering Lead | TBD | TBD |
| Communications | TBD | TBD |

## Runbooks

- [ ] Database failover: `docs/runbooks/db-failover.md`
- [ ] Rollback deployment: `docs/runbooks/rollback.md`
- [ ] Credential rotation: `docs/runbooks/credential-rotation.md`
```

### Security Audit Schedule Stub

> **TEMPLATE — review and adapt before applying**

Target: `docs/security-audit-schedule.md`

```markdown
# Security Audit Schedule

## Recurring Audits

| Audit | Frequency | Owner | Last Completed | Next Due |
|---|---|---|---|---|
| Dependency vulnerability scan | Weekly (automated) | CI/CD | TBD | TBD |
| OWASP Top 10 review | Quarterly | Security Lead | TBD | TBD |
| Infrastructure access review | Quarterly | Platform Team | TBD | TBD |
| Penetration test | Annually | External Vendor | TBD | TBD |
| SOC 2 / compliance audit | Annually | Compliance Team | TBD | TBD |

## Ad-Hoc Triggers

Run an unscheduled security review when any of these occur:

- Major infrastructure change (new cloud provider, region, service)
- Authentication or authorization system changes
- New third-party integration with data access
- Security incident or near-miss (post-incident action item)
- Significant codebase refactor affecting security boundaries
```

---

## Next Steps

- **Critical findings?** Fix them before shipping — each finding includes a specific remediation action.
- **All checks pass?** Use `/ship` to commit, push, create PR, run review, and merge to main.
- **Want a multi-model review too?** Use `/debate-team` for cross-model adversarial review before shipping.
