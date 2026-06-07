# Changelog

All notable changes to OpenMailGate.

## v0.1.0-alpha

This is the first alpha release. No upgrade path from a previous public release is provided.

### Added
- Docker Compose deployment (api, worker-sqs, smtp-sender, dovecot)
- Web-based dashboard with first-run admin setup
- AWS/Cloudflare credential validation (STS, Cloudflare zone)
- IAM credentials preflight (access key discovery)
- OpenTofu init/plan/apply via dashboard with safeguards
- Post-apply infrastructure validation (S3, SQS, SES, Cloudflare DNS)
- Runtime environment sync from OpenTofu outputs
- First mailbox wizard with IMAP password setup
- IMAP user sync to Dovecot passwd-file
- SES/S3/SQS inbound email flow via worker-sqs
- SES SMTP outbound relay via smtp-sender
- Dovecot IMAP/Maildir with Thunderbird compatibility
- Custom MAIL FROM domain automation (SES + Cloudflare DNS)
- Basic IaC conflict detection and recovery guidance
- Unique resource naming with persistent suffix
- About / License page with GNU AGPL-3.0-or-later
- Copyright footer on all dashboard pages
- OpenMailGate branding and logo

### Fixed
- SES Custom MAIL FROM timing: wait for identity propagation before MAIL FROM setup
- Maildir ownership: normalize root and intermediate folder permissions for Dovecot
- IMAP alpha authentication: allow local plaintext IMAP authentication for trusted-network testing
- Dovecot volume sharing with API container
- OpenTofu state persistence in Docker volume
- IMAP sync without sudo in Docker setup
- S3 bucket env var standardization
- Placeholder detection for .env values in IaC setup
- Inline comment handling in .env values

### Documentation
- README updated for alpha release
- `docs/deploy-docker.md` — Docker deployment guide
- `docs/security-alpha.md` — Alpha security checklist
- `docs/test-triage-alpha.md` — Pytest triage (71 passed, 56 failed)
- `docs/troubleshooting-iac.md` — IaC recovery and conflict resolution
- `docs/backup-restore.md` — Backup and restore procedures
- `docs/operations.md` — Operational commands
- `docs/release-notes-v0.1.0-alpha.md` — Detailed release notes
- Documentation sanitized for public release

### Validation
- G.2.7 — Final clean install release candidate (approved)
- Real inbound and outbound email delivery tested
- Thunderbird IMAP/SMTP configuration validated
- Sent folder copy confirmed working
- SES/Cloudflare DNS records validated, including DKIM, SPF, and Custom MAIL FROM

### Known Limitations
- Not production-ready
- No built-in HTTPS/TLS for dashboard or IMAP
- No local SMTP authentication
- PostgreSQL not yet supported
- RBAC / multi-admin permissions incomplete
- AWS SES sandbox may limit outbound email
- Automated test suite needs post-alpha repair (71 passed, 56 failed)
