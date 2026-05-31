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
    status="sent",
    error_message=None,
    relay_response=None,
    smtp_message_id=None,
):
    ensure_sent_dirs()

    digest = hashlib.sha256(raw_bytes).hexdigest()[:16]
    ts = datetime.now(timezone.utc)
    ts_str = ts.isoformat()
    filename = f"{int(ts.timestamp())}.{digest}.eml"

    # ── raw-outbound copy ────────────────────────────────────────────
    raw_path = RAW_OUTBOUND_DIR / filename
    raw_path.write_bytes(raw_bytes)

    # ── Maildir .Sent ────────────────────────────────────────────────
    sent_path = SENT_CUR / f"{filename}:2,S"
    shutil.copy2(raw_path, sent_path)

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
        status,                 # status (sent / failed)
        (error_message or "")[:500],
        ts_str,                 # processed_at
        smtp_message_id,
        ts_str,                 # sent_at
        relay_response,
    ]

    assert len(OUTBOUND_COLUMNS) == len(values), (
        f"BUG: {len(OUTBOUND_COLUMNS)} columns, {len(values)} values"
    )

    placeholders = ", ".join(["?"] * len(OUTBOUND_COLUMNS))
    columns_sql = ", ".join(OUTBOUND_COLUMNS)
    sql = f"INSERT OR IGNORE INTO messages ({columns_sql}) VALUES ({placeholders})"

    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(sql, values)
        conn.commit()
    except Exception as exc:
        log("ERROR", f"Failed to save outbound metadata: {exc}")
    finally:
        conn.close()
