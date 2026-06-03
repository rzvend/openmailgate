# Backup and Restore

## What to Backup

| Item | Path | Notes |
|---|---|---|
| SQLite database | `data/mailbox.db` | All mailboxes, messages, settings, operators |
| Maildir | `data/maildir/` | All email content |
| Raw emails | `data/raw-emails/` `data/raw-outbound/` | Inbound and outbound raw copies |
| Terraform state | `terraform/*.tfstate` or volume `iac_state` | Cloud infrastructure state — essential for future applies |
| Environment | `.env` | AWS keys, Cloudflare token, SMTP credentials — protect carefully |
| Dovecot users | `/etc/dovecot/users` | Virtual IMAP users (host file) |

## Backup (manual)

```bash
# From the project root:
tar -czf /tmp/ses-s3-backup-$(date +%Y%m%d).tar.gz \
  data/mailbox.db \
  data/maildir/ \
  data/raw-emails/ \
  data/raw-outbound/ \
  terraform/*.tfstate* \
  .env

# Protect the backup file:
chmod 600 /tmp/ses-s3-backup-*.tar.gz
```

**Warning:** The backup contains email content and may contain secrets from `.env`. Store it securely. Do not commit backups to the repository.

## Backup (Docker)

```bash
# SQLite only:
docker compose run --rm api cp /app/data/mailbox.db /app/logs/mailbox-backup.db

# Full backup using volumes:
docker run --rm -v ses-s3-mailbox_app_data:/data -v $(pwd)/backups:/backup \
  alpine tar -czf /backup/ses-s3-backup-$(date +%Y%m%d).tar.gz /data
```

## Restore

```bash
# Stop services
docker compose down

# Restore data directory
tar -xzf ses-s3-backup-YYYYMMDD.tar.gz -C .

# Start services
docker compose up -d
docker compose run --rm api python3 worker/migrate.py
```

## Dovecot Users (host)

```bash
# Backup
sudo cp /etc/dovecot/users /etc/dovecot/users.backup

# Restore (after data restore)
sudo python3 -m worker.mailbox_admin sync-imap-users --apply
```

## Safety

- Backup before running Terraform/OpenTofu apply.
- Backup before upgrading.
- Store backups outside the project directory.
- Do not commit backups.
- Consider encrypting backups containing `.env`.
