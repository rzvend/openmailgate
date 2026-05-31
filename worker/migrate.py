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


if __name__ == "__main__":
    main()
