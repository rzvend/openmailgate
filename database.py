"""Database access layer — centralized connection helper and read-only queries.

All modules should use ``get_conn()`` for SQLite connections instead of
calling ``sqlite3.connect(DB_PATH)`` directly.
"""

import sqlite3
import sys
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
