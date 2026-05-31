#!/usr/bin/env python3
"""
SES → S3 → Maildir Worker

Downloads raw emails from the S3 inbox bucket, parses headers, delivers a
copy to a local Maildir, records metadata in SQLite, and moves the S3 object
to a processed/ (or failed/) prefix.
"""

import boto3
import hashlib
import os
import shutil
import sqlite3
import sys
import traceback
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env (optional — falls back to os.environ)
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "ricardo-vc-ses-mailbox")
S3_INCOMING_PREFIX = os.getenv("S3_INCOMING_PREFIX", "incoming/")
S3_PROCESSED_PREFIX = os.getenv("S3_PROCESSED_PREFIX", "processed/")
S3_FAILED_PREFIX = os.getenv("S3_FAILED_PREFIX", "failed/")

BASE_DIR = Path(os.getenv("BASE_DIR", str(Path.home() / "ses-s3-mailbox")))
RAW_DIR = BASE_DIR / "data" / "raw-emails"
DB_PATH = BASE_DIR / "data" / "mailbox.db"

MAILDIR_BASE = os.getenv(
    "MASTER_MAILDIR",
    str(BASE_DIR / "data" / "maildir" / "master"),
)
MAILDIR_NEW = Path(MAILDIR_BASE) / "new"

SETUP_NOTIFICATION_KEY = f"{S3_INCOMING_PREFIX.rstrip('/')}/AMAZON_SES_SETUP_NOTIFICATION"


def ensure_dirs():
    for p in (RAW_DIR, MAILDIR_NEW):
        p.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def log(level, msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr if level == "ERROR" else sys.stdout
    print(f"[{ts}] [{level}] {msg}", file=stream)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------
def init_db():
    ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH))
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
            cc TEXT,
            bcc TEXT,
            subject TEXT,
            date_header TEXT,
            in_reply_to TEXT,
            references_header TEXT,
            thread_id TEXT,
            ses_spam_verdict TEXT,
            ses_virus_verdict TEXT,
            object_size INTEGER,
            s3_last_modified TEXT,
            direction TEXT DEFAULT 'inbound',
            status TEXT DEFAULT 'processed',
            error_message TEXT,
            processed_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()


def already_processed(s3_key):
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.execute(
        "SELECT 1 FROM messages WHERE s3_key = ? AND status = 'processed'",
        (s3_key,),
    )
    exists = cur.fetchone() is not None
    conn.close()
    return exists


INSERT_COLUMNS = [
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
]


def save_metadata(s3_key, raw_path, maildir_path, headers, obj_meta,
                  status, error_message):
    h = headers or {}
    m = obj_meta or {}

    values = [
        S3_BUCKET,
        s3_key,
        str(raw_path) if raw_path else None,
        str(maildir_path) if maildir_path else None,
        h.get("message_id"),
        h.get("sender"),
        h.get("recipient"),
        h.get("cc"),
        h.get("bcc"),
        h.get("subject"),
        h.get("date_header"),
        h.get("in_reply_to"),
        h.get("references"),
        h.get("thread_id"),
        h.get("ses_spam_verdict"),
        h.get("ses_virus_verdict"),
        m.get("size"),
        m.get("last_modified"),
        "inbound",
        status,
        (error_message or "")[:500],
        datetime.now(timezone.utc).isoformat(),
    ]

    assert len(INSERT_COLUMNS) == len(values), (
        f"BUG: {len(INSERT_COLUMNS)} columns, {len(values)} values"
    )

    placeholders = ", ".join(["?"] * len(INSERT_COLUMNS))
    columns_sql = ", ".join(INSERT_COLUMNS)
    sql = f"INSERT OR IGNORE INTO messages ({columns_sql}) VALUES ({placeholders})"

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(sql, values)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# S3 helpers
# ---------------------------------------------------------------------------
def list_incoming_objects(s3):
    """Generator that yields every object under S3_INCOMING_PREFIX."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=S3_BUCKET, Prefix=S3_INCOMING_PREFIX):
        for obj in page.get("Contents", []):
            yield obj


def dest_key(s3_key, target_prefix):
    """Build target key by replacing the incoming prefix."""
    if not s3_key.startswith(S3_INCOMING_PREFIX):
        raise ValueError(f"Key does not start with incoming prefix: {s3_key}")
    name = s3_key[len(S3_INCOMING_PREFIX):]
    return f"{target_prefix.rstrip('/')}/{name}"


def move_s3_object(s3, s3_key, target_prefix):
    """Copy object to target prefix then delete from source."""
    target = dest_key(s3_key, target_prefix)
    s3.copy_object(
        Bucket=S3_BUCKET,
        CopySource={"Bucket": S3_BUCKET, "Key": s3_key},
        Key=target,
    )
    s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
    log("INFO", f"  Moved s3://{S3_BUCKET}/{s3_key} → s3://{S3_BUCKET}/{target}")


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------
def parse_email_headers(raw_path):
    with open(raw_path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)

    return {
        "message_id": str(msg.get("Message-ID", "")),
        "sender": str(msg.get("From", "")),
        "recipient": str(msg.get("To", "")),
        "cc": str(msg.get("Cc", "")),
        "bcc": str(msg.get("Bcc", "")),
        "subject": str(msg.get("Subject", "")),
        "date_header": str(msg.get("Date", "")),
        "in_reply_to": str(msg.get("In-Reply-To", "")),
        "references": str(msg.get("References", "")),
        "ses_spam_verdict": str(msg.get("X-SES-Spam-Verdict", "")),
        "ses_virus_verdict": str(msg.get("X-SES-Virus-Verdict", "")),
    }


def compute_thread_id(headers):
    references = (headers.get("references") or "").strip()
    in_reply_to = (headers.get("in_reply_to") or "").strip()
    message_id = (headers.get("message_id") or "").strip()

    if references:
        return references.split()[0]
    if in_reply_to:
        return in_reply_to
    if message_id:
        return message_id
    return None


def make_safe_filename(s3_key):
    digest = hashlib.sha256(s3_key.encode()).hexdigest()[:16]
    safe = s3_key.replace("/", "_")
    return f"{digest}_{safe}.eml"


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------
def process_s3_object(s3, s3_key, size=None, last_modified=None):
    """Download and deliver a single S3 object.

    Returns:
        "processed" — success, moved to processed/
        "skipped"   — directory marker, setup notification, or already done
        "failed"    — error handled, moved to failed/

    Raises on transient errors (e.g. cannot move to failed/ → retry).
    """
    if s3_key.endswith("/"):
        log("INFO", f"Skipping directory marker: {s3_key}")
        return "skipped"

    if s3_key == SETUP_NOTIFICATION_KEY:
        log("INFO", f"Ignoring setup notification: {s3_key}")
        return "skipped"

    if already_processed(s3_key):
        log("INFO", f"Already processed: {s3_key}")
        return "skipped"

    filename = make_safe_filename(s3_key)
    raw_path = RAW_DIR / filename
    maildir_path = MAILDIR_NEW / filename

    if last_modified and hasattr(last_modified, "isoformat"):
        last_modified = last_modified.isoformat()

    obj_meta = {
        "size": size,
        "last_modified": last_modified,
    }

    headers = None

    try:
        log("INFO", f"Downloading: {s3_key} ({size} bytes)")

        s3.download_file(S3_BUCKET, s3_key, str(raw_path))

        headers = parse_email_headers(raw_path)
        headers["thread_id"] = compute_thread_id(headers)

        shutil.copy2(raw_path, maildir_path)

        save_metadata(
            s3_key=s3_key,
            raw_path=raw_path,
            maildir_path=maildir_path,
            headers=headers,
            obj_meta=obj_meta,
            status="processed",
            error_message=None,
        )

        move_s3_object(s3, s3_key, S3_PROCESSED_PREFIX)

        log("INFO", f"OK  {s3_key}")
        log("INFO", f"    From:    {headers.get('sender')}")
        log("INFO", f"    To:      {headers.get('recipient')}")
        log("INFO", f"    Subject: {headers.get('subject')}")
        log("INFO", f"    Thread:  {headers.get('thread_id')}")
        log("INFO", f"    Spam:    {headers.get('ses_spam_verdict')}")
        log("INFO", f"    Virus:   {headers.get('ses_virus_verdict')}")
        return "processed"

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        log("ERROR", f"FAIL {s3_key} — {error_msg}")
        traceback.print_exc(file=sys.stderr)

        try:
            save_metadata(
                s3_key=s3_key,
                raw_path=raw_path if raw_path.exists() else None,
                maildir_path=maildir_path if maildir_path.exists() else None,
                headers=headers,
                obj_meta=obj_meta,
                status="failed",
                error_message=error_msg,
            )
        except Exception as meta_exc:
            log("ERROR", f"  Could not save error metadata: {meta_exc}")

        # Move to failed/ — if this fails let it propagate (transient error)
        move_s3_object(s3, s3_key, S3_FAILED_PREFIX)
        return "failed"


def process_one(s3, obj):
    """Thin wrapper for S3 polling — unpacks the S3 list_objects_v2 dict."""
    return process_s3_object(
        s3,
        obj["Key"],
        size=obj.get("Size"),
        last_modified=obj.get("LastModified"),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    log("INFO", "Worker started")
    ensure_dirs()
    init_db()

    session = boto3.Session(region_name=AWS_REGION)
    s3 = session.client("s3")

    objects = list(list_incoming_objects(s3))

    if not objects:
        log("INFO", "No objects found in incoming/")
        return

    log("INFO", f"Found {len(objects)} object(s) in incoming/")

    processed = 0
    failed = 0
    skipped = 0

    for obj in objects:
        s3_key = obj["Key"]

        if s3_key.endswith("/"):
            skipped += 1
            continue

        if s3_key == SETUP_NOTIFICATION_KEY:
            log("INFO", f"Ignoring setup notification: {s3_key}")
            skipped += 1
            continue

        if already_processed(s3_key):
            log("INFO", f"Already processed (moving to processed/): {s3_key}")
            try:
                move_s3_object(s3, s3_key, S3_PROCESSED_PREFIX)
            except Exception as exc:
                log("ERROR", f"  Could not move {s3_key} to processed/: {exc}")
            skipped += 1
            continue

        try:
            result = process_one(s3, obj)
            if result == "processed":
                processed += 1
            elif result == "failed":
                failed += 1
            else:
                skipped += 1
        except Exception:
            failed += 1

    log("INFO", f"Worker finished — {processed} processed, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    main()
