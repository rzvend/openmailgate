# OpenCode — Clean VM Installation Test Context

## Project

`ses-s3-mailbox` — self-hosted multi-mailbox email administration tool.

**Architecture (alpha):**

```
Receiving:  Amazon SES → S3/SQS → worker-sqs → Maildir → Dovecot Docker → Thunderbird
Sending:    Thunderbird → smtp-sender Python → Amazon SES
```

Postfix is **not** part of the alpha critical path.

## Recent Commits

```
c8403e0 Validate SMTP sender Docker setup
2772960 Add Dovecot Docker alpha
13d0089 Add first admin bootstrap
d5bec1f Prepare Docker alpha distribution
e33ddff Add first mailbox setup flow
0c07b62 Add setup infrastructure validation
f04c831 Add Terraform OpenTofu apply safeguards
0ae6433 Add Terraform OpenTofu init plan safeguards
9a94d03 Add setup credentials validation
7546e7d Add dashboard setup env validation
```

## Roadmap Status

**Completed:**
- E.2 — administrative write (mailboxes, IMAP passwords, operators, catch-all, archive)
- E.3a — operational diagnostics and docs
- E.3b — archive/audit mailboxes
- E.3c — S3 dry-run and lifecycle docs
- E.3d — S3 dry-run dashboard
- F.0 — Docker setup plan
- G.1 — minimal Docker base
- F.1a — setup page, env var status
- F.1b — AWS/Cloudflare credentials wizard
- F.1c-1 — Terraform/OpenTofu init/plan with safeguards
- F.1c-2 — Terraform/OpenTofu apply with confirmation
- F.1d — setup validation (AWS/S3/SQS/SES/Cloudflare)
- F.1e — first mailbox and Thunderbird instructions
- G.2 — Docker alpha distribution
- G.2.1 — admin bootstrap
- G.2.2 — Dovecot Docker alpha
- G.2.3 — SMTP sender Docker validation

**Current phase:** G.2.4 — Clean VM installation test and Level 1 near-self-service validation

**After:** v0.1.0-alpha publication

## What G.2.4 Must Validate

1. Create clean VM.
2. Install Docker, Docker Compose plugin, Git, curl, openssl.
3. Clone the repository.
4. Copy `.env.example` to `.env`.
5. Fill in minimum required `.env` variables.
6. Run `./install.sh`.
7. Run `docker compose config`.
8. Run `docker compose build`.
9. Run `docker compose up -d`.
10. Run migrations.
11. Run admin bootstrap.
12. Access dashboard.
13. Validate `/dashboard/setup`.
14. Validate AWS/Cloudflare credentials.
15. Run Terraform/OpenTofu init/plan/apply if applicable, with plan review and explicit confirmation.
16. Validate DNS/SES/S3/SQS.
17. Create first mailbox.
18. Sync IMAP users.
19. Validate Dovecot Docker.
20. Validate smtp-sender Docker.
21. Connect Thunderbird via IMAP.
22. Send via Thunderbird using smtp-sender SMTP.
23. Test real inbound.
24. Test real outbound.

## Minimum `.env` Variables

```
SESSION_SECRET=                 # openssl rand -hex 32

AWS_REGION=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=

CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ZONE_ID=

MAIL_DOMAIN=

S3_BUCKET=
SQS_QUEUE_URL=

SES_SMTP_USERNAME=
SES_SMTP_PASSWORD=

IMAP_BIND=127.0.0.1
IMAP_PORT=143

SMTP_BIND=127.0.0.1
SMTP_PORT=2525

DOVECOT_USERS_FILE=/app/dovecot/users
```

**Never commit `.env`.** Never paste secrets into logs, reports, or chat.
Generate `SESSION_SECRET` with: `openssl rand -hex 32`

## Expected Docker Services

```
api
worker-sqs
smtp-sender
dovecot
```

Postfix must **not** appear as an active service in the compose file.

## Expected Port Binds

| Port | Bind |
|---|---|
| API | 8000 |
| IMAP | **127.0.0.1**:143 |
| SMTP | **127.0.0.1**:2525 |

These defaults are **not** acceptable:
```
0.0.0.0:143
0.0.0.0:2525
143:143
2525:2525
```

For remote access, use tailnet, VPN, SSH tunnel, or other private network.

## Do Not Do This

- Do not add Postfix.
- Do not install Dovecot on the host as the primary solution.
- Do not expose IMAP/SMTP on `0.0.0.0` by default.
- Do not commit `.env`.
- Do not commit `terraform.tfstate`.
- Do not commit `*.tfplan`.
- Do not commit `mailbox.db`.
- Do not commit Maildir contents.
- Do not commit `.eml` files.
- Do not commit the real Dovecot `users` file.
- Do not paste secrets in reports.
- Do not run Terraform/OpenTofu apply without a prior plan and review.
- Do not run apply without the confirmation phrase: `I understand this will create/update cloud resources`
- Do not create a release or tag.
- Do not publish to public GitHub.
- Do not do large refactors outside the clean VM test scope.

## Allowed Fixes During G.2.4

- docker-compose adjustments
- .env.example adjustments
- install.sh adjustments
- Docker path adjustments
- Volume adjustments
- Healthcheck adjustments
- DOVECOT_USERS_FILE adjustments
- sync-imap-users in Docker adjustments
- Thunderbird instruction adjustments
- docs/deploy-docker.md updates
- docs/docker-base.md updates
- Small template fixes if instructions are wrong
- Tests for bugs found

**Not allowed:** Postfix, full public TLS, advanced RBAC, PostgreSQL, architecture rewrite, full production hardening.

## Useful Commands for Clean VM

```bash
git log --oneline -10
git status

cp .env.example .env
openssl rand -hex 32

./install.sh

docker compose config
docker compose build
docker compose up -d
docker compose ps

docker compose logs --tail=100 api
docker compose logs --tail=100 worker-sqs
docker compose logs --tail=100 smtp-sender
docker compose logs --tail=100 dovecot

docker compose run --rm api python3 worker/migrate.py
docker compose run --rm api python3 scripts/bootstrap_admin.py

docker compose run --rm api python3 -m worker.mailbox_admin sync-imap-users --apply
docker compose restart dovecot

ss -ltnp | grep ':143' || true
ss -ltnp | grep ':2525' || true

git status --short
find . -name ".env" -o -name "*.tfstate" -o -name "*.tfplan" -o -name "*.eml" -o -name "mailbox.db" -o -name "users"
```

## Security Greps

```bash
grep -R "AWS_SECRET_ACCESS_KEY=.*[A-Za-z0-9]\{10,\}" -n . \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ \
  --exclude='.env' 2>/dev/null || true

grep -R "CLOUDFLARE_API_TOKEN=.*[A-Za-z0-9]\{10,\}" -n . \
  --exclude-dir=.git --exclude-dir=.venv --exclude-dir=__pycache__ \
  --exclude='.env' 2>/dev/null || true

grep -R "0.0.0.0.*143\|0.0.0.0.*2525\|143:143\|2525:2525" -n \
  docker-compose.yml .env.example docs tests 2>/dev/null || true

grep -R "postfix" -n docker-compose.yml Dockerfile docker docs tests 2>/dev/null || true
```

Acceptable: Postfix mentioned only in docs as future/optional; `0.0.0.0` only in docs with explicit warnings. Variable names may appear; real values must not.

## Acceptance Criteria for G.2.4

- [ ] Clean VM can clone the project.
- [ ] `.env` created from `.env.example`.
- [ ] `install.sh` works.
- [ ] `docker compose config` passes.
- [ ] `docker compose build` passes.
- [ ] `docker compose up -d` brings up services.
- [ ] Migrations work.
- [ ] Admin bootstrap works.
- [ ] Dashboard opens.
- [ ] Login works.
- [ ] `/dashboard/setup` opens.
- [ ] `/dashboard/setup/credentials` opens.
- [ ] `/dashboard/setup/iac` opens.
- [ ] `/dashboard/setup/validate` opens.
- [ ] `/dashboard/setup/first-mailbox` opens.
- [ ] First mailbox created.
- [ ] IMAP sync works.
- [ ] Dovecot Docker is up.
- [ ] Thunderbird connects via IMAP.
- [ ] smtp-sender Docker is up.
- [ ] Thunderbird sends via SMTP.
- [ ] Real inbound works.
- [ ] Real outbound works.
- [ ] Postfix was not needed.
- [ ] IMAP/SMTP not publicly exposed by default.
- [ ] No real secrets/artifacts committed.

## Clean VM Test Report Template

```markdown
# Clean VM Test Report

## VM
- Distro:
- Docker version:
- Docker Compose version:
- Commit tested:

## Setup
- .env created from .env.example: yes/no
- install.sh result:
- docker compose config:
- docker compose build:
- docker compose up:

## Services
- api:
- worker-sqs:
- smtp-sender:
- dovecot:

## Dashboard
- login:
- /dashboard/status:
- /dashboard/setup:
- /dashboard/setup/credentials:
- /dashboard/setup/iac:
- /dashboard/setup/validate:
- /dashboard/setup/first-mailbox:

## Mailbox
- first mailbox created:
- IMAP sync:
- Dovecot users file:

## Thunderbird
- IMAP:
- SMTP:

## Real Email Tests
- inbound:
- outbound:

## Security Checks
- .env not committed:
- tfstate/tfplan not committed:
- mailbox.db/Maildir/.eml not committed:
- IMAP bind:
- SMTP bind:
- Postfix absent from active compose:

## Problems Found
- ...

## Fixes Applied
- ...

## Final Status
- APTO PARA PUBLICAÇÃO ALPHA
- or NÃO APTO, with blockers
```
