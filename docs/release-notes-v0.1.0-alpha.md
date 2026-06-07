# OpenMailGate v0.1.0-alpha Release Notes

## Summary

This is the **first alpha release** of OpenMailGate — free software for
self-hosted/hybrid email infrastructure using Amazon SES, S3, SQS, Dovecot,
and a FastAPI dashboard.

It delivers a functional Docker-based flow for receiving and sending email
with a custom domain, using AWS SES for transport and local Dovecot/Maildir
for storage and IMAP access.

**This is alpha software. It is not production-ready.**

## Who this alpha is for

- Technical users comfortable with Docker, AWS, and DNS
- Homelab and self-hosting enthusiasts
- Small-business evaluation
- Clean-install validation and early feedback
- Developers interested in contributing

## What is included

| Component | Description |
|---|---|
| API / dashboard | FastAPI web interface for setup, mailbox management, and IaC |
| Docker Compose | One-command stack: api, worker-sqs, smtp-sender, dovecot |
| worker-sqs | Long-polling SQS worker for inbound SES email |
| smtp-sender | Python SMTP server relaying outbound email via SES |
| Dovecot | IMAP server with passwd-file authentication |
| Maildir | Local email storage shared across containers |
| SQLite | Embedded database for mailboxes, messages, and operators |
| OpenTofu setup | Infrastructure-as-code for AWS and Cloudflare |
| First mailbox wizard | Guided creation of the first functional mailbox |
| Runtime env sync | Update .env from OpenTofu outputs |
| Post-apply validation | Read-only checks for all created resources |
| About / License | License, copyright, and attribution page |
| Branding / logo | OpenMailGate visual identity |

## Validated clean-install flow

The following flow was validated end-to-end in a clean VM (G.2.7):

```text
Docker Compose up
→ dashboard first-run admin creation
→ AWS/Cloudflare credential validation
→ IAM credentials preflight
→ OpenTofu init → plan → apply
→ post-apply infrastructure validation
→ runtime env sync from outputs
→ first mailbox creation via dashboard
→ Thunderbird IMAP/SMTP configuration
→ outbound email via SES with SPF, DKIM, and Custom MAIL FROM validation
→ Sent copy saved via IMAP APPEND
→ inbound reply via SES → S3 → SQS → worker-sqs
→ message delivered to Dovecot/Maildir
→ message visible in Thunderbird
```

## Important fixes included

- **SES Custom MAIL FROM timing** (ee557b1): The `aws_ses_domain_mail_from`
  resource now waits for SES domain identity propagation before configuring
  the custom MAIL FROM domain.

- **Maildir ownership for Dovecot** (f595f3d): Maildir root and intermediate
  folder ownership is normalized for Dovecot (UID 1000). This prevents
  "Permission denied" errors when Thunderbird saves copies to the Sent folder.

## Documentation

- `README.md` — Project overview and quick start
- `docs/deploy-docker.md` — Docker deployment guide
- `docs/security-alpha.md` — Alpha security checklist
- `docs/test-triage-alpha.md` — Pytest failure triage
- `docs/operations.md` — Operational commands
- `docs/backup-restore.md` — Backup and restore procedures
- `docs/troubleshooting-iac.md` — IaC recovery and conflict resolution
- `docs/validation-g26.md` — Validation report (G.2.6)
- `docs/validation-g27.md` — Validation report (G.2.7)
- `CHANGELOG.md` — Project changelog

## Security notes

- Do **not** commit `.env` to version control.
- Protect `.env` with `chmod 600`.
- Do **not** expose the dashboard/API directly to the internet without HTTPS
  and a reverse proxy.
- Do **not** expose IMAP (port 143) or SMTP (port 2525) directly to the
  internet.
- Use a VPN, Tailscale, firewall, SSH tunnel, or reverse proxy for remote
  access.
- OpenTofu state files may contain sensitive information (credentials,
  tokens). Treat state files as secrets.
- AWS resources incur real costs. Review costs before applying.
- Always review the OpenTofu plan before applying.
- Do **not** use AWS root account access keys.

## Known limitations

- **Not production-ready.** This is alpha software.
- No built-in HTTPS/TLS for dashboard or API.
- No IMAP TLS in the alpha Docker flow.
- No local SMTP authentication in the alpha Docker flow.
- PostgreSQL is not yet supported. Only SQLite is available.
- RBAC / multi-admin permissions are incomplete.
- Backup and restore procedures are basic and manual.
- AWS and Cloudflare are assumed for the automated setup flow.
- AWS SES may be in sandbox mode, limiting outbound email to verified
  recipients only.
- The automated test suite has pre-existing failures (see below).
- No automated backup is included.
- No automated TLS certificate management.

## Test status

```text
pytest result: 71 passed, 56 failed, 1 warning
```

The failures were triaged in `docs/test-triage-alpha.md`. They are
concentrated in outdated auth/session test fixtures, old seed data
assumptions, protected-route behavior expectations, and a Python `crypt`
deprecation warning.

These failures do **not** currently block v0.1.0-alpha because the real
clean-install functional flow was validated in G.2.7 and works correctly.

## Installation

See `README.md` and `docs/deploy-docker.md` for complete instructions.

Quick start:

```bash
git clone <repository-url> openmailgate
cd openmailgate
cp .env.example .env
# Edit .env with your AWS, Cloudflare, and domain settings
docker compose up -d --build
# Open http://YOUR_VM_IP:8000 and create the first administrator
```

## Upgrade notes

This is the **first alpha release**. No upgrade path from a previous public
release is provided.

If you are migrating from a private development version, expect to re-apply
OpenTofu and re-create mailboxes.

## License and attribution

```text
OpenMailGate — Copyright (C) 2026 Ricardo Z. Vendramini.
Licensed under the GNU Affero General Public License v3.0 or later
(GNU AGPL-3.0-or-later).
```

When using, modifying, redistributing, forking, or publishing modified
versions of this project, copyright notices, license notices, and attribution
to the original project and original author must be preserved in accordance
with the GNU AGPL-3.0-or-later.

## AWS / trademark disclaimer

This project is **not affiliated with, endorsed by, or sponsored by Amazon
Web Services.**

Amazon Web Services, AWS, Amazon SES, Amazon S3, and Amazon SQS are
trademarks of their respective owners.

Third-party names, trademarks, libraries, services, and software belong to
their respective owners.

## Next steps after alpha

- Repair the pytest test suite
- HTTPS/TLS hardening for dashboard and IMAP
- Backup and restore improvements
- RBAC / multi-admin permissions
- PostgreSQL optional backend
- Metrics, audit logs, and monitoring
- Webmail integration
- Production hardening
