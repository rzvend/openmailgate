# Admin Dashboard

## Overview

The admin dashboard provides basic administration of mailboxes, email addresses, IMAP users, operators and catch-all routing.

## Login

Access `http://<host>:8000/dashboard` and log in with an active operator account. Operators are managed via the dashboard or CLI (`worker/mailbox_admin`).

## Create Mailbox Wizard

The wizard (`/dashboard/mailboxes/wizard`) is the recommended flow to create a fully functional mailbox. It:

1. Creates the mailbox and primary email address
2. Sets the IMAP password
3. Optionally runs IMAP sync to update Dovecot

After completion, the mailbox is ready for Thunderbird.

## IMAP Password

Each email address can have an IMAP password set via the address detail page. Password hashes are never displayed in the dashboard.

## IMAP Sync

IMAP Sync (`/dashboard/imap-sync`) generates Dovecot virtual users from the database. Dry-run previews the result without modifying files. Apply writes to `/etc/dovecot/users` (requires sudoers configuration).

## Enable / Disable

Mailboxes and addresses can be disabled without deleting data — only the `is_active` flag is changed. After enabling or disabling, run IMAP Sync to update Dovecot.

## Operators and Permissions

Operators are dashboard users. They can be created, assigned passwords, enabled/disabled, and granted mailbox access with `viewer` or `admin` roles. Full RBAC enforcement is planned for a later phase.

## Catch-all

Catch-all receives messages sent to unknown or inactive addresses. Set via `/dashboard/catch-all`. Active addresses with active mailboxes always take priority over catch-all.

## Thunderbird Settings

| Setting | Value |
|---|---|
| IMAP Server | `10.10.10.16` |
| IMAP Port | `143` |
| Security | STARTTLS |
| Username | Full email address |
| Password | IMAP password configured in dashboard |

SMTP settings depend on the local SMTP relay configuration (port `2525` by default, no authentication, STARTTLS disabled).

## Safety Notes

- Never commit `.env`, `mailbox.db`, Maildir data, or real email files
- Passwords and hashes are never displayed in the dashboard
- Run `sync-imap-users` after creating mailboxes or changing activation status
- Dovecot is not restarted automatically — validate with `doveadm user <email>`
