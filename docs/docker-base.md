# Docker Base Setup (G.1)

This is the initial Docker Compose setup for `ses-s3-mailbox`. It containerizes the three core Python services: API/dashboard, SQS worker, and SMTP sender.

Dovecot is included as an alpha Docker service. Postfix is not included in the alpha path; outbound SMTP is handled by the built-in Python smtp-sender service.

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

# IMAP sync in Docker alpha
# Writes users to DOVECOT_USERS_FILE, usually /app/dovecot/users
docker compose run --rm api python3 -m worker.mailbox_admin sync-imap-users --apply

# Restart Dovecot after sync, if needed
docker compose restart dovecot

# Stop
docker compose down

# Restart a single service
docker compose restart api
```

## Known Limitations / Alpha Notes

- **Dovecot** is now available as an alpha Docker service. It is suitable for local, private-network, tailnet, or VPN testing, but is not yet a hardened public IMAP deployment.
- **Postfix** is not included in the alpha path. Outbound SMTP is handled by the built-in Python `smtp-sender` service.
- **IMAP user sync** should use `DOVECOT_USERS_FILE=/app/dovecot/users` in Docker mode. Host/systemd mode can still use `/etc/dovecot/users`.
- **Setup wizard** is available under `/dashboard/setup`.
- **Terraform/OpenTofu** init/plan/apply is available from the dashboard with safeguards and explicit confirmation.
- **SMTP sender** is exposed on `127.0.0.1:2525` by default for alpha safety. Use a tailnet/VPN/private network for remote clients.

## Next Steps

- G.2.4: Clean VM install test and Level 1 almost self-service validation.
- Public alpha: README, LICENSE, release notes, and final safety checklist.
- G.3: Optional Postfix / advanced MTA support after alpha.
