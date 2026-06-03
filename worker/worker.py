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

# Relative import for bounce detection
try:
    from worker.bounce import parse_dsn, apply_bounce

    _BOUNCE_AVAILABLE = True
except ImportError:
    _BOUNCE_AVAILABLE = False

# Mailbox resolution for inbound messages
try:
    from worker.mailbox_resolver import (
        get_master_id,
        resolve_mailbox_for_inbound,
    )

    _MULTI_MAILBOX = True
except ImportError:
    _MULTI_MAILBOX = False

# ── Import centralized configuration ──────────────────────────────────────
import sys as _sys
_sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (  # noqa: E402
    AWS_REGION,
    BASE_DIR,
    DB_PATH,
    MAILDIR_NEW,
    RAW_EMAILS_DIR as RAW_DIR,
    S3_BUCKET,
    S3_FAILED_PREFIX,
    S3_INCOMING_PREFIX,
    S3_PROCESSED_PREFIX,
    SETUP_NOTIFICATION_KEY,
)

MAILDIR_BASE = str(MAILDIR_NEW.parent)


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
    "mailbox_id",
]


def save_metadata(s3_key, raw_path, maildir_path, headers, obj_meta,
                  status, error_message, mailbox_id=None):
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
        mailbox_id,
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

        # ── multi-mailbox fan-out ────────────────────────────────
        target_id = None
        target_slug = "master"
        master_id = None
        destinations = []

        conn_r = sqlite3.connect(str(DB_PATH)) if _MULTI_MAILBOX else None
        try:
            if conn_r:
                target_id, target_slug = resolve_mailbox_for_inbound(conn_r, headers)
                master_id = get_master_id(conn_r)
        except Exception:
            log("WARN", "Mailbox resolution failed; falling back to master")

        if master_id is None:
            master_id = target_id or 1

        # Build destination list
        if target_id is None:
            destinations.append((master_id, "master", "fallback"))
            log("INFO", f"Resolved inbound: fallback master (no active mailbox) for recipient {headers.get('recipient')}")
        elif target_slug == "master":
            destinations.append((master_id, "master", "target"))
            log("INFO", f"Resolved inbound: master only for recipient {headers.get('recipient')}")
        else:
            destinations.append((target_id, target_slug, "target"))
            # Use configured inbound archive if set, otherwise fall back to master copy
            archive_id = master_id
            archive_slug = "master"
            archive_role = "master_copy"
            if conn_r:
                row = conn_r.execute(
                    "SELECT m.id, m.slug FROM mailboxes m JOIN settings s ON s.value = CAST(m.id AS TEXT) "
                    "WHERE s.key = 'inbound_archive_mailbox_id' AND m.is_active = 1"
                ).fetchone()
                if row and row[0] != target_id:  # Don't duplicate if same as target
                    archive_id, archive_slug = row[0], row[1]
            destinations.append((archive_id, archive_slug, archive_role))
            log("INFO", f"Resolved inbound: {target_slug} + archive {archive_slug} for recipient {headers.get('recipient')}")

        # Deliver to each destination Maildir
        for mb_id, mb_slug, role in destinations:
            mb_maildir = MAILDIR_NEW
            if conn_r:
                row = conn_r.execute(
                    "SELECT maildir_path FROM mailboxes WHERE id=?", (mb_id,)
                ).fetchone()
                if row:
                    mb_maildir = Path(row[0]) / "new"
                    mb_maildir.mkdir(parents=True, exist_ok=True)
            dest_path = mb_maildir / filename
            shutil.copy2(raw_path, dest_path)
            log("INFO", f"Saved inbound copy to mailbox {mb_slug}: {dest_path}")

        # Canonical message row (target as primary mailbox_id)
        canonical_mb_id = target_id if target_id else master_id
        canonical_dest = destinations[0]
        canonical_path = str(
            (Path(conn_r.execute("SELECT maildir_path FROM mailboxes WHERE id=?",
                                 (canonical_dest[0],)).fetchone()[0])
             / "new" / filename)
        ) if conn_r else str(maildir_path)

        save_metadata(
            s3_key=s3_key,
            raw_path=raw_path,
            maildir_path=canonical_path,
            headers=headers,
            obj_meta=obj_meta,
            status="processed",
            error_message=None,
            mailbox_id=canonical_mb_id,
        )

        # Insert message_mailboxes associations
        if conn_r:
            row = conn_r.execute(
                "SELECT id FROM messages WHERE s3_key=?", (s3_key,)
            ).fetchone()
            if row:
                msg_id = row[0]
                for mb_id, mb_slug, role in destinations:
                    mb_row = conn_r.execute(
                        "SELECT maildir_path FROM mailboxes WHERE id=?", (mb_id,)
                    ).fetchone()
                    mm_path = str(Path(mb_row[0]) / "new" / filename) if mb_row else ""
                    conn_r.execute(
                        "INSERT OR IGNORE INTO message_mailboxes (message_id, mailbox_id, role, maildir_path) VALUES (?, ?, ?, ?)",
                        (msg_id, mb_id, role, mm_path),
                    )
                    log("INFO", f"Created message_mailboxes: msg={msg_id} mb={mb_slug} role={role}")
                conn_r.commit()
        if conn_r:
            conn_r.close()

        move_s3_object(s3, s3_key, S3_PROCESSED_PREFIX)

        # ── bounce / DSN detection ────────────────────────────────
        if _BOUNCE_AVAILABLE:
            try:
                import email
                from email import policy as _policy
                from email.parser import BytesParser as _BytesParser

                with open(raw_path, "rb") as _f:
                    _msg = _BytesParser(policy=_policy.default).parse(_f)
                _bounce = parse_dsn(_msg)
                if _bounce:
                    log("INFO", f"DSN/bounce detected: action={_bounce.get('action')} "
                        f"recipient={_bounce.get('final_recipient')} "
                        f"status={_bounce.get('status')}")
                    apply_bounce(_bounce, inbound_s3_key=s3_key)
            except Exception as _bounce_exc:
                log("WARN", f"Bounce processing error (non-fatal): {_bounce_exc}")

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
            # Try to resolve mailbox even on error
            err_mailbox_id = None
            if _MULTI_MAILBOX and headers:
                try:
                    err_conn = sqlite3.connect(str(DB_PATH))
                    err_mailbox_id, _ = resolve_mailbox_for_inbound(err_conn, headers)
                    err_conn.close()
                except Exception:
                    pass

            save_metadata(
                s3_key=s3_key,
                raw_path=raw_path if raw_path.exists() else None,
                maildir_path=maildir_path if maildir_path.exists() else None,
                headers=headers,
                obj_meta=obj_meta,
                status="failed",
                error_message=error_msg,
                mailbox_id=err_mailbox_id,
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
