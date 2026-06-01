"""Mailbox resolution helpers.

Used by both the inbound worker and outbound sender to map email addresses
to mailbox IDs.  Falls back to the "master" mailbox when no match is found.
"""

import re
import sqlite3
from pathlib import Path


def _connect():
    import os

    db_path = Path(
        os.getenv(
            "DB_PATH",
            str(Path.home() / "ses-s3-mailbox" / "data" / "mailbox.db"),
        )
    )
    return sqlite3.connect(str(db_path))


def normalize_email_address(address):
    """Lowercase and strip display-name, returning just the addr-spec."""
    if not address:
        return ""
    # Remove display name: "Name <addr>" → addr
    match = re.search(r"<([^>]+)>", address)
    if match:
        return match.group(1).strip().lower()
    return address.strip().lower()


def get_mailbox_by_address(conn, address):
    """Return (mailbox_id, slug) or None."""
    addr = normalize_email_address(address)
    if not addr:
        return None
    row = conn.execute(
        "SELECT m.id, m.slug FROM mailboxes m "
        "JOIN email_addresses e ON e.mailbox_id = m.id "
        "WHERE e.address = ? AND e.is_active = 1 AND m.is_active = 1",
        (addr,),
    ).fetchone()
    return row if row else None


def get_master_id(conn):
    row = conn.execute("SELECT id FROM mailboxes WHERE slug='master'").fetchone()
    return row[0] if row else None


def resolve_mailbox_for_inbound(conn, headers):
    """Walk recipient headers in priority order, return (mailbox_id, slug).

    Returns (None, None) when no active mailbox matches — caller should
    use master as fallback.  This allows the caller to distinguish a
    genuine master match from a no-match situation for audit purposes.
    """
    candidates = []
    for hdr in ("Delivered-To", "Envelope-To", "To", "recipient", "delivered_to", "envelope_to", "to"):
        raw = headers.get(hdr, "") if isinstance(headers, dict) else ""
        if raw:
            candidates.append(raw)

    seen = set()
    for raw in candidates:
        for addr in (a.strip() for a in raw.split(",")):
            addr = normalize_email_address(addr)
            if not addr or addr in seen:
                continue
            seen.add(addr)
            match = get_mailbox_by_address(conn, addr)
            if match:
                return match

    return None, None


def resolve_mailbox_for_outbound(conn, sender):
    """Resolve mailbox from the From: header. Falls back to 'master'."""
    addr = normalize_email_address(sender)
    if addr:
        match = get_mailbox_by_address(conn, addr)
        if match:
            return match

    return get_master_id(conn), "master"
