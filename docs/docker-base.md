# Docker Base Setup (G.1)

This is the initial Docker Compose setup for `ses-s3-mailbox`. It containerizes the three core Python services: API/dashboard, SQS worker, and SMTP sender.

> Dovecot and Postfix are **not** included as running containers in this version. They are planned for G.2. See `docker/dovecot/` and `docker/postfix/` for planned configuration.

## Quick Start

```bash
# 1. Configure environment
cp .env.example .env
# Edit .env — fill in required values (AWS keys, Cloudflare token, domain, etc.)

# 2. Build
docker compose build

# 3. Run migrations
docker compose run --rm api python3 worker/migrate.py

# 4. Start services
docker compose up -d

# 5. Verify
docker compose ps
docker compose logs -f api
curl http://localhost:8000/health
```

## Services

| Service | Port | Command |
|---|---|---|
| `api` | 8000 | `python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000` |
| `worker-sqs` | — | `python3 -m worker.sqs_worker` |
| `smtp-sender` | 2525 | `python3 -m sender.smtp_server` |

## Volumes

| Volume | Path | Purpose |
|---|---|---|
| `app_data` | `/app/data` | SQLite database, Maildir, raw emails |
| `app_logs` | `/app/logs` | Application logs |
| `iac_state` | `/app/state/iac` | Terraform/OpenTofu state (future) |
| `iac_setup_logs` | `/app/logs/setup` | Setup logs (future) |

## Useful Commands

```bash
# View logs
docker compose logs -f api
docker compose logs -f worker-sqs
docker compose logs -f smtp-sender

# Run migration
docker compose run --rm api python3 worker/migrate.py

# Run tests
docker compose run --rm api python3 -m pytest tests/ -q

# IMAP sync (manual — depends on host Dovecot)
# Not yet automated inside Docker. Run on host:
sudo python3 -m worker.mailbox_admin sync-imap-users --apply

# Stop
docker compose down

# Restart a single service
docker compose restart api
```

## Known Limitations (G.1)

- **Dovecot** is not containerized. The host must have Dovecot installed and configured to serve IMAP from the `MAILDIR_ROOT` volume.
- **Postfix / SMTP local relay** is not containerized. The host runs the SMTP sender directly or uses an external relay.
- **IMAP user sync** (`sync-imap-users --apply`) still needs to run on the host with sudo to write `/etc/dovecot/users`.
- **Setup wizard** (`/setup`, first-run) is not yet implemented (planned for F.1).
- **Terraform/OpenTofu** integration is not yet implemented (planned for F.1).

## Next Steps

- F.1: First-run setup wizard, environment validation, Terraform/OpenTofu integration
- G.2: Dovecot/Postfix containers, refined compose, healthchecks, backup/restore, installer, distribution
