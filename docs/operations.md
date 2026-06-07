# Operations

See `docs/setup-docker-plan.md` for the Docker deployment and first-run setup plan.

## Service Status

```bash
```

Or use the dashboard: `/dashboard/status`

## Logs

```bash
```

## Migrations

```bash
```

## Tests

```bash
python3 -m compileall .
pytest
```

## IMAP Sync

Dashboard: `/dashboard/imap-sync`

Terminal:
```bash
```

## Dovecot Validation

```bash
sudo doveadm user user@domain
sudo doveadm auth test user@domain
```

Do not paste real passwords into tickets, logs or reports.

## SQLite Validation

```bash
```

## Maildir Validation

```bash
```

## Security Notes

Do not commit:

- `.env`
- `data/`
- `mailbox.db`
- Maildir contents
- Raw emails (`data/raw-emails/`, `data/raw-outbound/`)
- AWS keys / Cloudflare tokens
- `/etc/dovecot/users`
- Backups under `/etc/dovecot/users.bak-*`
