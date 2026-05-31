#!/usr/bin/env python3
"""DSN / bounce detection and outbound status update.

Parses incoming Delivery Status Notification emails, extracts failure
details, matches the original outbound message, updates its status to
'bounced', and inserts a row into message_events for audit.
"""

import sqlite3
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=True)
except ImportError:
    pass

import os

DB_PATH = Path(os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "mailbox.db")))


# ── logging ──────────────────────────────────────────────────────────────
def log(level, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr if level == "ERROR" else sys.stdout
    print(f"[{ts}] [{level}] {msg}", file=stream)


# ── DSN parser ───────────────────────────────────────────────────────────
def parse_dsn(msg):
    """Check if *msg* is a Delivery Status Notification and extract structured data.

    Returns a dict or ``None`` if the message is not a bounce.
    """
    content_type = msg.get_content_type()

    # Fast check: multipart/report is the standard bounce container
    if content_type != "multipart/report":
        return None

    # Confirm by looking for message/delivery-status part
    ds_part = None
    rfc822_part = None
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "message/delivery-status" and ds_part is None:
            ds_part = part
        elif ct == "message/rfc822" and rfc822_part is None:
            rfc822_part = part

    if ds_part is None:
        # Also accept if From is MAILER-DAEMON as fallback
        if "MAILER-DAEMON" in (msg.get("From") or ""):
            pass  # partial bounce, continue
        else:
            return None

    # ── parse delivery-status blocks ────────────────────────────────
    info = {
        "is_bounce": True,
        "reporting_mta": None,
        "final_recipient": None,
        "action": None,
        "status": None,
        "diagnostic_code": None,
        "original_message_id": None,
        "original_from": None,
        "original_to": None,
        "original_subject": None,
        "original_date": None,
    }

    if ds_part is not None:
        payload = ds_part.get_payload()
        if isinstance(payload, list):
            for block in payload:
                if hasattr(block, "items"):
                    for k, v in block.items():
                        k_lower = k.lower()
                        if k_lower == "reporting-mta":
                            info["reporting_mta"] = str(v)
                        elif k_lower == "final-recipient":
                            # Strip "rfc822;" prefix
                            info["final_recipient"] = _clean_recipient(v)
                        elif k_lower == "action":
                            info["action"] = str(v)
                        elif k_lower == "status":
                            info["status"] = str(v)
                        elif k_lower == "diagnostic-code":
                            # Strip "smtp;" prefix
                            info["diagnostic_code"] = _clean_diag(v)

    # ── parse original message from rfc822 part ────────────────────
    if rfc822_part is not None:
        inner = rfc822_part.get_payload()
        if isinstance(inner, list):
            inner = inner[0] if inner else None
        if hasattr(inner, "get"):
            info["original_message_id"] = str(inner.get("Message-ID", "") or "")
            info["original_from"] = str(inner.get("From", "") or "")
            info["original_to"] = str(inner.get("To", "") or "")
            info["original_subject"] = str(inner.get("Subject", "") or "")
            info["original_date"] = str(inner.get("Date", "") or "")

    return info


def _clean_recipient(raw):
    s = str(raw)
    if s.lower().startswith("rfc822;"):
        s = s[7:].strip()
    return s


def _clean_diag(raw):
    s = str(raw)
    if s.lower().startswith("smtp;"):
        s = s[5:].strip()
    return s


# ── outbound matcher ─────────────────────────────────────────────────────
def find_outbound_by_bounce(bounce_info, conn):
    """Return (messages_id, match_method) or (None, None).

    Tries (in order):
      1. original_message_id exact match (primary, most reliable).
      2. subject + recipient fallback (logged as less reliable).
    """
    # ── primary: Message-ID ──────────────────────────────────────────
    mid = (bounce_info.get("original_message_id") or "").strip()
    if mid:
        row = conn.execute(
            "SELECT id FROM messages WHERE direction='outbound' AND message_id=? ORDER BY id DESC LIMIT 1",
            (mid,),
        ).fetchone()
        if row:
            return row[0], "message_id"

    # ── fallback: subject + recipient ────────────────────────────────
    subject = (bounce_info.get("original_subject") or "").strip()
    recipient = (bounce_info.get("final_recipient") or "").strip()
    if subject and recipient:
        row = conn.execute(
            """SELECT id FROM messages
               WHERE direction='outbound'
                 AND recipient LIKE ?
                 AND subject = ?
                 AND status IN ('accepted_by_ses', 'sent')
               ORDER BY sent_at DESC, id DESC
               LIMIT 1""",
            (f"%{recipient}%", subject),
        ).fetchone()
        if row:
            return row[0], "fallback_subject_recipient"

    return None, None


# ── status updater ───────────────────────────────────────────────────────
def apply_bounce(bounce_info, inbound_s3_key=None):
    """Update outbound status and insert message_events row."""
    conn = sqlite3.connect(str(DB_PATH))

    outbound_id, match_method = find_outbound_by_bounce(bounce_info, conn)
    now = datetime.now(timezone.utc).isoformat()

    if outbound_id:
        if match_method == "message_id":
            log("INFO", f"Bounce match by original_message_id: "
                f"{bounce_info.get('original_message_id')} → outbound id={outbound_id}")
        else:
            log("WARN", f"Bounce matched by fallback subject+recipient → outbound id={outbound_id}")

        conn.execute(
            """UPDATE messages
               SET status = 'bounced',
                   delivery_action = ?,
                   delivery_status = ?,
                   diagnostic_code = ?,
                   bounced_at = ?
               WHERE id = ?""",
            (
                bounce_info.get("action"),
                bounce_info.get("status"),
                bounce_info.get("diagnostic_code"),
                now,
                outbound_id,
            ),
        )
        conn.commit()
        log("INFO", f"Updated outbound id={outbound_id} status=bounced")
    else:
        log("WARN", "Bounce detected but no matching outbound found")
        match_method = None

    # ── metadata for audit ──────────────────────────────────────────
    import json

    metadata = {
        "match_method": match_method,
        "original_subject": bounce_info.get("original_subject"),
        "original_to": bounce_info.get("original_to"),
        "original_from": bounce_info.get("original_from"),
    }
    metadata_json = json.dumps(metadata, default=str)

    # ── insert event regardless ──────────────────────────────────────
    conn.execute(
        """INSERT INTO message_events (
               message_id, event_type, event_time, source,
               final_recipient, action, status_code, diagnostic_code,
               related_message_id, raw_message_id, metadata_json, created_at
           ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            outbound_id,
            "bounce",
            now,
            "dsn",
            bounce_info.get("final_recipient"),
            bounce_info.get("action"),
            bounce_info.get("status"),
            bounce_info.get("diagnostic_code"),
            bounce_info.get("original_message_id"),
            inbound_s3_key,
            metadata_json,
            now,
        ),
    )
    conn.commit()
    log("INFO", "Inserted message_events row event_type=bounce")
    conn.close()


# ── convenience: parse a raw .eml file path ───────────────────────────────
def parse_dsn_from_file(path):
    with open(path, "rb") as f:
        msg = BytesParser(policy=policy.default).parse(f)
    return parse_dsn(msg)


# ── main (manual test / idempotent re-process) ───────────────────────────
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        path = sys.argv[1]
        info = parse_dsn_from_file(path)
        if info:
            log("INFO", f"DSN detected: action={info['action']} recipient={info['final_recipient']} status={info['status']}")
            log("INFO", f"  diagnostic: {info['diagnostic_code']}")
            log("INFO", f"  original_subject: {info['original_subject']}")
            log("INFO", f"  original_message_id: {info['original_message_id']}")
            apply_bounce(info, inbound_s3_key=path)
        else:
            log("INFO", "Not a bounce/DSN")
    else:
        log("INFO", "Usage: python3 -m worker.bounce <path-to-.eml>")
