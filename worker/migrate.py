#!/usr/bin/env python3
"""Apply incremental schema changes to mailbox.db without losing data.

Safe to run multiple times — only adds columns that don't exist yet.
"""

import sqlite3
import sys
from pathlib import Path

DB_PATH = Path.home() / "ses-s3-mailbox" / "data" / "mailbox.db"

NEW_COLUMNS = [
    ("cc", "TEXT"),
    ("bcc", "TEXT"),
    ("in_reply_to", "TEXT"),
    ("references_header", "TEXT"),
    ("thread_id", "TEXT"),
    ("object_size", "INTEGER"),
    ("s3_last_modified", "TEXT"),
    ("direction", "TEXT DEFAULT 'inbound'"),
    ("status", "TEXT DEFAULT 'processed'"),
    ("error_message", "TEXT"),
    ("smtp_message_id", "TEXT"),
    ("sent_at", "TEXT"),
    ("relay_response", "TEXT"),
    ("delivery_status", "TEXT"),
    ("delivery_action", "TEXT"),
    ("diagnostic_code", "TEXT"),
    ("bounced_at", "TEXT"),
    ("delivered_at", "TEXT"),
    ("mailbox_id", "INTEGER"),
]


def ensure_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            s3_bucket TEXT NOT NULL,
            s3_key TEXT NOT NULL UNIQUE,
            local_raw_path TEXT NOT NULL,
            local_maildir_path TEXT NOT NULL,
            message_id TEXT,
            sender TEXT,
            recipient TEXT,
            subject TEXT,
            date_header TEXT,
            ses_spam_verdict TEXT,
            ses_virus_verdict TEXT,
            processed_at TEXT NOT NULL
        )
    """)
    conn.commit()


def existing_columns(conn):
    rows = conn.execute("PRAGMA table_info('messages')").fetchall()
    return {row[1] for row in rows}


def add_column(conn, name, col_def):
    sql = f"ALTER TABLE messages ADD COLUMN {name} {col_def}"
    conn.execute(sql)
    conn.commit()
    print(f"  + added column: {name} ({col_def})")


def main():
    db = DB_PATH
    if not db.exists():
        print(f"Database not found: {db}")
        print("Run worker.py first to create it, then re-run this script.")
        sys.exit(1)

    conn = sqlite3.connect(str(db))

    print("Ensuring table 'messages' exists...")
    ensure_table(conn)

    columns = existing_columns(conn)
    print(f"  current columns ({len(columns)}): {', '.join(sorted(columns))}")

    added = 0
    for name, col_def in NEW_COLUMNS:
        if name in columns:
            print(f"  - already exists: {name}")
        else:
            try:
                add_column(conn, name, col_def)
                added += 1
            except sqlite3.OperationalError as exc:
                print(f"  ! failed to add {name}: {exc}")

    conn.close()
    print(f"\nDone — {added} column(s) added.")

    # ── message_events table ──────────────────────────────────────────
    conn = sqlite3.connect(str(db))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            event_type TEXT NOT NULL,
            event_time TEXT NOT NULL,
            source TEXT,
            final_recipient TEXT,
            action TEXT,
            status_code TEXT,
            diagnostic_code TEXT,
            related_message_id TEXT,
            raw_message_id TEXT,
            metadata_json TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(message_id) REFERENCES messages(id)
        )
    """)
    conn.commit()
    print("Ensured message_events table exists.")
    conn.close()

    # ── multi-mailbox tables ──────────────────────────────────────────
    conn = sqlite3.connect(str(db))

    conn.execute("""
        CREATE TABLE IF NOT EXISTS mailboxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            maildir_path TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT
        )
    """)
    print("Ensured mailboxes table exists.")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS email_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mailbox_id INTEGER NOT NULL,
            address TEXT NOT NULL UNIQUE,
            is_primary INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT,
            FOREIGN KEY(mailbox_id) REFERENCES mailboxes(id)
        )
    """)
    print("Ensured email_addresses table exists.")

    # ── email_addresses.imap_password_hash ────────────────────────────
    ea_cols = {
        r[1]
        for r in conn.execute("PRAGMA table_info('email_addresses')").fetchall()
    }
    if "imap_password_hash" not in ea_cols:
        conn.execute("ALTER TABLE email_addresses ADD COLUMN imap_password_hash TEXT")
        print("  + added column imap_password_hash to email_addresses")
    else:
        print("  - imap_password_hash already exists")

    # ── seed master mailbox ───────────────────────────────────────────
    import os
    master_maildir = os.getenv(
        "MASTER_MAILDIR",
        str(Path.home() / "ses-s3-mailbox" / "data" / "maildir" / "master"),
    )
    row = conn.execute(
        "SELECT id FROM mailboxes WHERE slug = ?", ("master",)
    ).fetchone()
    if row:
        master_id = row[0]
        print(f"  - master mailbox already exists (id={master_id})")
    else:
        cur = conn.execute(
            "INSERT INTO mailboxes (name, slug, maildir_path) VALUES (?, ?, ?)",
            ("Master", "master", master_maildir),
        )
        master_id = cur.lastrowid
        print(f"  + created master mailbox (id={master_id}, path={master_maildir})")

    # ── seed default address ──────────────────────────────────────────
    default_addr = "teste@inbox.ricardo.vc"
    row = conn.execute(
        "SELECT id FROM email_addresses WHERE address = ?", (default_addr,)
    ).fetchone()
    if row:
        print(f"  - default address already exists ({default_addr})")
    else:
        conn.execute(
            "INSERT INTO email_addresses (mailbox_id, address, is_primary, is_active) VALUES (?, ?, 1, 1)",
            (master_id, default_addr),
        )
        print(f"  + linked {default_addr} → master mailbox (id={master_id})")

    # ── backfill existing messages with NULL mailbox_id ───────────────
    updated = conn.execute(
        "UPDATE messages SET mailbox_id = ? WHERE mailbox_id IS NULL", (master_id,)
    ).rowcount
    if updated:
        print(f"Backfilled {updated} existing message(s) with mailbox_id={master_id}")

    # ── message_mailboxes table (fan-out / N:N) ──────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message_mailboxes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER NOT NULL,
            mailbox_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            maildir_path TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY(message_id) REFERENCES messages(id),
            FOREIGN KEY(mailbox_id) REFERENCES mailboxes(id),
            UNIQUE(message_id, mailbox_id)
        )
    """)
    print("Ensured message_mailboxes table exists.")

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_mm_message_id
        ON message_mailboxes(message_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_mm_mailbox_id
        ON message_mailboxes(mailbox_id)
    """)

    # Backfill: create an association for every existing message
    backfilled = conn.execute("""
        INSERT OR IGNORE INTO message_mailboxes (message_id, mailbox_id, role, maildir_path)
        SELECT id, mailbox_id, 'legacy', local_maildir_path
        FROM messages
        WHERE mailbox_id IS NOT NULL
    """).rowcount
    if backfilled:
        print(f"Backfilled {backfilled} message_mailboxes association(s)")

    # ── operators and collaboration ───────────────────────────────────
    conn.execute("""
        CREATE TABLE IF NOT EXISTS operators (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    print("Ensured operators table exists.")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS operator_mailboxes (
            operator_id INTEGER NOT NULL,
            mailbox_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (operator_id, mailbox_id),
            FOREIGN KEY (operator_id) REFERENCES operators(id),
            FOREIGN KEY (mailbox_id) REFERENCES mailboxes(id)
        )
    """)
    print("Ensured operator_mailboxes table exists.")

    # ── messages workflow columns ──────────────────────────────────────
    msg_cols = {
        r[1]
        for r in conn.execute("PRAGMA table_info('messages')").fetchall()
    }
    for col, cdef in [
        ("assigned_to", "INTEGER REFERENCES operators(id)"),
        ("internal_status", "TEXT DEFAULT 'open'"),
    ]:
        if col not in msg_cols:
            conn.execute(f"ALTER TABLE messages ADD COLUMN {col} {cdef}")
            print(f"  + added column {col} to messages")
        else:
            print(f"  - {col} already exists in messages")

    conn.commit()
    conn.close()
    print("Multi-mailbox migration complete.")


if __name__ == "__main__":
    main()
