# Operations

## Service Status

```bash
systemctl status ses-s3-mailbox-api --no-pager
systemctl status ses-s3-mailbox-sqs-worker --no-pager
systemctl status ses-s3-mailbox-smtp-sender --no-pager
systemctl status dovecot --no-pager
```

Or use the dashboard: `/dashboard/status`

## Logs

```bash
journalctl -u ses-s3-mailbox-api -n 100 --no-pager
journalctl -u ses-s3-mailbox-sqs-worker -n 100 --no-pager
journalctl -u ses-s3-mailbox-smtp-sender -n 100 --no-pager
journalctl -u dovecot -n 100 --no-pager
```

## Migrations

```bash
python3 worker/migrate.py
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
sudo /home/ricardo/ses-s3-mailbox/scripts/sync_imap_users_apply.sh
```

## Dovecot Validation

```bash
sudo doveadm user user@domain
sudo doveadm auth test user@domain
```

Do not paste real passwords into tickets, logs or reports.

## SQLite Validation

```bash
sqlite3 /home/ricardo/ses-s3-mailbox/data/mailbox.db "SELECT 1;"
```

## Maildir Validation

```bash
find /home/ricardo/ses-s3-mailbox/data/maildir -maxdepth 2 -type d | head
```

## Security Notes

Do not commit:

- `.env`
- `data/`
- `mailbox.db`
- Maildir contents
- Raw emails (`data/raw-emails/`, `data/raw-outbound/`)
- AWS keys / Cloudflare tokens
- Terraform state
- `/etc/dovecot/users`
- Backups under `/etc/dovecot/users.bak-*`
