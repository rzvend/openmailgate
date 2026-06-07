# Alpha Security Checklist — v0.1.0-alpha

> **IMPORTANT:** OpenMailGate v0.1.0-alpha is **not production-ready**.
> This checklist helps ensure the alpha release does not contain
> real secrets, internal data, or unsafe defaults.

---

## 1. Secrets in source code

Run from the project root:

```bash
grep -RInE \
'AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|cfat_[A-Za-z0-9_-]+|\b[0-9]{12}\b' \
README.md docs/*.md docs/archive/*.md .env.example api/templates api/routes || true
```

- [ ] No real AWS access keys in tracked files.
- [ ] No real Cloudflare tokens in tracked files.
- [ ] No real AWS account IDs in tracked files.

## 2. Secret variable names (acceptable)

```bash
grep -RInE \
'AWS_SECRET_ACCESS_KEY|CLOUDFLARE_API_TOKEN|SES_SMTP_PASSWORD|SESSION_SECRET' \
README.md docs/*.md .env.example api/templates api/routes || true
```

- [ ] Variable **names** and placeholder values (`CHANGE_ME`) are acceptable.
- [ ] Real secret **values** are never present in tracked files.

## 3. Internal / outdated references

```bash
grep -RInE \
'SES S3 Mailbox|bootstrap_admin|worker/migrate|10\.10\.10\.16|10\.10\.10\.36|10\.10\.10\.56|openmailgate\.ricardo\.vc|alpha\.ricardo\.vc|boto\.ricardo\.vc|/home/ricardo' \
README.md docs/*.md .env.example || true
```

- [ ] No old project name references in active documentation.
- [ ] No internal lab IPs in active documentation.
- [ ] No real test domains in active documentation.
- [ ] Historical references in `docs/archive/` are acceptable.

## 4. `.env` and `.env.example`

- [ ] `.env` is listed in `.gitignore`.
- [ ] `.env.example` contains no real secrets, tokens, account IDs, or internal data.
- [ ] `.env.example` uses `CHANGE_ME` or empty values for all required fields.
- [ ] `APP_NAME` is set to `OpenMailGate`.
- [ ] `SES_SMTP_STARTTLS=true` is correct (SES SMTP relay, not local IMAP).

## 5. `.gitignore` review

- [ ] `*.tfstate` and `*.tfstate.*` are ignored.
- [ ] `*.tfplan` is ignored.
- [ ] `.env` is ignored.
- [ ] `data/raw-emails/` and `data/raw-outbound/` are ignored.
- [ ] `maildir/` and `dovecot/users` are ignored.
- [ ] `*.eml` is ignored.
- [ ] `.terraform/` and `.tofu/` are ignored.
- [ ] `mailbox.db` is ignored.

## 6. OpenTofu state

```bash
find . -name '*.tfstate*' -o -name 'terraform.tfstate*'
```

- [ ] No OpenTofu/Terraform state files are committed or tracked.
- [ ] State is stored in a persistent Docker volume (`iac_state` at `/app/state/iac`).
- [ ] State backups are excluded from version control.

## 7. Docker volumes / persistent data

- [ ] `app_data` volume contains the SQLite database and Maildir.
- [ ] `dovecot_data` volume contains Dovecot users file.
- [ ] `iac_state` volume contains OpenTofu state.
- [ ] No volume data is committed to version control.

## 8. Network exposure

- [ ] Dashboard/API uses HTTP by default (no TLS). Use a reverse proxy for production.
- [ ] IMAP binds to `127.0.0.1:143` by default. Change `IMAP_BIND` for remote access.
- [ ] SMTP binds to `127.0.0.1:2525` by default. Change `SMTP_BIND` for remote access.
- [ ] Do not expose IMAP/SMTP to the public internet in the alpha configuration.
- [ ] Use a trusted network, VPN, Tailscale, firewall, or SSH tunnel for remote access.

## 9. Documentation sanitization

- [ ] `README.md` uses example values, no real data.
- [ ] `docs/deploy-docker.md` is up to date with the current alpha flow.
- [ ] `docs/troubleshooting-iac.md` uses generic resource names.
- [ ] Validation reports (`docs/validation-*`) use example domains.
- [ ] `docs/archive/` contains historical documents with appropriate notices.

## 10. Log sanitization

- [ ] The dashboard sanitizes Terraform/OpenTofu output via `_sanitize_setup_log()`.
- [ ] Secrets are masked in OpenTofu plan/apply output before rendering.
- [ ] Dovecot logs are not exposed to the public.
- [ ] Worker logs do not contain raw email content or credentials.

## 11. AWS SES sandbox / production

- [ ] AWS SES may be in sandbox mode. Outbound email only works with verified recipients.
- [ ] Request SES production access for unrestricted sending.
- [ ] Verify `MAIL_DOMAIN` identity and DKIM before sending.

## 12. IAM permissions

- [ ] `AdministratorAccess` is acceptable for alpha testing but not recommended for production.
- [ ] The Terraform-created IAM user (`ses-s3-mailbox-smtp-sender`) has only `ses:SendRawEmail` and `ses:SendEmail`.
- [ ] Review IAM policies before applying in production.

## 13. Cloudflare token

- [ ] The Cloudflare API token has DNS edit permission for the target zone.
- [ ] Do not use Account ID as Zone ID.
- [ ] The token is not committed to version control.

## 14. About / License / Credits

- [ ] `/dashboard/about` page includes license (GNU AGPL-3.0-or-later).
- [ ] Footer on dashboard pages includes copyright and license notice.
- [ ] AWS non-affiliation disclaimer is present.
- [ ] Third-party trademark notice is present.

## 15. Alpha limitations

- [ ] Dashboard/API runs over HTTP (no TLS).
- [ ] IMAP (port 143) has no TLS.
- [ ] SMTP (port 2525) has no local authentication.
- [ ] AWS resources incur real costs.
- [ ] Review OpenTofu plans before applying.
- [ ] Backup `.env`, database (`mailbox.db`), Maildir, and OpenTofu state regularly.
- [ ] No automated backup is included in alpha.
- [ ] No automated TLS certificate management.

---

## Final checklist before v0.1.0-alpha tag

- [ ] README reviewed
- [ ] `docs/deploy-docker.md` reviewed
- [ ] `docs/security-alpha.md` created
- [ ] All documentation sanitized
- [ ] About/License/Credits in dashboard
- [ ] Secrets grep clean
- [ ] Internal data grep clean
- [ ] `.env.example` has no real values
- [ ] `.gitignore` reviewed
- [ ] No OpenTofu state committed
- [ ] Logs sanitized
- [ ] Alpha limitations documented
- [ ] Release notes prepared
- [ ] Tag `v0.1.0-alpha` created
