#!/usr/bin/env python3
"""CLI for managing mailboxes and email addresses in the SES S3 Mailbox project.

Usage:
    python3 -m worker.mailbox_admin list
    python3 -m worker.mailbox_admin show <slug>
    python3 -m worker.mailbox_admin create <slug> --name <name> [--address <email>] [--maildir-path <path>]
    python3 -m worker.mailbox_admin addresses [--mailbox <slug>]
    python3 -m worker.mailbox_admin add-address <slug> <email> [--primary]
    python3 -m worker.mailbox_admin disable-address <email>
    python3 -m worker.mailbox_admin enable-address <email>
    python3 -m worker.mailbox_admin disable-mailbox <slug>
    python3 -m worker.mailbox_admin enable-mailbox <slug>
"""

import argparse
import getpass
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

# ── load project configuration ───────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from config import DB_PATH as _DB_PATH, MAILDIR_BASE, MASTER_MAILDIR  # noqa: E402

DB_PATH = _DB_PATH

from worker.mailbox_resolver import normalize_email_address  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _conn():
    return sqlite3.connect(str(DB_PATH))


def _die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def _ensure_maildir(slug):
    base = MAILDIR_BASE / slug
    for sub in ("cur", "new", "tmp", ".Sent/cur", ".Sent/new", ".Sent/tmp"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    (base / ".Sent" / "maildirfolder").write_text("")
    return str(base)


def _validate_slug(slug):
    if not SLUG_RE.match(slug):
        _die(f"invalid slug: '{slug}' — use lowercase letters, numbers, hyphen, underscore")


def _validate_email(email):
    if not EMAIL_RE.match(normalize_email_address(email)):
        _die(f"invalid email address: '{email}'")


def _format_yn(val):
    return "yes" if val else "no"


# ── commands ─────────────────────────────────────────────────────────────


def cmd_list():
    conn = _conn()
    rows = conn.execute(
        "SELECT id, slug, name, maildir_path, is_active FROM mailboxes ORDER BY id"
    ).fetchall()
    conn.close()

    if not rows:
        print("(no mailboxes)")
        return

    print(f"{'ID':<4} {'SLUG':<16} {'NAME':<16} {'ACTIVE':<7} MAILDIR")
    for r in rows:
        print(f"{r[0]:<4} {r[1]:<16} {r[2]:<16} {_format_yn(r[4]):<7} {r[3]}")


def cmd_show(slug):
    conn = _conn()
    mb = conn.execute(
        "SELECT id, slug, name, maildir_path, is_active, created_at FROM mailboxes WHERE slug=?",
        (slug,),
    ).fetchone()
    if not mb:
        _die(f"mailbox not found: {slug}")

    addrs = conn.execute(
        "SELECT address, is_primary, is_active FROM email_addresses WHERE mailbox_id=? ORDER BY is_primary DESC, id",
        (mb[0],),
    ).fetchall()

    total = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE mailbox_id=?", (mb[0],)
    ).fetchone()[0]
    inbound = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE mailbox_id=? AND direction='inbound'", (mb[0],)
    ).fetchone()[0]
    outbound = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE mailbox_id=? AND direction='outbound'", (mb[0],)
    ).fetchone()[0]
    conn.close()

    print(f"Mailbox:")
    print(f"  id: {mb[0]}")
    print(f"  slug: {mb[1]}")
    print(f"  name: {mb[2]}")
    print(f"  active: {_format_yn(mb[4])}")
    print(f"  maildir_path: {mb[3]}")
    print(f"  created_at: {mb[5]}")
    print()
    print(f"Addresses:")
    if addrs:
        for a in addrs:
            pri = "yes" if a[1] else "no"
            act = "yes" if a[2] else "no"
            print(f"  {a[0]:<40} primary={pri}  active={act}")
    else:
        print(f"  (none)")
    print()
    print(f"Messages:")
    print(f"  total: {total}")
    print(f"  inbound: {inbound}")
    print(f"  outbound: {outbound}")


def cmd_create(slug, name, address, maildir_path):
    _validate_slug(slug)

    conn = _conn()
    existing = conn.execute("SELECT id FROM mailboxes WHERE slug=?", (slug,)).fetchone()
    if existing:
        _die(f"mailbox already exists: {slug}")

    mdir = maildir_path or _ensure_maildir(slug)

    cur = conn.execute(
        "INSERT INTO mailboxes (name, slug, maildir_path) VALUES (?, ?, ?)",
        (name, slug, mdir),
    )
    mailbox_id = cur.lastrowid

    if address:
        _validate_email(address)
        norm = normalize_email_address(address)
        conn.execute(
            "INSERT INTO email_addresses (mailbox_id, address, is_primary, is_active) VALUES (?, ?, 1, 1)",
            (mailbox_id, norm),
        )

    conn.commit()
    conn.close()

    print(f"Created mailbox: {slug} (id={mailbox_id}, maildir={mdir})")
    if address:
        print(f"  with address: {normalize_email_address(address)}")


def cmd_addresses(slug_filter):
    conn = _conn()
    if slug_filter:
        mb = conn.execute("SELECT id FROM mailboxes WHERE slug=?", (slug_filter,)).fetchone()
        if not mb:
            _die(f"mailbox not found: {slug_filter}")
        rows = conn.execute(
            """SELECT e.id, e.address, m.slug, e.is_primary, e.is_active
               FROM email_addresses e
               JOIN mailboxes m ON m.id = e.mailbox_id
               WHERE e.mailbox_id = ?
               ORDER BY e.id""",
            (mb[0],),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT e.id, e.address, m.slug, e.is_primary, e.is_active
               FROM email_addresses e
               JOIN mailboxes m ON m.id = e.mailbox_id
               ORDER BY e.id""",
        ).fetchall()
    conn.close()

    if not rows:
        print("(no addresses)")
        return

    print(f"{'ID':<4} {'ADDRESS':<38} {'MAILBOX':<16} {'PRIMARY':<8} ACTIVE")
    for r in rows:
        print(f"{r[0]:<4} {r[1]:<38} {r[2]:<16} {_format_yn(r[3]):<8} {_format_yn(r[4])}")


def cmd_add_address(slug, email, primary):
    _validate_email(email)
    norm = normalize_email_address(email)

    conn = _conn()
    mb = conn.execute("SELECT id, is_active FROM mailboxes WHERE slug=?", (slug,)).fetchone()
    if not mb:
        _die(f"mailbox not found: {slug}")
    if not mb[1]:
        _die(f"mailbox is inactive: {slug}")

    dup = conn.execute("SELECT id FROM email_addresses WHERE address=?", (norm,)).fetchone()
    if dup:
        _die(f"email address already exists: {norm}")

    # Determine is_primary: if --primary flag is set, or this is the first address
    if primary:
        is_primary = 1
        conn.execute(
            "UPDATE email_addresses SET is_primary=0 WHERE mailbox_id=?", (mb[0],)
        )
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM email_addresses WHERE mailbox_id=?", (mb[0],)
        ).fetchone()[0]
        is_primary = 1 if count == 0 else 0

    conn.execute(
        "INSERT INTO email_addresses (mailbox_id, address, is_primary, is_active) VALUES (?, ?, ?, 1)",
        (mb[0], norm, is_primary),
    )
    conn.commit()
    conn.close()
    print(f"Added address: {norm} → {slug}" + (" (primary)" if is_primary else ""))


def cmd_disable_address(email):
    norm = normalize_email_address(email)

    conn = _conn()
    row = conn.execute(
        "SELECT id, is_active FROM email_addresses WHERE address=?", (norm,)
    ).fetchone()
    if not row:
        _die(f"address not found: {norm}")
    if not row[1]:
        conn.close()
        print(f"Address already inactive: {norm}")
        return

    conn.execute("UPDATE email_addresses SET is_active=0 WHERE id=?", (row[0],))
    conn.commit()
    conn.close()
    print(f"Disabled address: {norm}")


def cmd_enable_address(email):
    norm = normalize_email_address(email)

    conn = _conn()
    row = conn.execute(
        "SELECT id, is_active FROM email_addresses WHERE address=?", (norm,)
    ).fetchone()
    if not row:
        _die(f"address not found: {norm}")
    if row[1]:
        conn.close()
        print(f"Address already active: {norm}")
        return

    conn.execute("UPDATE email_addresses SET is_active=1 WHERE id=?", (row[0],))
    conn.commit()
    conn.close()
    print(f"Enabled address: {norm}")


def cmd_disable_mailbox(slug):
    if slug == "master":
        _die("cannot disable master mailbox")

    conn = _conn()
    mb = conn.execute("SELECT id, is_active FROM mailboxes WHERE slug=?", (slug,)).fetchone()
    if not mb:
        _die(f"mailbox not found: {slug}")
    if not mb[1]:
        conn.close()
        print(f"Mailbox already inactive: {slug}")
        return

    conn.execute("UPDATE mailboxes SET is_active=0 WHERE id=?", (mb[0],))
    conn.commit()
    conn.close()
    print(f"Disabled mailbox: {slug}")


def cmd_enable_mailbox(slug):
    conn = _conn()
    mb = conn.execute("SELECT id, is_active FROM mailboxes WHERE slug=?", (slug,)).fetchone()
    if not mb:
        _die(f"mailbox not found: {slug}")
    if mb[1]:
        conn.close()
        print(f"Mailbox already active: {slug}")
        return

    conn.execute("UPDATE mailboxes SET is_active=1 WHERE id=?", (mb[0],))
    conn.commit()
    conn.close()
    print(f"Enabled mailbox: {slug}")


def cmd_set_imap_password(email):
    norm = normalize_email_address(email)

    conn = _conn()
    row = conn.execute(
        "SELECT e.id, e.is_active, m.is_active AS mb_active FROM email_addresses e "
        "JOIN mailboxes m ON m.id = e.mailbox_id WHERE e.address = ?",
        (norm,),
    ).fetchone()
    if not row:
        _die(f"address not found: {norm}")
    if not row[1] or not row[2]:
        _die(f"address or mailbox is inactive: {norm}")

    pw1 = getpass.getpass(f"New IMAP password for {norm}: ")
    if not pw1:
        _die("password cannot be empty")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        _die("passwords do not match")

    # Use doveadm pw via stdin (secure — never in process args)
    try:
        result = subprocess.run(
            ["doveadm", "pw", "-s", "SHA512-CRYPT"],
            input=f"{pw1}\n{pw1}",
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            _die(f"doveadm pw failed: {result.stderr.strip()}")
        hashed = result.stdout.strip().split("\n")[-1]
        if not hashed.startswith("{"):
            _die(f"unexpected hash output from doveadm pw")
    except FileNotFoundError:
        _die("doveadm not found — install dovecot or use a system with dovecot installed")
    except Exception as exc:
        _die(f"failed to generate password hash: {exc}")

    conn.execute("UPDATE email_addresses SET imap_password_hash=? WHERE id=?", (hashed, row[0]))
    conn.commit()
    conn.close()

    masked = hashed[:25] + "****"
    print(f"Updated IMAP password for {norm}")
    print(f"Hash stored: {masked}")


# ── operator commands ────────────────────────────────────────────────────


def _gen_hash(password):
    result = subprocess.run(
        ["doveadm", "pw", "-s", "SHA512-CRYPT"],
        input=f"{password}\n{password}",
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        _die(f"doveadm pw failed: {result.stderr.strip()}")
    hashed = result.stdout.strip().split("\n")[-1]
    if not hashed.startswith("{"):
        _die("unexpected hash output from doveadm pw")
    return hashed


def cmd_create_operator(username):
    username = username.strip().lower()
    if not username:
        _die("username cannot be empty")
    conn = _conn()
    dup = conn.execute("SELECT id FROM operators WHERE username=?", (username,)).fetchone()
    if dup:
        _die(f"operator already exists: {username}")
    conn.execute("INSERT INTO operators (username, password_hash, is_active) VALUES (?, '', 1)", (username,))
    op_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    print(f"Created operator: {username} (id={op_id})")
    print(f"Run: python3 -m worker.mailbox_admin set-operator-password {username}")


def cmd_set_operator_password(username):
    username = username.strip().lower()
    conn = _conn()
    op = conn.execute("SELECT id, is_active FROM operators WHERE username=?", (username,)).fetchone()
    if not op:
        _die(f"operator not found: {username}")
    if not op[1]:
        print(f"Warning: operator {username} is inactive")

    pw1 = getpass.getpass(f"New dashboard password for operator {username}: ")
    if not pw1:
        _die("password cannot be empty")
    pw2 = getpass.getpass("Confirm password: ")
    if pw1 != pw2:
        _die("passwords do not match")

    hashed = _gen_hash(pw1)
    conn.execute("UPDATE operators SET password_hash=? WHERE id=?", (hashed, op[0]))
    conn.commit()
    conn.close()
    print(f"Updated dashboard password for operator: {username}")
    print(f"Hash stored: {hashed[:25]}****")


def cmd_list_operators():
    conn = _conn()
    rows = conn.execute(
        """SELECT o.id, o.username, o.is_active, o.created_at,
                  (SELECT COUNT(*) FROM operator_mailboxes WHERE operator_id=o.id) AS mb_count
           FROM operators o ORDER BY o.id"""
    ).fetchall()
    conn.close()
    if not rows:
        print("(no operators)")
        return
    print(f"{'ID':<4} {'USERNAME':<20} {'ACTIVE':<7} {'MAILBOXES':<10} CREATED_AT")
    for r in rows:
        print(f"{r[0]:<4} {r[1]:<20} {_format_yn(r[2]):<7} {r[4]:<10} {r[3]}")


def cmd_show_operator(username):
    username = username.strip().lower()
    conn = _conn()
    op = conn.execute(
        "SELECT id, username, is_active, created_at FROM operators WHERE username=?", (username,)
    ).fetchone()
    if not op:
        _die(f"operator not found: {username}")

    perms = conn.execute(
        """SELECT m.slug, m.name, om.role
           FROM operator_mailboxes om
           JOIN mailboxes m ON m.id = om.mailbox_id
           WHERE om.operator_id = ?
           ORDER BY m.slug""",
        (op[0],),
    ).fetchall()
    conn.close()

    print("Operator:")
    print(f"  id: {op[0]}")
    print(f"  username: {op[1]}")
    print(f"  active: {_format_yn(op[2])}")
    print(f"  created_at: {op[3]}")
    print()
    print("Mailboxes:")
    if perms:
        for p in perms:
            print(f"  {p[0]:<16} role={p[2]}")
    else:
        print("  (none)")


def cmd_disable_operator(username):
    username = username.strip().lower()
    conn = _conn()
    op = conn.execute("SELECT id, is_active FROM operators WHERE username=?", (username,)).fetchone()
    if not op:
        _die(f"operator not found: {username}")
    if not op[1]:
        conn.close()
        print(f"Operator already inactive: {username}")
        return
    conn.execute("UPDATE operators SET is_active=0 WHERE id=?", (op[0],))
    conn.commit()
    conn.close()
    print(f"Disabled operator: {username}")


def cmd_enable_operator(username):
    username = username.strip().lower()
    conn = _conn()
    op = conn.execute("SELECT id, is_active FROM operators WHERE username=?", (username,)).fetchone()
    if not op:
        _die(f"operator not found: {username}")
    if op[1]:
        conn.close()
        print(f"Operator already active: {username}")
        return
    conn.execute("UPDATE operators SET is_active=1 WHERE id=?", (op[0],))
    conn.commit()
    conn.close()
    print(f"Enabled operator: {username}")


def cmd_grant_mailbox(username, slug, role):
    username = username.strip().lower()
    conn = _conn()
    op = conn.execute("SELECT id, is_active FROM operators WHERE username=?", (username,)).fetchone()
    if not op:
        _die(f"operator not found: {username}")
    if not op[1]:
        _die(f"operator is inactive: {username}")
    mb = conn.execute("SELECT id, is_active FROM mailboxes WHERE slug=?", (slug,)).fetchone()
    if not mb:
        _die(f"mailbox not found: {slug}")
    if not mb[1]:
        _die(f"mailbox is inactive: {slug}")

    conn.execute(
        """INSERT INTO operator_mailboxes (operator_id, mailbox_id, role)
           VALUES (?, ?, ?)
           ON CONFLICT(operator_id, mailbox_id) DO UPDATE SET role=excluded.role""",
        (op[0], mb[0], role),
    )
    conn.commit()
    conn.close()
    print(f"Granted {username} role={role} on mailbox {slug}")


def cmd_revoke_mailbox(username, slug):
    username = username.strip().lower()
    conn = _conn()
    op = conn.execute("SELECT id FROM operators WHERE username=?", (username,)).fetchone()
    if not op:
        _die(f"operator not found: {username}")
    mb = conn.execute("SELECT id FROM mailboxes WHERE slug=?", (slug,)).fetchone()
    if not mb:
        _die(f"mailbox not found: {slug}")

    deleted = conn.execute(
        "DELETE FROM operator_mailboxes WHERE operator_id=? AND mailbox_id=?",
        (op[0], mb[0]),
    ).rowcount
    conn.commit()
    conn.close()
    if deleted:
        print(f"Revoked {username} access to mailbox {slug}")
    else:
        print(f"No grant found: {username} on {slug}")


# ── argument parser ──────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        prog="mailbox_admin",
        description="Manage mailboxes and email addresses for ses-s3-mailbox",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # list
    sub.add_parser("list", help="List all mailboxes")

    # show
    p_show = sub.add_parser("show", help="Show mailbox details")
    p_show.add_argument("slug")

    # create
    p_create = sub.add_parser("create", help="Create a new mailbox")
    p_create.add_argument("slug")
    p_create.add_argument("--name", required=True)
    p_create.add_argument("--address", default=None)
    p_create.add_argument("--maildir-path", default=None)

    # addresses
    p_addr = sub.add_parser("addresses", help="List email addresses")
    p_addr.add_argument("--mailbox", default=None)

    # add-address
    p_add = sub.add_parser("add-address", help="Add an email address to a mailbox")
    p_add.add_argument("slug")
    p_add.add_argument("email")
    p_add.add_argument("--primary", action="store_true")

    # disable-address / enable-address
    p_da = sub.add_parser("disable-address", help="Disable an email address")
    p_da.add_argument("email")
    p_ea = sub.add_parser("enable-address", help="Enable an email address")
    p_ea.add_argument("email")

    # disable-mailbox / enable-mailbox
    p_dm = sub.add_parser("disable-mailbox", help="Disable a mailbox")
    p_dm.add_argument("slug")
    p_em = sub.add_parser("enable-mailbox", help="Enable a mailbox")
    p_em.add_argument("slug")

    # set-imap-password
    p_sp = sub.add_parser("set-imap-password", help="Set IMAP password for an email address")
    p_sp.add_argument("email")

    # sync-imap-users
    p_sync = sub.add_parser("sync-imap-users", help="Sync Dovecot passwd-file from database")
    import os
    p_sync.add_argument("--users-file", default=os.getenv("DOVECOT_USERS_FILE", "/etc/dovecot/users"))
    p_sync.add_argument("--output", default=None)
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.add_argument("--apply", action="store_true")
    p_sync.add_argument("--uid", type=int, default=1000)
    p_sync.add_argument("--gid", type=int, default=1000)
    p_sync.add_argument("--home", default="/home/ricardo")

    # operators
    p_co = sub.add_parser("create-operator", help="Create a dashboard operator")
    p_co.add_argument("username")
    p_spo = sub.add_parser("set-operator-password", help="Set dashboard password for an operator")
    p_spo.add_argument("username")
    sub.add_parser("list-operators", help="List dashboard operators")
    p_so = sub.add_parser("show-operator", help="Show operator details")
    p_so.add_argument("username")
    p_do = sub.add_parser("disable-operator", help="Disable a dashboard operator")
    p_do.add_argument("username")
    p_eo = sub.add_parser("enable-operator", help="Enable a dashboard operator")
    p_eo.add_argument("username")
    p_gm = sub.add_parser("grant-mailbox", help="Grant operator access to a mailbox")
    p_gm.add_argument("username")
    p_gm.add_argument("slug")
    p_gm.add_argument("--role", default="viewer", choices=["viewer", "admin"])
    p_rm = sub.add_parser("revoke-mailbox", help="Revoke operator access to a mailbox")
    p_rm.add_argument("username")
    p_rm.add_argument("slug")

    args = parser.parse_args()

    cmd = args.command
    if cmd == "list":
        cmd_list()
    elif cmd == "show":
        cmd_show(args.slug)
    elif cmd == "create":
        cmd_create(args.slug, args.name, args.address, args.maildir_path)
    elif cmd == "addresses":
        cmd_addresses(args.mailbox)
    elif cmd == "add-address":
        cmd_add_address(args.slug, args.email, args.primary)
    elif cmd == "disable-address":
        cmd_disable_address(args.email)
    elif cmd == "enable-address":
        cmd_enable_address(args.email)
    elif cmd == "disable-mailbox":
        cmd_disable_mailbox(args.slug)
    elif cmd == "enable-mailbox":
        cmd_enable_mailbox(args.slug)
    elif cmd == "set-imap-password":
        cmd_set_imap_password(args.email)
    elif cmd == "sync-imap-users":
        from worker.dovecot_users import cmd_sync

        cmd_sync(args, DB_PATH)
    elif cmd == "create-operator":
        cmd_create_operator(args.username)
    elif cmd == "set-operator-password":
        cmd_set_operator_password(args.username)
    elif cmd == "list-operators":
        cmd_list_operators()
    elif cmd == "show-operator":
        cmd_show_operator(args.username)
    elif cmd == "disable-operator":
        cmd_disable_operator(args.username)
    elif cmd == "enable-operator":
        cmd_enable_operator(args.username)
    elif cmd == "grant-mailbox":
        cmd_grant_mailbox(args.username, args.slug, args.role)
    elif cmd == "revoke-mailbox":
        cmd_revoke_mailbox(args.username, args.slug)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
