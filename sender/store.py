"""Save outbound email copies to disk and SQLite."""

import hashlib
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow importing from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sender.config import (                           # noqa: E402
    DB_PATH,
    RAW_OUTBOUND_DIR,
    SENT_CUR,
    SENT_MAILDIR_BASE,
    SENT_NEW,
    SENT_TMP,
    log,
)


def ensure_sent_dirs():
    for p in (RAW_OUTBOUND_DIR, SENT_CUR, SENT_NEW, SENT_TMP):
        p.mkdir(parents=True, exist_ok=True)
    (SENT_MAILDIR_BASE / "maildirfolder").write_text("")


def _resolve_sent_cur(master_id):
    """Return Path() to .Sent/cur/ for a given mailbox id. Falls back to master."""
    if master_id == 1:
        return SENT_CUR
    try:
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT maildir_path FROM mailboxes WHERE id=?", (master_id,)
        ).fetchone()
        conn.close()
        if row:
            return Path(row[0]) / ".Sent" / "cur"
    except Exception:
        pass
    return SENT_CUR


OUTBOUND_COLUMNS = [
    "s3_bucket",
    "s3_key",
    "local_raw_path",
    "local_maildir_path",
    "message_id",
    "sender",
    "recipient",
    "cc",
    "bcc",
    "subject",
    "date_header",
    "in_reply_to",
    "references_header",
    "thread_id",
    "ses_spam_verdict",
    "ses_virus_verdict",
    "object_size",
    "s3_last_modified",
    "direction",
    "status",
    "error_message",
    "processed_at",
    "smtp_message_id",
    "sent_at",
    "relay_response",
    "mailbox_id",
]


def save_outbound(
    raw_bytes,
    mail_from,
    rcpt_tos,
    subject="",
    message_id="",
    date_header="",
    in_reply_to="",
    references="",
    thread_id="",
    cc="",
    bcc="",
    status="accepted_by_ses",
    error_message=None,
    relay_response=None,
    smtp_message_id=None,
    mailbox_id=None,
):
    ensure_sent_dirs()

    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    ts = datetime.now(timezone.utc)
    ts_str = ts.isoformat()
    filename = f"{int(ts.timestamp())}.{digest}.eml"

    # ── raw-outbound copy ────────────────────────────────────────────
    raw_path = RAW_OUTBOUND_DIR / filename
    raw_path.write_bytes(raw_bytes)

    # ── Maildir .Sent (fan-out: target + master_copy) ──────────────
    sent_paths = {}  # mb_id -> Path

    # Always include master .Sent
    master_cur = _resolve_sent_cur(master_id=1)
    master_cur.mkdir(parents=True, exist_ok=True)
    sent_paths[1] = master_cur / f"{filename}:2,S"

    # If a specific active mailbox other than master is resolved, add it too
    if mailbox_id and mailbox_id != 1:
        specific_cur = _resolve_sent_cur(master_id=mailbox_id)
        if specific_cur != master_cur:
            specific_cur.mkdir(parents=True, exist_ok=True)
            sent_paths[mailbox_id] = specific_cur / f"{filename}:2,S"

    # Physical copies
    for mb_id, path in sent_paths.items():
        shutil.copy2(raw_path, path)

    # Canonical sent_path: use specific mailbox if available, else master
    sent_path = sent_paths.get(mailbox_id) if (mailbox_id and mailbox_id in sent_paths) else sent_paths[1]

    # ── SQLite ───────────────────────────────────────────────────────
    recipient = ", ".join(rcpt_tos) if rcpt_tos else mail_from
    s3_key = f"outbound/{filename}"
    size = len(raw_bytes)

    values = [
        "",                     # s3_bucket (empty for outbound)
        s3_key,                 # s3_key
        str(raw_path),          # local_raw_path
        str(sent_path),         # local_maildir_path
        message_id or None,
        mail_from or None,      # sender
        recipient or None,      # recipient
        cc or None,
        bcc or None,
        subject or None,
        date_header or None,
        in_reply_to or None,
        references or None,
        thread_id or None,
        None,                   # ses_spam_verdict
        None,                   # ses_virus_verdict
        size,                   # object_size
        None,                   # s3_last_modified
        "outbound",             # direction
        status,                  # status (accepted_by_ses / failed)
        (error_message or "")[:500],
        ts_str,                 # processed_at
        smtp_message_id,
        ts_str,                 # sent_at
        relay_response,
        mailbox_id,
    ]

    assert len(OUTBOUND_COLUMNS) == len(values), (
        f"BUG: {len(OUTBOUND_COLUMNS)} columns, {len(values)} values"
    )

    placeholders = ", ".join(["?"] * len(OUTBOUND_COLUMNS))
    columns_sql = ", ".join(OUTBOUND_COLUMNS)
    sql = f"INSERT OR IGNORE INTO messages ({columns_sql}) VALUES ({placeholders})"

    conn = sqlite3.connect(str(DB_PATH))
    msg_id = None
    try:
        conn.execute(sql, values)
        conn.commit()

        # ── message_mailboxes associations ──────────────────────────
        row = conn.execute(
            "SELECT id FROM messages WHERE s3_key=?", (s3_key,)
        ).fetchone()
        if row:
            msg_id = row[0]
            for mb_id in sent_paths:
                if len(sent_paths) == 1:
                    role = "target"
                elif mb_id == 1:
                    role = "master_copy"
                else:
                    role = "target"
                conn.execute(
                    "INSERT OR IGNORE INTO message_mailboxes (message_id, mailbox_id, role, maildir_path) VALUES (?, ?, ?, ?)",
                    (msg_id, mb_id, role, str(sent_paths[mb_id])),
                )
                log("INFO", f"Created outbound message_mailboxes: msg={msg_id} mb_id={mb_id} role={role}")
            conn.commit()
    except Exception as exc:
        log("ERROR", f"Failed to save outbound metadata: {exc}")
    finally:
        conn.close()
