> **Historical document.** This file records an earlier planning/implementation phase and may not represent the current v0.1.0-alpha deployment flow. For current installation instructions, use `README.md` and `docs/deploy-docker.md`.

# Docker Deployment and First-run Setup Plan

## Overview

This document defines how `ses-s3-mailbox` will be deployed via Docker and how the first-run setup will work. Implementation happens in later phases:

| Phase | Purpose |
|---|---|
| **F.0** | This planning document |
| **G.1** | Docker Compose, `.env.example`, volumes, base containers |
| **F.1** | First-run screen, env var validation, AWS/Cloudflare wizard, Terraform/OpenTofu |
| **G.2** | Refined compose, healthchecks, backup/restore, installer, distribution |

> **Terraform/OpenTofu automation is alpha.** The plan must always be reviewed before apply. Manual commands are provided as fallback.

## Environment Variables

### App

```env
APP_NAME=SES S3 Mailbox
APP_VERSION=0.1.0-dev
SESSION_SECRET=          # required — generate with: openssl rand -hex 32
MAIL_DOMAIN=             # required — domain for sending/receiving email (e.g. inbox.example.com)
```

`SESSION_SECRET` must be set to a random value. Never commit it.

### Database and Paths

```env
DB_PATH=/app/data/mailbox.db           # SQLite, volume-persisted
MAILDIR_ROOT=/app/data/maildir         # Maildir root, volume-persisted
RAW_EMAIL_DIR=/app/data/raw-emails     # inbound raw storage
RAW_OUTBOUND_DIR=/app/data/raw-outbound # outbound raw storage
```

In Docker these paths map to named volumes or bind mounts.

### AWS

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=       # required
AWS_SECRET_ACCESS_KEY=   # required — never commit, never display
S3_BUCKET=              # required — S3 bucket for SES receiving
SQS_QUEUE_URL=           # required — SQS queue URL
S3_INCOMING_PREFIX=incoming/
S3_PROCESSED_PREFIX=processed/
S3_FAILED_PREFIX=failed/
```

Permissions required: `SES`, `S3`, `SQS` (see IAM checklist below).

### SMTP / SES Sending

```env
SES_SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SES_SMTP_PORT=587
SES_SMTP_USERNAME=       # required for outbound
SES_SMTP_PASSWORD=       # required — never commit
SES_SMTP_STARTTLS=true
LOCAL_SMTP_PORT=2525
```

### Cloudflare

```env
CLOUDFLARE_API_TOKEN=    # required — never commit
CLOUDFLARE_ZONE_ID=      # required
```

Permissions: DNS read, DNS edit, zone read.

### Terraform / OpenTofu

```env
IAC_TOOL=tofu            # terraform or tofu
IAC_WORKDIR=/app/iac           # mounted volume
IAC_STATE_DIR=/app/state/iac   # persistent volume
IAC_LOG_DIR=/app/logs/setup    # persistent volume
```

These are internal container paths. The state directory must be on a persistent volume — container recreation must not destroy the state.

### Setup

```env
SETUP_COMPLETED=false    # stored in settings table after first-run
```

### Support / About (future)

```env
APP_SUPPORT_URL=
APP_SUPPORT_LABEL=
```

Optional. Used in the About page (G.2).

---

## Planned `.env.example`

The `.env.example` file (created in G.1) will:

- Use placeholder values (e.g. `CHANGE_ME`)
- Group variables by section (App, AWS, Cloudflare, etc.)
- Mark required vs optional variables
- Include security comments
- Never contain real secrets

Example:

```env
# ── App ──────────────────────────────────────────────────────────────────
SESSION_SECRET=CHANGE_ME                   # required
MAIL_DOMAIN=example.com                    # required

# ── AWS ──────────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID=CHANGE_ME                # required
AWS_SECRET_ACCESS_KEY=CHANGE_ME            # required — protect this file
# ... more variables
```

---

## First-run Flow (F.1)

```
1. User clones the repository.
2. Copies .env.example to .env and fills in required values.
3. Runs docker compose up.
4. Opens the dashboard at the configured address.
5. If SETUP_COMPLETED is not set, the user is redirected to /setup.
6. The screen validates which env vars are present (shows configured/missing).
7. The user chooses:
   a. Use credentials from .env (recommended).
   b. Enter credentials temporarily in the wizard (not persisted to DB).
8. The app validates AWS connectivity.
9. The app validates Cloudflare connectivity.
10. The app runs Terraform/OpenTofu init.
11. The app runs Terraform/OpenTofu plan.
12. The app shows a plan summary.
13. The user reviews and clicks "I understand this will create/update cloud resources".
14. The app runs apply.
15. The app validates DNS records, SES identity, S3 bucket, SQS queue.
16. The app creates the first operator (admin).
17. The app creates the first mailbox and email address.
18. The app sets an IMAP password and runs IMAP sync.
19. The app displays Thunderbird settings.
20. The app marks SETUP_COMPLETED = true.
```

---

## Credentials Strategy

### Via `.env` (recommended)

- User sets values in `.env` before starting Docker.
- Dashboard reads them from the environment.
- Shows only `configured` / `missing` — never displays values.

### Via wizard (temporary)

- Accepts credentials during the first-run session.
- Does not persist to the database in this version.
- Does not write to `.env` automatically.
- Must not appear in logs or HTML after input.

If future versions need persistent credential storage, that requires a separate phase with encryption at rest, a master key, and rotation support.

---

## Terraform / OpenTofu Strategy

Support both `terraform` and `tofu` via the `IAC_TOOL` variable.

Planned flow:

```
init   → initialize working directory
plan   → generate execution plan
apply  → execute plan (only after plan review)
```

Safety rules:

- Never run apply without a prior plan.
- Show plan summary before apply.
- Require explicit confirmation: "I understand this will create/update cloud resources."
- Block concurrent plan/apply executions.
- Store state on a persistent volume.

---

## State Management

- State file lives in a persistent Docker volume (`IAC_STATE_DIR`).
- State is never committed to the repository.
- Backup and restore procedures are documented (G.2).
- Container recreation must not lose the state.

---

## Concurrent Execution Lock

Conceptual design:

- Before running plan or apply, check for an active job in the `settings` table (key: `setup_job_active`).
- If a job is active, block the new request.
- Mark the job as active during execution, clear on completion or error.
- Dashboard shows running/completed/failed status.

---

## Log Sanitization and Masking

All setup logs must:

- Be viewable in the dashboard.
- Be downloadable for review.
- Be sanitized before display.
- Mask `AWS_SECRET_ACCESS_KEY` → `***MASKED***`.
- Mask `CLOUDFLARE_API_TOKEN` → `***MASKED***`.
- Not print the full `.env` file.

---

## Manual Mode

For users who prefer running Terraform/OpenTofu manually, or when automation is unavailable, the dashboard will display equivalent commands:

```bash
cd /app/iac
$IAC_TOOL init
$IAC_TOOL plan
$IAC_TOOL apply

# Validate DNS
$IAC_TOOL output mx_record
$IAC_TOOL output spf_record
```

This mode is useful for:

- Troubleshooting automation failures.
- Teams with existing IaC workflows.
- Environments where the dashboard can't run external tools.

---

## AWS / Cloudflare / DNS / SES Checklist

The setup process will validate:

### AWS

- Credentials are valid (sts:GetCallerIdentity)
- Region is configured
- SES is available in the region
- Identity/domain exists or will be created
- S3 bucket exists
- SQS queue exists or notification is configured

### Cloudflare

- API token is valid
- Zone ID is valid
- DNS records can be read
- DNS records can be created/updated

### DNS

- MX record → inbound SMTP
- SPF record
- DKIM records (3 CNAMEs)
- DMARC record

### SES

- Domain identity verified
- DKIM enabled and verification succeeded
- Receiving rule set active
- S3 action configured (incoming prefix)
- SQS notification configured
- Sending authorized (out of sandbox or verified recipients)

### App

- First operator created
- First mailbox created with address
- IMAP password configured
- IMAP sync executed
- Thunderbird settings displayed

---

## First Mailbox Creation

The setup wizard reuses the existing mailbox creation logic:

1. Create a `master` mailbox (always present).
2. Create the user's first mailbox (e.g. `admin` or their chosen name).
3. Create the primary email address.
4. Set the IMAP password.
5. Run IMAP sync.
6. Optionally configure inbound/outbound archive.
7. Display Thunderbird settings:

   | Setting | Value |
   |---|---|
   | IMAP Server | Host IP |
   | IMAP Port | 143 |
   | Security | STARTTLS |
   | Username | Full email address |
   | Password | Password configured above |

---

## Setup Completed

After the first-run flow finishes:

- `settings.setup_completed` = `"true"`
- Dashboard no longer redirects to `/setup`.
- Future `/setup` page shows "Setup already completed" with a reset option (future feature).

---

## Next Phase: G.1

G.1 creates the base Docker Compose setup.

- `docker-compose.yml` with services: API, SQS worker, SMTP sender, Dovecot, Postfix
- `.env.example` file based on the variable map above
- Volume definitions for persistent data
- Volume for Terraform/OpenTofu state
- Volume for setup logs
- Migration execution strategy
