#!/usr/bin/env python3
"""
Local SMTP → Amazon SES Relay Server

Accepts SMTP submissions from Thunderbird on localhost:2525, relays
them via Amazon SES SMTP, saves a copy to Maildir .Sent, and records
outbound metadata in SQLite.

Security: only connections from allowed IP networks are accepted.
"""

import asyncio
import email
import signal
import sys
import time
from email import policy
from email.parser import BytesParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiosmtpd.controller import Controller  # noqa: E402

from sender.config import (  # noqa: E402
    DEFAULT_FROM_DOMAIN,
    LOCAL_SMTP_HOST,
    LOCAL_SMTP_PORT,
    is_ip_allowed,
    log,
)
from sender.ses_relay import relay_via_ses  # noqa: E402
from sender.store import save_outbound      # noqa: E402

# Mailbox resolution for outbound messages
try:
    from worker.mailbox_resolver import resolve_mailbox_for_outbound

    _MULTI_MAILBOX = True
except ImportError:
    _MULTI_MAILBOX = False


def compute_thread_id(message_id, in_reply_to, references):
    """Same thread-id logic as the inbound worker."""
    refs = (references or "").strip()
    irt = (in_reply_to or "").strip()
    mid = (message_id or "").strip()

    if refs:
        return refs.split()[0]
    if irt:
        return irt
    if mid:
        return mid
    return None


class OutboundHandler:
    async def handle_DATA(self, server, session, envelope):
        peer_ip = session.peer[0] if session.peer else "unknown"
        log("INFO", f"DATA from {peer_ip} ({len(envelope.content)} bytes)")

        if not is_ip_allowed(peer_ip):
            log("WARNING", f"Rejected connection from {peer_ip} (not in allowlist)")
            return "550 5.7.1 Connection not allowed"

        raw_bytes = envelope.original_content or envelope.content
        if isinstance(raw_bytes, str):
            raw_bytes = raw_bytes.encode("utf-8")

        mail_from = envelope.mail_from
        rcpt_tos = envelope.rcpt_tos

        # ── parse headers for metadata ───────────────────────────────
        msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)
        subject = str(msg.get("Subject", ""))
        message_id = str(msg.get("Message-ID", ""))
        date_header = str(msg.get("Date", ""))
        in_reply_to = str(msg.get("In-Reply-To", ""))
        references = str(msg.get("References", ""))
        cc = str(msg.get("Cc", ""))
        bcc = str(msg.get("Bcc", ""))
        thread_id = compute_thread_id(message_id, in_reply_to, references)

        # ── relay via SES ────────────────────────────────────────────
        loop = asyncio.get_running_loop()
        ok, response = await loop.run_in_executor(
            None, relay_via_ses, raw_bytes, mail_from, rcpt_tos
        )

        # ── save local copy ──────────────────────────────────────────
        status = "accepted_by_ses" if ok else "failed"
        mailbox_id = None
        if _MULTI_MAILBOX:
            import sqlite3
            from sender.config import DB_PATH

            conn = sqlite3.connect(str(DB_PATH))
            try:
                mailbox_id, mailbox_slug = resolve_mailbox_for_outbound(conn, mail_from)
                log("INFO", f"Resolved outbound mailbox: {mailbox_slug} for sender {mail_from}")
            except Exception:
                log("WARN", "Mailbox resolution failed for outbound; falling back to master")
            finally:
                conn.close()
        try:
            save_outbound(
                raw_bytes=raw_bytes,
                mail_from=mail_from,
                rcpt_tos=rcpt_tos,
                subject=subject,
                message_id=message_id,
                date_header=date_header,
                in_reply_to=in_reply_to,
                references=references,
                thread_id=thread_id,
                cc=cc,
                bcc=bcc,
                status=status,
                error_message=None if ok else response,
                relay_response=response,
                mailbox_id=mailbox_id,
            )
        except Exception as exc:
            log("ERROR", f"Failed to save outbound copy: {exc}")

        if ok:
            log("INFO", f"Sent OK — from={mail_from} to={rcpt_tos} subj={subject}")
            return "250 2.0.0 OK"

        log("ERROR", f"Send FAILED — from={mail_from} to={rcpt_tos}: {response}")
        return f"550 5.0.0 {response}"


# ── main ────────────────────────────────────────────────────────────────
_shutdown = False


def _on_signal(signum, _frame):
    global _shutdown
    name = signal.Signals(signum).name
    log("INFO", f"Received {name}, shutting down...")
    _shutdown = True


def main():
    global _shutdown
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    log("INFO", f"SMTP sender starting on {LOCAL_SMTP_HOST}:{LOCAL_SMTP_PORT}")
    log("INFO", f"Allowed networks: {[str(n) for n in ALLOWED_NETWORKS]}")

    controller = Controller(
        OutboundHandler(),
        hostname=LOCAL_SMTP_HOST,
        port=LOCAL_SMTP_PORT,
    )
    controller.start()
    log("INFO", "SMTP sender ready — accepting connections")

    try:
        while not _shutdown:
            time.sleep(0.5)
    finally:
        log("INFO", "Stopping SMTP sender...")
        controller.stop()
        log("INFO", "SMTP sender stopped")


if __name__ == "__main__":
    # avoid double-definition of ALLOWED_NETWORKS at import time
    from sender.config import ALLOWED_NETWORKS  # noqa: E402
    main()
