#!/usr/bin/env bash
# Wrapper for sync-imap-users --apply.
# Runs the real sync with fixed paths. Called by the dashboard or manually.
# Requires sudoers entry:
#   ricardo ALL=(root) NOPASSWD: /home/ricardo/ses-s3-mailbox/scripts/sync_imap_users_apply.sh
set -euo pipefail
cd /home/ricardo/ses-s3-mailbox
exec /usr/bin/python3 -m worker.mailbox_admin sync-imap-users --apply
