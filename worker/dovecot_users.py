"""Parse and generate Dovecot passwd-file entries.

The passwd-file format is:
    user:password:uid:gid:gecos:home:shell:extra_fields

For virtual users we use:
    user:{SCHEME}hash:uid:gid::home::userdb_mail=maildir:/path
"""

import os
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path


def parse_dovecot_users(path):
    """Return dict {user: full_line} from a Dovecot passwd-file."""
    entries = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":", 1)
                if len(parts) >= 2:
                    entries[parts[0]] = line
    except FileNotFoundError:
        pass
    return entries


def _mask_hash(full_line):
    """Replace password hash with masked version for display."""
    return re.sub(
        r"(\{[A-Z0-9-]+\}\$[^:]{0,10})[^:]*",
        r"\1****",
        full_line,
    )


def generate_entries(conn, existing_entries, uid, gid, home):
    """Return (lines, added, kept, removed, pending) based on DB vs existing file.

    - kept: users in both DB and file
    - added: users in DB but not in file (no hash — listed as pending)
    - removed: users in file but not in DB
    - pending: users in DB without hash in file
    """
    rows = conn.execute("""
        SELECT e.address, m.maildir_path, m.slug
        FROM email_addresses e
        JOIN mailboxes m ON m.id = e.mailbox_id
        WHERE e.is_active = 1 AND m.is_active = 1
        ORDER BY e.id
    """).fetchall()

    db_users = {r[0]: r for r in rows}

    kept = {}
    added = {}
    pending = {}
    removed = {}

    for addr, (address, maildir_path, slug) in db_users.items():
        if addr in existing_entries:
            kept[addr] = existing_entries[addr]
        else:
            pending[addr] = maildir_path

    for addr, line in existing_entries.items():
        if addr not in db_users:
            removed[addr] = line

    # Build output lines
    lines = {}
    for addr, line in kept.items():
        lines[addr] = _rebuild_line(line, uid, gid, home, db_users[addr][1])

    return lines, kept, added, removed, pending


def _rebuild_line(existing_line, uid, gid, home, maildir_path):
    """Rebuild a passwd-file line preserving the hash, updating uid/gid/home/maildir.

    Handles the 9-field format caused by the colon in ``maildir:/path``.
    """
    parts = existing_line.split(":")
    if len(parts) >= 3:
        parts[2] = str(uid)
        parts[3] = str(gid)
    if len(parts) >= 6:
        parts[5] = str(home)
    # Rebuild extra_fields: store userdb_mail as 2 colon-separated parts
    # (the colon in maildir:/path splits the field in passwd-file format)
    while len(parts) < 9:
        parts.append("")
    parts[7] = "userdb_mail=maildir"
    parts[8] = maildir_path
    return ":".join(parts[:9])


def apply_users_file(new_entries, target_path="/etc/dovecot/users", group="dovecot"):
    """Write entries to target_path atomically with backup."""
    target = Path(target_path)

    # Backup
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target.parent / f"{target.name}.bak-{ts}"
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")

    # Write to temp file
    tmp = Path(tempfile.mktemp(dir=target.parent, prefix=".dovecot_users."))
    with open(tmp, "w") as f:
        for _user, line in sorted(new_entries.items()):
            f.write(line + "\n")

    # Set permissions
    try:
        import grp
        gid = grp.getgrnam(group).gr_gid
        os.chown(tmp, 0, gid)
    except (ImportError, KeyError, ModuleNotFoundError):
        pass
    os.chmod(tmp, 0o640)

    # Atomic rename
    tmp.rename(target)
    print(f"Wrote {len(new_entries)} user(s) to {target}")
    print("Validate with: sudo doveadm user <email>")


def cmd_sync(args, db_path):
    """Handle the sync-imap-users CLI command."""
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        existing = parse_dovecot_users(args.users_file)
    except PermissionError:
        print(
            f"ERROR: cannot read {args.users_file}. "
            "Run with sudo or use --users-file pointing to a readable file.",
            file=sys.stderr,
        )
        sys.exit(1)
    except FileNotFoundError:
        print(
            f"WARNING: {args.users_file} not found. No existing users to preserve.",
            file=sys.stderr,
        )
        existing = {}

    lines, kept, added, removed, pending = generate_entries(
        conn, existing, args.uid, args.gid, args.home
    )
    conn.close()

    n_kept = len(kept)
    n_pending = len(pending)
    n_removed = len(removed)

    if args.dry_run:
        print(f"[dry-run] Would keep: {n_kept}")
        for addr, line in sorted(kept.items()):
            print(f"  keep  {addr:40s} {_mask_hash(line)}")
        if n_pending:
            print()
            print(f"[dry-run] Pending (active in DB, no hash in file): {n_pending}")
            for addr, maildir in sorted(pending.items()):
                print(f"  NEW   {addr:40s} → {maildir}")
        if n_removed:
            print()
            print(f"[dry-run] Would remove (no longer active): {n_removed}")
            for addr in sorted(removed):
                print(f"  DEL   {addr:40s}")
        return

    if args.output:
        out = Path(args.output)
        with open(out, "w") as f:
            for _user, line in sorted(lines.items()):
                f.write(line + "\n")
        print(f"Generated {len(lines)} user(s) → {out}")
        return

    if args.apply:
        apply_users_file(lines, target_path=args.users_file)
        return

    # Default: dry-run behavior when no flag
    print(f"Kept: {n_kept}, Pending: {n_pending}, Removed: {n_removed}")
    print("Use --dry-run, --output <path>, or --apply")
