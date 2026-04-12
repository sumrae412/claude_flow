---
name: production-readiness-check
description: Infrastructure and ops-level production readiness checker. Runs as a Phase 6 parallel reviewer — checks authentication config, data protection, and monitoring. Hybrid trigger — minimal core always runs, full category deep-dives when file patterns match the diff. Use when shipping to production or when user invokes /production-readiness.
user-invocable: true
---

# Production Readiness Check

Checks infrastructure and ops-level production readiness that code-level security review (OWASP, injection, XSS) does not cover. Runs as a parallel reviewer in Phase 6 alongside the code reviewer, silent failure hunter, security reviewer, and test coverage analyzer.

> Running production readiness check — scanning for auth, data protection, and monitoring gaps.

## When to Use

- **Automatically** — dispatched as a Phase 6 parallel reviewer during the code-creation-workflow
- **Manually** — invoke `/production-readiness` for a full standalone audit before shipping to production

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

### Step 3: Match Deep-Dive Triggers

Compare changed file paths against these patterns. If any match, run the corresponding expanded section.

| File Pattern | Expanded Section |
|---|---|
| `auth/`, `login`, `session`, `jwt`, `token`, `password`, `oauth`, `middleware/auth` | Authentication |
| `models/`, `migrations/`, `schema`, `encrypt`, `pii`, `personal`, `backup`, `gdpr` | Data Protection |
| `logging`, `monitor`, `alert`, `metric`, `sentry`, `datadog`, `grafana`, `prometheus` | Monitoring |

If no patterns match, skip the deep-dives and proceed to reporting.

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

## Step 5: Report Findings

Present findings in a table matching the format used by other Phase 6 reviewers. Only report items with score >= 60 or status UNCONFIRMED. Omit PASS items unless they provide useful context.

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
