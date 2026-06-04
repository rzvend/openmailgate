# Docker Deployment

> **Alpha software.** Review Terraform/OpenTofu plans before applying. Backup your data.

## Prerequisites

- Docker and Docker Compose
- AWS account with SES, S3, and SQS
- Cloudflare account with DNS zone (optional for first-run)

## Quick Start

```bash
# Clone
git clone <repo-url> ses-s3-mailbox
cd ses-s3-mailbox

# Configure
cp .env.example .env
# Edit .env — fill in required values (see .env.example comments)

# Start
docker compose build
docker compose run --rm api python3 worker/migrate.py
docker compose run --rm api python3 scripts/bootstrap_admin.py
docker compose up -d
docker compose ps
```

Open `http://localhost:8000/dashboard` and log in with the **admin** credentials shown by the bootstrap step above.

## Initial Admin Bootstrap

On a fresh installation, `scripts/bootstrap_admin.py` creates an initial `admin` operator with a random password. The password is printed once in the terminal — save it immediately and change it from the dashboard.

The script is idempotent: if any active operator already exists, it does nothing.

```bash
# Manual re-run (Docker):
docker compose run --rm api python3 scripts/bootstrap_admin.py
```

## Setup Workflow

1. **Environment variables**: `/dashboard/setup` — check configured/missing vars
2. **Credentials**: `/dashboard/setup/credentials` — validate AWS/Cloudflare
3. **Infrastructure**: `/dashboard/setup/iac` — run Terraform/OpenTofu init/plan/apply
4. **Validation**: `/dashboard/setup/validate` — verify AWS, S3, SQS, SES, Cloudflare
5. **First mailbox**: `/dashboard/setup/first-mailbox` — create mailbox and get Thunderbird settings

## Services

| Service | Port (host) | Description |
|---|---|---|
| API | `127.0.0.1:8000` | Dashboard and JSON API |
| SMTP sender | `127.0.0.1:2525` | Local SMTP relay for Thunderbird |
| Dovecot | `127.0.0.1:143` | IMAP (alpha) |
| Worker SQS | — | Consumes SQS events from S3 |

## Day-to-day Commands

```bash
docker compose up -d                # start
docker compose down                 # stop
docker compose logs -f api          # view logs
docker compose restart api          # restart API
docker compose run --rm api python3 worker/migrate.py  # migrate
docker compose ps                   # status
```

## Thunderbird Settings

| Field | Value |
|---|---|
| IMAP Server | Host IP or `10.10.10.16` |
| IMAP Port | 143 (Dovecot on host) |
| IMAP Security | STARTTLS |
| Username | Full email address |
| SMTP Server | Host IP or `10.10.10.16` |
| SMTP Port | 2525 |
| SMTP Security | None |

## Limitations (alpha)

- **Dovecot** runs in Docker (alpha). IMAP binds to `127.0.0.1:143` by default. No TLS/STARTTLS.
- **IMAP user sync** uses `DOVECOT_USERS_FILE` path; no sudo needed in Docker mode.
- **Terraform/OpenTofu** automation is alpha. Review plans before applying.
- **Postfix/SMTP relay** is not containerized; the host runs `smtp_server.py` directly.
- **No HTTPS/TLS termination** is provided. Use a reverse proxy (Caddy, Nginx) for production.

## Security

```
chmod 600 .env
# Never commit .env, data/, terraform state, or backups.
# Backup terraform state and database regularly.
# See docs/backup-restore.md.
# IaC setup issues? See docs/troubleshooting-iac.md.
```
