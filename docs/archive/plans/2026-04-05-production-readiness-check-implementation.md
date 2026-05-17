# Production Readiness Check Skill — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a production readiness checker that runs as a 5th parallel reviewer in Phase 6, catching infra/ops security gaps (MFA, encryption at rest, backup, anomaly detection) that code-level review misses.

**Architecture:** Standalone skill at `skills/production-readiness-check/SKILL.md` with hybrid triggering (minimal core always, deep-dive on file-pattern match). Wired into `code-creation-workflow` Phase 6 as a parallel reviewer. IaC snippet templates inline in the skill.

**Tech Stack:** Markdown skill file, grep-based code checks, IaC templates (Terraform/CDK)

**Design doc:** `docs/plans/2026-04-05-production-readiness-check-design.md`

---

### Task 1: Create the Production Readiness Check Skill

**Files:**
- Create: `skills/production-readiness-check/SKILL.md`

**Step 1: Create the skill directory**

Run: `mkdir -p skills/production-readiness-check`

**Step 2: Write the skill file**

Create `skills/production-readiness-check/SKILL.md` with the following content:

```markdown
---
name: production-readiness-check
description: Infrastructure and ops-level production readiness checker. Runs as a Phase 6 parallel reviewer — checks authentication config, data protection, and monitoring. Hybrid trigger — minimal core always runs, full category deep-dives when file patterns match the diff. Use when shipping to production or when user invokes /production-readiness.
user-invocable: true
---

# Production Readiness Check

Checks infrastructure and ops-level production readiness that code-level security review (OWASP, injection, XSS) doesn't cover. Runs as a parallel reviewer in Phase 6 of code-creation-workflow.

**Announce:** "Running production readiness check — scanning for auth, data protection, and monitoring gaps."

## When to Use

- **Automatically:** Dispatched by Phase 6 of code-creation-workflow as a parallel reviewer
- **Manually:** User invokes `/production-readiness` for a full standalone audit

## Trigger System

### Step 1: Get the Diff

```bash
git diff origin/main...HEAD --name-only
```

### Step 2: Run Minimal Core (Always)

These three checks run on every ship cycle regardless of what files changed.

**1. Secrets in Code**

Grep the diff for hardcoded secrets:

```bash
git diff origin/main...HEAD -U0 | grep -iE '(api_key|api_secret|password|secret_key|private_key|token)\s*=\s*["\x27][^"\x27]{8,}'
```

Also check for:
- AWS keys: `AKIA[0-9A-Z]{16}`
- Generic tokens: strings matching `sk-`, `pk_live_`, `ghp_`, `glpat-`
- `.env` files committed (should be in `.gitignore`)

Score: 100 (always critical). Status: FAIL if any match found.

**2. HTTPS/TLS Enforcement**

Grep for insecure URLs and missing security headers:

```bash
git diff origin/main...HEAD -U0 | grep -iE 'http://' | grep -v 'localhost\|127\.0\.0\.1\|0\.0\.0\.0\|http://schemas\|http://www\.w3'
```

Check for HSTS header in middleware/config:

```bash
grep -riE 'Strict-Transport-Security|HSTS' --include='*.py' --include='*.js' --include='*.ts'
```

Score: 75 if `http://` URLs found pointing to non-local hosts. Score: 60 if HSTS not configured.

**3. Security Event Logging**

For each new endpoint or auth-related function in the diff, check that it includes a logging call:

```bash
# Find new route/endpoint definitions
git diff origin/main...HEAD | grep -E '^\+.*@(router|app)\.(get|post|put|patch|delete)'
```

Cross-reference against logging calls in the same file. Score: 80 if new endpoints lack audit logging.

### Step 3: Match Deep-Dive Triggers

Check the diff file list against these patterns. Expand matching sections only.

| Pattern (in changed file paths or content) | Expands |
|---|---|
| `auth/`, `login`, `session`, `jwt`, `token`, `password`, `oauth`, `middleware/auth` | → Authentication deep-dive |
| `models/`, `migrations/`, `schema`, `encrypt`, `pii`, `personal`, `backup`, `gdpr` | → Data Protection deep-dive |
| `logging`, `monitor`, `alert`, `metric`, `sentry`, `datadog`, `grafana`, `prometheus` | → Monitoring deep-dive |

If no patterns match, skip to Step 5 (Report).

### Step 4: Run Expanded Checks

#### Authentication Deep-Dive

| # | Item | Type | How to Check |
|---|------|------|-------------|
| A1 | MFA enabled | Infra-confirm | Ask user: "Is MFA enabled for all user-facing authentication?" If no, offer IaC snippet. |
| A2 | Strong password policy | Code-check | Grep for password validation. Look for min length (≥12), complexity checks (uppercase, number, special char). Check Pydantic validators, Django validators, or custom validation. Score: 75 if no policy found. |
| A3 | Session management | Code-check | Check session config for: `max_age` (≤3600), `same_site` (lax or strict), `https_only` (True), `httponly` (True). Score: 75 per missing attribute. |
| A4 | JWT properly secured | Code-check | Check for: algorithm pinning (not `none`), secret from env var (not hardcoded), expiry set (≤30 min for access tokens), token type validation. Score: 85 if algorithm allows `none`. Score: 100 if secret is hardcoded. |

#### Data Protection Deep-Dive

| # | Item | Type | How to Check |
|---|------|------|-------------|
| D1 | Encryption at rest | Infra-confirm | Ask user: "Is encryption at rest enabled for your database and object storage?" If no, offer IaC snippet. |
| D2 | TLS/HTTPS for all endpoints | Code-check | (Covered by minimal core check #2 — report combined.) |
| D3 | PII anonymization | Code-check | Grep for PII field names (`email`, `phone`, `ssn`, `address`, `date_of_birth`) in: log statements, error responses, API response models that don't use a filtered serializer. Score: 70 per PII field exposed in logs. Score: 80 per PII field in error responses. |
| D4 | Backup & recovery tested | Infra-confirm | Ask user: "Do you have automated backups with tested recovery?" If no, offer IaC snippet. |

#### Monitoring Deep-Dive

| # | Item | Type | How to Check |
|---|------|------|-------------|
| M1 | Security event logging | Code-check | (Covered by minimal core check #3 — report combined.) |
| M2 | Anomaly detection configured | Infra-confirm | Ask user: "Do you have anomaly detection / alerting configured for your production environment?" If no, offer IaC snippet. |
| M3 | Incident response plan | Infra-confirm | Check for `docs/incident-response.md` or similar. If missing, offer to create stub. |
| M4 | Security audits scheduled | Infra-confirm | Check for `docs/security-audit-schedule.md` or similar. If missing, offer to create stub. |

## Step 5: Report Findings

Present all findings in a single table, consistent with other Phase 6 reviewers:

```
### Production Readiness Check

**Triggered sections:** [list which sections ran]

| # | Item | Status | Score | Action |
|---|------|--------|-------|--------|
| 1 | ... | PASS/FAIL/UNCONFIRMED | score | action |

**Proposed fix plan:**
1. [code fix with file:line]
2. [IaC snippet to generate with target path]
3. [doc stub to create]

Proceed with fixes?
```

Statuses:
- **PASS** — Check passed, no action needed
- **FAIL** — Code-level issue found, score ≥ 60
- **UNCONFIRMED** — Infra item, needs user confirmation

**Only report items with score ≥ 60 or status UNCONFIRMED.** PASS items can be shown for context but don't need action.

## Step 6: Fix Iteration (After User Approval)

<HARD-GATE>
Do NOT apply any fixes until the user approves the fix plan.
</HARD-GATE>

1. **Code fixes** — Apply directly (e.g., add `https_only: True`, add logging call, add password validation)
2. **IaC snippets** — Generate to the appropriate directory (see templates below), clearly marked as starting points
3. **Doc stubs** — Create in `docs/` with starter templates
4. **Re-verify** — Re-run the checks that failed to confirm fixes resolved them

## IaC Snippet Templates

### MFA — AWS Cognito (Terraform)

Target path: `terraform/modules/auth/mfa.tf` (or user-specified)

```hcl
# MFA Configuration for AWS Cognito User Pool
# TEMPLATE — review and adapt to your environment before applying

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

Target path: `terraform/modules/database/encryption.tf`

```hcl
# RDS Encryption at Rest
# TEMPLATE — review and adapt to your environment before applying

resource "aws_db_instance" "main" {
  # ... existing config ...

  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn
}

resource "aws_kms_key" "rds" {
  description             = "KMS key for RDS encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
```

### Encryption at Rest — S3 (Terraform)

Target path: `terraform/modules/storage/encryption.tf`

```hcl
# S3 Default Encryption
# TEMPLATE — review and adapt to your environment before applying

resource "aws_s3_bucket_server_side_encryption_configuration" "main" {
  bucket = aws_s3_bucket.main.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
  }
}
```

### Automated Backups — RDS (Terraform)

Target path: `terraform/modules/database/backups.tf`

```hcl
# Automated Backup Configuration
# TEMPLATE — review and adapt to your environment before applying

resource "aws_db_instance" "main" {
  # ... existing config ...

  backup_retention_period = 30
  backup_window           = "03:00-04:00"
  copy_tags_to_snapshot   = true

  # Enable point-in-time recovery
  deletion_protection = true
}
```

### Anomaly Detection — CloudWatch (Terraform)

Target path: `terraform/modules/monitoring/alarms.tf`

```hcl
# CloudWatch Anomaly Detection Alarms
# TEMPLATE — review and adapt to your environment before applying

resource "aws_cloudwatch_metric_alarm" "high_error_rate" {
  alarm_name          = "${var.app_name}-high-error-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 2
  metric_name         = "5XXError"
  namespace           = "AWS/ApplicationELB"
  period              = 300
  statistic           = "Sum"
  threshold           = 10
  alarm_description   = "High 5XX error rate detected"
  alarm_actions       = [var.sns_topic_arn]
}

resource "aws_cloudwatch_metric_alarm" "unusual_login_failures" {
  alarm_name          = "${var.app_name}-unusual-login-failures"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "FailedLoginAttempts"
  namespace           = var.app_namespace
  period              = 300
  statistic           = "Sum"
  threshold           = 50
  alarm_description   = "Unusual number of failed login attempts"
  alarm_actions       = [var.sns_topic_arn]
}
```

### Incident Response Plan Stub

Target path: `docs/incident-response.md`

```markdown
# Incident Response Plan

**Last updated:** YYYY-MM-DD
**Owner:** [team/person]

## Severity Levels

| Level | Definition | Response Time | Example |
|-------|-----------|---------------|---------|
| SEV-1 | Service down, data breach | 15 min | Production database compromised |
| SEV-2 | Major feature broken | 1 hour | Authentication failing for all users |
| SEV-3 | Minor feature broken | 4 hours | Non-critical endpoint returning errors |
| SEV-4 | Cosmetic / low impact | Next business day | UI rendering issue |

## Response Procedure

1. **Detect** — Alert fires or user report received
2. **Triage** — Assign severity, identify responder
3. **Communicate** — Notify stakeholders per severity level
4. **Investigate** — Identify root cause
5. **Mitigate** — Apply fix or rollback
6. **Resolve** — Confirm service restored
7. **Postmortem** — Document within 48 hours (SEV-1/2 only)

## Contacts

| Role | Name | Contact |
|------|------|---------|
| Primary on-call | [TBD] | [TBD] |
| Engineering lead | [TBD] | [TBD] |
| Security lead | [TBD] | [TBD] |

## Runbooks

- [Service recovery](./runbooks/service-recovery.md)
- [Database rollback](./runbooks/database-rollback.md)
- [Security incident](./runbooks/security-incident.md)
```

### Security Audit Schedule Stub

Target path: `docs/security-audit-schedule.md`

```markdown
# Security Audit Schedule

**Last updated:** YYYY-MM-DD
**Owner:** [team/person]

## Recurring Audits

| Audit | Frequency | Last Run | Next Due | Tool/Method |
|-------|-----------|----------|----------|-------------|
| Dependency vulnerability scan | Weekly | [TBD] | [TBD] | `pip-audit` / `npm audit` |
| OWASP Top 10 review | Quarterly | [TBD] | [TBD] | Manual review + semgrep |
| Penetration test | Annually | [TBD] | [TBD] | External vendor |
| Access control audit | Quarterly | [TBD] | [TBD] | Manual review |
| Secrets rotation | Quarterly | [TBD] | [TBD] | Manual + vault policy |

## Ad-Hoc Triggers

Run a security review when:
- New authentication flow is added
- Third-party integration is added
- Database schema changes involving PII
- Infrastructure provider or region changes
```
```

**Step 3: Verify the file was created**

Run: `cat skills/production-readiness-check/SKILL.md | head -5`
Expected: The frontmatter header with `name: production-readiness-check`

**Step 4: Commit**

```bash
git add skills/production-readiness-check/SKILL.md
git commit -m "feat: add production-readiness-check skill"
```

---

### Task 2: Wire Into code-creation-workflow Phase 6

**Files:**
- Modify: `skills/code-creation-workflow/SKILL.md` (two locations: reviewer table and agents table)

**Step 1: Add to Phase 6 Tier 1 reviewer table**

In `skills/code-creation-workflow/SKILL.md`, find the Tier 1 table (around line 676):

```markdown
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | Test coverage gaps, missing edge cases, untested error paths |
```

Add this row immediately after:

```markdown
| Production Readiness | `general-purpose` | Auth config, data protection, monitoring, IaC gaps — uses `production-readiness-check` skill |
```

**Step 2: Add to the Agents Used table**

In `skills/code-creation-workflow/SKILL.md`, find the agents table (around line 896):

```markdown
| QA Edge-Case Reviewer | `pr-review-toolkit:pr-test-analyzer` | 6 | Always (overshoot prompts) | sonnet |
```

Add this row immediately after:

```markdown
| Production Readiness | `general-purpose` | 6 | Always (hybrid trigger) | sonnet |
```

**Step 3: Add to the Skills Invoked table**

Find the skills table (around line 919):

```markdown
| session-learnings | Phase 6 (capture discoveries) |
```

Add this row immediately after:

```markdown
| production-readiness-check | Phase 6 (production infra/ops review) |
```

**Step 4: Update the Phase 6 summary row**

Find the quick reference table (around line 881):

```markdown
| 6 | Quality + Finish | **sonnet/opus** | 5-tier review (overshoot technique) + random exploration + UX polish + de-slopification → verify → commit | **Verification** |
```

Change `5-tier` to `5-tier + production readiness`:

```markdown
| 6 | Quality + Finish | **sonnet/opus** | 5-tier + production readiness review (overshoot technique) + random exploration + UX polish + de-slopification → verify → commit | **Verification** |
```

**Step 5: Verify the changes**

Run: `grep -n "production-readiness" skills/code-creation-workflow/SKILL.md`
Expected: 4 matches (Tier 1 table, agents table, skills table, quick reference)

**Step 6: Commit**

```bash
git add skills/code-creation-workflow/SKILL.md
git commit -m "feat: wire production-readiness-check into Phase 6 review"
```

---

### Task 3: Verify End-to-End

**Step 1: Verify skill file structure**

Run: `ls -la skills/production-readiness-check/`
Expected: `SKILL.md` exists

**Step 2: Verify skill frontmatter**

Run: `head -6 skills/production-readiness-check/SKILL.md`
Expected: Valid frontmatter with `name`, `description`, `user-invocable: true`

**Step 3: Verify wiring — all 4 references exist**

Run: `grep -c "production-readiness" skills/code-creation-workflow/SKILL.md`
Expected: `4`

**Step 4: Verify no broken markdown tables**

Run: `grep -A1 "Production Readiness" skills/code-creation-workflow/SKILL.md`
Expected: Properly formatted table rows with `|` delimiters

**Step 5: Final commit (if any cleanup needed)**

If any fixes were needed, commit them:

```bash
git add -A
git commit -m "fix: cleanup production-readiness-check wiring"
```
