"""Database access layer — centralized connection helper and read-only queries.

All modules should use ``get_conn()`` for SQLite connections instead of
calling ``sqlite3.connect(DB_PATH)`` directly.
"""

import re
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
        "SELECT id, mailbox_id, address, is_primary, is_active, created_at "
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


def ensure_maildir_structure(base_path):
    """Create Maildir directory tree under base_path."""
    for sub in (
        "cur", "new", "tmp",
        ".Sent/cur", ".Sent/new", ".Sent/tmp",
        ".Trash/cur", ".Trash/new", ".Trash/tmp",
        ".SentDuplicates/cur", ".SentDuplicates/new", ".SentDuplicates/tmp",
    ):
        (base_path / sub).mkdir(parents=True, exist_ok=True)
    (base_path / "maildirfolder").write_text("")


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
