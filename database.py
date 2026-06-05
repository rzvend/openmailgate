"""Database access layer — centralized connection helper and read-only queries.

All modules should use ``get_conn()`` for SQLite connections instead of
calling ``sqlite3.connect(DB_PATH)`` directly.
"""

import re
import os
import sqlite3
import sys
from pathlib import Path
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DB_PATH  # noqa: E402


def get_conn():
    """Return a new SQLite connection to the project database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ── read-only queries (for API/dashboard) ────────────────────────────────


def get_mailboxes():
    """Return all mailboxes ordered by id."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM mailboxes ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mailbox_by_slug(slug):
    """Return a single mailbox dict or None."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM mailboxes WHERE slug = ?", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_messages_by_mailbox(mailbox_id, limit=50, offset=0):
    """Return messages for a mailbox via message_mailboxes join, newest first."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT msg.*, mm.role AS mm_role
           FROM messages msg
           JOIN message_mailboxes mm ON mm.message_id = msg.id
           WHERE mm.mailbox_id = ?
           ORDER BY msg.processed_at DESC, msg.id DESC
           LIMIT ? OFFSET ?""",
        (mailbox_id, limit, offset),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_message(message_id):
    """Return a single message dict or None."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM messages WHERE id = ?", (message_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_message_events(message_id):
    """Return events for a message, oldest first."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM message_events WHERE message_id = ? ORDER BY id",
        (message_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_message_mailboxes(message_id):
    """Return mailbox associations for a message."""
    conn = get_conn()
    rows = conn.execute(
        """SELECT mm.*, m.slug, m.name
           FROM message_mailboxes mm
           JOIN mailboxes m ON m.id = mm.mailbox_id
           WHERE mm.message_id = ?""",
        (message_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_message_notes(message_id):
    """Return notes (message_events with event_type='note') for a message."""
    return [
        e for e in get_message_events(message_id)
        if e.get("event_type") == "note"
    ]


def get_mailbox_addresses(mailbox_id):
    """Return email addresses for a mailbox (without password hash)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, mailbox_id, address, is_primary, is_active, created_at, "
        "CASE WHEN imap_password_hash IS NOT NULL AND imap_password_hash != '' THEN 1 ELSE 0 END AS has_imap_password "
        "FROM email_addresses WHERE mailbox_id = ? ORDER BY id",
        (mailbox_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_mailbox_counts(mailbox_id):
    """Return (total, inbound, outbound) counts for a mailbox."""
    conn = get_conn()
    total = conn.execute(
        "SELECT COUNT(*) FROM message_mailboxes WHERE mailbox_id = ?", (mailbox_id,)
    ).fetchone()[0]
    inbound = conn.execute(
        "SELECT COUNT(*) FROM message_mailboxes mm "
        "JOIN messages msg ON msg.id = mm.message_id "
        "WHERE mm.mailbox_id = ? AND msg.direction = 'inbound'",
        (mailbox_id,),
    ).fetchone()[0]
    outbound = conn.execute(
        "SELECT COUNT(*) FROM message_mailboxes mm "
        "JOIN messages msg ON msg.id = mm.message_id "
        "WHERE mm.mailbox_id = ? AND msg.direction = 'outbound'",
        (mailbox_id,),
    ).fetchone()[0]
    conn.close()
    return total, inbound, outbound


def get_operators():
    """Return all operators (without password_hash)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT o.id, o.username, o.is_active, o.created_at, "
        "(SELECT COUNT(*) FROM operator_mailboxes WHERE operator_id = o.id) AS mailbox_count "
        "FROM operators o ORDER BY o.id"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_operator_by_username(username):
    """Return a single operator dict (without password_hash) or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT o.id, o.username, o.is_active, o.created_at, "
        "(SELECT COUNT(*) FROM operator_mailboxes WHERE operator_id = o.id) AS mailbox_count "
        "FROM operators o WHERE o.username = ?",
        (username,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_operator_mailboxes(operator_id):
    """Return mailbox grants for an operator."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT m.id AS mailbox_id, m.slug, m.name, om.role "
        "FROM operator_mailboxes om "
        "JOIN mailboxes m ON m.id = om.mailbox_id "
        "WHERE om.operator_id = ? ORDER BY m.slug",
        (operator_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_operator_name(operator_id):
    """Return username for an operator id, or None."""
    if operator_id is None:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT username FROM operators WHERE id = ?", (operator_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else None


# ── write helpers (admin) ────────────────────────────────────────────────


_DOVECOT_UID = int(os.getenv("DOVECOT_UID", "1000"))
_DOVECOT_GID = int(os.getenv("DOVECOT_GID", "1000"))


def ensure_maildir_structure(base_path):
    """Create Maildir directory tree under base_path."""
    dirs = (
        "cur", "new", "tmp",
        ".Sent/cur", ".Sent/new", ".Sent/tmp",
        ".Drafts/cur", ".Drafts/new", ".Drafts/tmp",
        ".Trash/cur", ".Trash/new", ".Trash/tmp",
        ".Junk/cur", ".Junk/new", ".Junk/tmp",
        ".Archive/cur", ".Archive/new", ".Archive/tmp",
        ".SentDuplicates/cur", ".SentDuplicates/new", ".SentDuplicates/tmp",
    )
    for sub in dirs:
        p = (base_path / sub)
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.chown(p, _DOVECOT_UID, _DOVECOT_GID)
        except OSError:
            pass

    # Maildir++ folder markers — one per subfolder, plus root
    folders = ("", ".Sent", ".Drafts", ".Trash", ".Junk", ".Archive", ".SentDuplicates")
    for folder in folders:
        mf = base_path / folder / "maildirfolder"
        if not mf.exists():
            mf.write_text("")
        try:
            os.chown(mf, _DOVECOT_UID, _DOVECOT_GID)
        except OSError:
            pass


def create_mailbox_with_address(slug, name, address, maildir_parent):
    """Create a mailbox + primary address in a single transaction.

    Returns dict with mailbox id, slug, name, maildir_path or raises ValueError.
    """
    maildir_base = Path(maildir_parent)
    maildir_path = maildir_base / slug
    if not str(maildir_path).startswith(str(maildir_base)):
        raise ValueError("mailbox path traversal denied")

    if not re.match(r"^[a-z0-9_-]+$", slug):
        raise ValueError("invalid slug")

    conn = get_conn()
    try:
        dup_slug = conn.execute(
            "SELECT id FROM mailboxes WHERE slug = ?", (slug,)
        ).fetchone()
        if dup_slug:
            raise ValueError("mailbox slug already exists")

        dup_addr = conn.execute(
            "SELECT id FROM email_addresses WHERE address = ?", (address.lower(),)
        ).fetchone()
        if dup_addr:
            raise ValueError("email address already exists")

        ensure_maildir_structure(maildir_path)

        conn.execute(
            "INSERT INTO mailboxes (name, slug, maildir_path) VALUES (?, ?, ?)",
            (name.strip(), slug, str(maildir_path)),
        )
        mb_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

        conn.execute(
            "INSERT INTO email_addresses (mailbox_id, address, is_primary, is_active) VALUES (?, ?, 1, 1)",
            (mb_id, address.lower().strip()),
        )
        conn.commit()
        return {"id": mb_id, "slug": slug, "name": name, "maildir_path": str(maildir_path)}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_email_address(address_id):
    """Return address data (without hash) for display, or None."""
    conn = get_conn()
    row = conn.execute(
        "SELECT e.id, e.address, e.mailbox_id, e.is_primary, e.is_active, "
        "m.slug AS mailbox_slug, m.name AS mailbox_name, "
        "CASE WHEN e.imap_password_hash IS NOT NULL AND e.imap_password_hash != '' THEN 1 ELSE 0 END AS has_imap_password "
        "FROM email_addresses e JOIN mailboxes m ON m.id = e.mailbox_id WHERE e.id = ?",
        (address_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_email_address_imap_password_hash(address_id, password_hash):
    """Set the IMAP password hash for an address."""
    conn = get_conn()
    conn.execute(
        "UPDATE email_addresses SET imap_password_hash = ? WHERE id = ?",
        (password_hash, address_id),
    )
    conn.commit()
    conn.close()


def set_mailbox_active(slug, active):
    """Set is_active on a mailbox. Returns dict or None."""
    conn = get_conn()
    conn.execute("UPDATE mailboxes SET is_active = ? WHERE slug = ?", (int(active), slug))
    row = conn.execute("SELECT id, slug, name, is_active FROM mailboxes WHERE slug = ?", (slug,)).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def set_email_address_active(address_id, active):
    """Set is_active on an email address. Returns dict or None."""
    conn = get_conn()
    conn.execute("UPDATE email_addresses SET is_active = ? WHERE id = ?", (int(active), address_id))
    row = conn.execute(
        "SELECT e.id, e.address, e.mailbox_id, e.is_active, m.slug AS mailbox_slug "
        "FROM email_addresses e JOIN mailboxes m ON m.id = e.mailbox_id WHERE e.id = ?",
        (address_id,),
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


# ── operator write helpers ─────────────────────────────────────────────


def create_operator(username, password_hash, active=True):
    """Create an operator. Returns dict or raises ValueError."""
    conn = get_conn()
    dup = conn.execute("SELECT id FROM operators WHERE username = ?", (username,)).fetchone()
    if dup:
        conn.close()
        raise ValueError("operator username already exists")
    conn.execute(
        "INSERT INTO operators (username, password_hash, is_active) VALUES (?, ?, ?)",
        (username, password_hash, int(active)),
    )
    op_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return {"id": op_id, "username": username, "is_active": int(active)}


def get_operator_detail(username):
    """Return operator detail (without password_hash) + permissions + mailbox count."""
    conn = get_conn()
    row = conn.execute(
        "SELECT id, username, is_active, created_at FROM operators WHERE username = ?", (username,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    op = dict(row)
    perms = conn.execute(
        "SELECT m.id AS mailbox_id, m.slug, m.name, om.role "
        "FROM operator_mailboxes om JOIN mailboxes m ON m.id = om.mailbox_id "
        "WHERE om.operator_id = ? ORDER BY m.slug", (op["id"],)
    ).fetchall()
    op["mailboxes"] = [dict(p) for p in perms]
    conn.close()
    return op


def count_active_operators():
    conn = get_conn()
    n = conn.execute("SELECT COUNT(*) FROM operators WHERE is_active = 1").fetchone()[0]
    conn.close()
    return n


def set_operator_active(username, active):
    """Set is_active on an operator. Returns dict or None."""
    conn = get_conn()
    conn.execute("UPDATE operators SET is_active = ? WHERE username = ?", (int(active), username))
    row = conn.execute(
        "SELECT id, username, is_active FROM operators WHERE username = ?", (username,)
    ).fetchone()
    conn.commit()
    conn.close()
    return dict(row) if row else None


def update_operator_password_hash(username, password_hash):
    conn = get_conn()
    conn.execute("UPDATE operators SET password_hash = ? WHERE username = ?", (password_hash, username))
    conn.commit()
    conn.close()


def grant_operator_mailbox(username, mailbox_id, role):
    conn = get_conn()
    op = conn.execute("SELECT id FROM operators WHERE username = ?", (username,)).fetchone()
    if not op:
        conn.close()
        raise ValueError("operator not found")
    conn.execute(
        "INSERT INTO operator_mailboxes (operator_id, mailbox_id, role) VALUES (?, ?, ?) "
        "ON CONFLICT(operator_id, mailbox_id) DO UPDATE SET role = excluded.role",
        (op[0], mailbox_id, role),
    )
    conn.commit()
    conn.close()


def revoke_operator_mailbox(username, mailbox_id):
    conn = get_conn()
    op = conn.execute("SELECT id FROM operators WHERE username = ?", (username,)).fetchone()
    if not op:
        conn.close()
        raise ValueError("operator not found")
    conn.execute("DELETE FROM operator_mailboxes WHERE operator_id = ? AND mailbox_id = ?",
                 (op[0], mailbox_id))
    conn.commit()
    conn.close()


# ── settings / catch-all ───────────────────────────────────────────────


def get_setting(key):
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else None


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = datetime('now')",
        (key, str(value)),
    )
    conn.commit()
    conn.close()


def delete_setting(key):
    conn = get_conn()
    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    conn.commit()
    conn.close()


def get_catch_all_mailbox():
    mb_id = get_setting("catch_all_mailbox_id")
    if not mb_id:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT id, slug, name, maildir_path, is_active FROM mailboxes WHERE id = ? AND is_active = 1",
        (int(mb_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_catch_all_mailbox(mailbox_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, slug, name, is_active FROM mailboxes WHERE id = ?", (mailbox_id,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    mb = dict(row)
    if not mb["is_active"]:
        conn.close()
        return None
    set_setting("catch_all_mailbox_id", mailbox_id)
    conn.close()
    return mb


def clear_catch_all_mailbox():
    delete_setting("catch_all_mailbox_id")


# ── archive / audit copy mailboxes ─────────────────────────────────────


def get_inbound_archive_mailbox():
    mb_id = get_setting("inbound_archive_mailbox_id")
    if not mb_id:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT id, slug, name, maildir_path, is_active FROM mailboxes WHERE id = ? AND is_active = 1",
        (int(mb_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_inbound_archive_mailbox(mailbox_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, is_active FROM mailboxes WHERE id = ?", (mailbox_id,)
    ).fetchone()
    if not row or not row[1]:
        conn.close()
        return None
    set_setting("inbound_archive_mailbox_id", mailbox_id)
    conn.close()
    return {"id": row[0], "is_active": row[1]}


def clear_inbound_archive_mailbox():
    delete_setting("inbound_archive_mailbox_id")


def get_outbound_archive_mailbox():
    mb_id = get_setting("outbound_archive_mailbox_id")
    if not mb_id:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT id, slug, name, maildir_path, is_active FROM mailboxes WHERE id = ? AND is_active = 1",
        (int(mb_id),),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def set_outbound_archive_mailbox(mailbox_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT id, is_active FROM mailboxes WHERE id = ?", (mailbox_id,)
    ).fetchone()
    if not row or not row[1]:
        conn.close()
        return None
    set_setting("outbound_archive_mailbox_id", mailbox_id)
    conn.close()
    return {"id": row[0], "is_active": row[1]}


def clear_outbound_archive_mailbox():
    delete_setting("outbound_archive_mailbox_id")
