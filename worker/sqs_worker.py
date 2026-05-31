#!/usr/bin/env python3
"""
SES → S3 → SQS → Maildir Worker (Long-Polling Daemon)

Listens on an SQS queue for S3 ObjectCreated events, downloads raw emails
from the S3 inbox bucket, delivers a copy to a local Maildir, records
metadata in SQLite, and moves the S3 object to processed/ (or failed/).

Designed to run as a long-lived systemd service.  The timer-based S3 polling
in worker.py remains available as a manual fallback.
"""

import os
import sys
from pathlib import Path

# ── load .env *before* any other project imports ──────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

try:
    from dotenv import load_dotenv

    loaded = load_dotenv(ENV_PATH, override=True)
except ImportError:
    loaded = False
    sys.stderr.write(
        "WARNING: python-dotenv not installed — run: pip install python-dotenv\n"
    )

if not ENV_PATH.exists():
    sys.stderr.write(f"WARNING: .env not found at {ENV_PATH}\n")

# ── SQS configuration (read from env now that .env is loaded) ─────────────
SQS_QUEUE_URL = os.getenv("SQS_QUEUE_URL", "")
SQS_WAIT_TIME = int(os.getenv("SQS_WAIT_TIME_SECONDS", "20"))
SQS_MAX_MESSAGES = int(os.getenv("SQS_MAX_MESSAGES", "10"))

# ── make worker package importable ────────────────────────────────────────
sys.path.insert(0, str(PROJECT_ROOT))

import json                      # noqa: E402
import signal                    # noqa: E402
from urllib.parse import unquote_plus  # noqa: E402

import boto3                     # noqa: E402

from worker.worker import (      # noqa: E402
    AWS_REGION,
    S3_BUCKET,
    S3_INCOMING_PREFIX,
    already_processed,
    ensure_dirs,
    init_db,
    log,
    move_s3_object,
    process_s3_object,
)

# ── graceful shutdown ──────────────────────────────────────────────────────
_shutdown = False


def _on_signal(signum, _frame):
    global _shutdown
    name = signal.Signals(signum).name
    log("INFO", f"Received {name}, shutting down gracefully...")
    _shutdown = True


signal.signal(signal.SIGTERM, _on_signal)
signal.signal(signal.SIGINT, _on_signal)


# ── SQS helpers ────────────────────────────────────────────────────────────
def extract_s3_records(body):
    """Parse an SQS message body and return a list of relevant S3 event dicts.

    Each dict has keys: ``bucket``, ``key``, ``size``, ``event_name``.
    Keys are URL-decoded.  Non-S3 events, wrong buckets, and keys outside
    the incoming prefix are silently ignored.
    """
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        log("ERROR", "Invalid JSON in SQS message body")
        return []

    records = []

    for rec in data.get("Records", []):
        if rec.get("eventSource") != "aws:s3":
            continue

        s3_info = rec.get("s3", {})
        bucket = s3_info.get("bucket", {}).get("name", "")
        obj_info = s3_info.get("object", {})
        raw_key = obj_info.get("key", "")
        key = unquote_plus(raw_key) if raw_key else ""
        size = obj_info.get("size")
        event_name = rec.get("eventName", "")

        if bucket and bucket != S3_BUCKET:
            log("INFO", f"Ignoring event for bucket '{bucket}' (expected '{S3_BUCKET}')")
            continue

        if not key.startswith(S3_INCOMING_PREFIX):
            log("INFO", f"Ignoring key outside incoming/: {key}")
            continue

        records.append(
            {
                "bucket": bucket or S3_BUCKET,
                "key": key,
                "size": size,
                "event_name": event_name,
            }
        )

    return records


def handle_sqs_message(sqs, s3, msg):
    """Process every S3 record inside one SQS message.

    Deletes the message *only* when every record was handled (including
    graceful failures that moved the object to failed/).  If any record
    raises a transient exception the message is left on the queue for
    automatic retry.
    """
    receipt = msg["ReceiptHandle"]
    msg_id = msg.get("MessageId", "?")

    try:
        records = extract_s3_records(msg.get("Body", ""))
    except Exception as exc:
        log("ERROR", f"[{msg_id}] Failed to parse body: {exc}")
        _delete(sqs, receipt)
        return

    if not records:
        log("INFO", f"[{msg_id}] No relevant S3 records — deleting")
        _delete(sqs, receipt)
        return

    all_handled = True

    for rec in records:
        s3_key = rec["key"]
        log("INFO", f"[{msg_id}] Processing {s3_key} (event: {rec['event_name']})")

        try:
            result = process_s3_object(
                s3,
                s3_key,
                size=rec.get("size"),
            )
            log("INFO", f"[{msg_id}] Result for {s3_key}: {result}")

        except Exception as exc:
            log("ERROR", f"[{msg_id}] Transient error for {s3_key}: {exc}")
            all_handled = False
            break  # leave the message for retry

    if all_handled:
        _delete(sqs, receipt)
    else:
        log("WARNING", f"[{msg_id}] Not deleted — transient error, will retry")


def _delete(sqs, receipt):
    try:
        sqs.delete_message(QueueUrl=SQS_QUEUE_URL, ReceiptHandle=receipt)
    except Exception as exc:
        log("ERROR", f"Failed to delete SQS message: {exc}")


# ── main loop ──────────────────────────────────────────────────────────────
def main():
    if not SQS_QUEUE_URL:
        log("ERROR", f"SQS_QUEUE_URL is not set. Checked: {ENV_PATH}")
        if not loaded:
            log("ERROR", "python-dotenv is not installed — run: pip install python-dotenv")
        if not ENV_PATH.exists():
            log("ERROR", f".env file not found at: {ENV_PATH}")
        sys.exit(1)

    log("INFO", "SQS worker started")
    ensure_dirs()
    init_db()

    session = boto3.Session(region_name=AWS_REGION)
    s3 = session.client("s3")
    sqs = session.client("sqs")

    log("INFO", f"Queue: {SQS_QUEUE_URL}")
    log("INFO", f"Wait: {SQS_WAIT_TIME}s  Max messages: {SQS_MAX_MESSAGES}")

    while not _shutdown:
        try:
            response = sqs.receive_message(
                QueueUrl=SQS_QUEUE_URL,
                MaxNumberOfMessages=SQS_MAX_MESSAGES,
                WaitTimeSeconds=SQS_WAIT_TIME,
                AttributeNames=["All"],
                MessageAttributeNames=["All"],
            )
        except Exception as exc:
            log("ERROR", f"SQS receive_message failed: {exc}")
            _shutdown_wait(10)
            continue

        messages = response.get("Messages", [])

        if messages:
            log("INFO", f"Received {len(messages)} message(s)")

        for msg in messages:
            if _shutdown:
                break
            handle_sqs_message(sqs, s3, msg)

    log("INFO", "SQS worker stopped")


def _shutdown_wait(seconds):
    """Sleep in small chunks so we still react to shutdown signals."""
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline and not _shutdown:
        time.sleep(0.5)


if __name__ == "__main__":
    main()
