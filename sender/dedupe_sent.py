#!/usr/bin/env python3
"""Deduplicate the .Sent Maildir folder by Message-ID.

When both the backend (sender/store.py) and Thunderbird (via Dovecot/IMAP)
save a copy of the same sent message, two files end up in .Sent/cur/ with
the same Message-ID.  This script keeps the copy registered in SQLite (or
the oldest one otherwise) and moves the rest to .SentDuplicates/cur/ for
safe quarantine — nothing is ever deleted.
"""

import hashlib
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from pathlib import Path

# Make project imports work from any cwd
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# Load .env
try:
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env", override=True)
except ImportError:
    pass


# ── paths ────────────────────────────────────────────────────────────────
MASTER_MAILDIR = Path(
    os.getenv(
        "MASTER_MAILDIR",
        str(PROJECT_ROOT / "data" / "maildir" / "master"),
    )
)
DB_PATH = Path(
    os.getenv("DB_PATH", str(PROJECT_ROOT / "data" / "mailbox.db"))
)

# ── ignore these Dovecot internal files ──────────────────────────────────
IGNORE_NAMES = {
    "dovecot.index.cache",
    "dovecot.index.log",
    "dovecot-uidlist",
    "dovecot-uidvalidity",
    "maildirfolder",
    "subscriptions",
}


# ── logging ──────────────────────────────────────────────────────────────
def log(level, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr if level == "ERROR" else sys.stdout
    print(f"[{ts}] [{level}] {msg}", file=stream)


# ── helpers ──────────────────────────────────────────────────────────────
def _is_eml(name):
    """True if this looks like a message file (ends with .eml or has Maildir flags)."""
    return name.endswith(".eml") or ":2," in name


def _extract_message_id(filepath):
    try:
        with open(filepath, "rb") as f:
            msg = BytesParser(policy=policy.default).parse(f)
        mid = str(msg.get("Message-ID", ""))
        return mid if mid else None
    except Exception:
        log("WARN", f"Could not parse {filepath}")
        return None


def _get_registered_paths():
    """Return a set of absolute local_maildir_path values for outbound messages."""
    if not DB_PATH.exists():
        return set()

    conn = sqlite3.connect(str(DB_PATH))
    try:
        rows = conn.execute(
            "SELECT local_maildir_path FROM messages WHERE direction = 'outbound'"
        ).fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return set()
    conn.close()
    return {str(Path(row[0]).resolve()) for row in rows if row[0]}


def _list_message_files(base_dir):
    """Return absolute paths to all message files in cur/ and new/ (non-recursive)."""
    files = []
    for sub in ("cur", "new"):
        subdir = base_dir / sub
        if not subdir.is_dir():
            continue
        for entry in subdir.iterdir():
            if entry.is_file() and _is_eml(entry.name) and entry.name not in IGNORE_NAMES:
                files.append(entry.resolve())
    return files


def _move_to_dupes(src, dupe_dir):
    """Move a file to the duplicates quarantine, preserving Maildir flags if possible."""
    dupe_dir.mkdir(parents=True, exist_ok=True)
    name = src.name
    dest = dupe_dir / name
    # avoid collision
    while dest.exists():
        digest = hashlib.sha256(str(dest).encode()).hexdigest()[:8]
        dest = dupe_dir / f"{src.stem}_{digest}{''.join(src.suffixes)}"
    shutil.move(str(src), str(dest))
    return dest


# ── main logic ───────────────────────────────────────────────────────────
def _dedupe_one_mailbox(sent_base, dupe_base, registered):
    """Run deduplication on one mailbox's .Sent folder. Returns (moved, unparseable, no_mid)."""
    sent_dup_cur = dupe_base / "cur"
    for p in (sent_dup_cur, dupe_base / "new", dupe_base / "tmp"):
        p.mkdir(parents=True, exist_ok=True)
    (dupe_base / "maildirfolder").write_text("")

    files = _list_message_files(sent_base)

    by_mid = {}
    unparseable = 0
    no_mid = 0

    for fpath in files:
        mid = _extract_message_id(fpath)
        if mid is None:
            no_mid += 1
            log("WARN", f"Message without Message-ID: {fpath}")
            continue
        by_mid.setdefault(mid, []).append(fpath)

    moved = 0

    for mid, paths in by_mid.items():
        if len(paths) <= 1:
            continue

        log("INFO", f"  Found duplicate Message-ID: {mid} ({len(paths)} copies)")

        keep = None
        for p in paths:
            if str(p) in registered:
                keep = p
                break

        if keep is None:
            keep = min(paths, key=lambda p: p.stat().st_mtime)

        log("INFO", f"    Keeping: {keep.name}")

        for p in paths:
            if p == keep:
                continue
            dest = _move_to_dupes(p, sent_dup_cur)
            log("INFO", f"    Moved duplicate: {p.name} → {dest}")

        moved += len(paths) - 1

    return moved, unparseable, no_mid


def _get_active_mailbox_sent_dirs():
    """Return list of (maildir_path, slug) for all active mailboxes."""
    conn = sqlite3.connect(str(DB_PATH))
    rows = conn.execute(
        "SELECT maildir_path, slug FROM mailboxes WHERE is_active=1 ORDER BY id"
    ).fetchall()
    conn.close()
    return [(Path(r[0]), r[1]) for r in rows]


def dedupe_sent():
    registered = _get_registered_paths()

    mailboxes = _get_active_mailbox_sent_dirs()
    if not mailboxes:
        log("WARN", "No active mailboxes found; using master as fallback")
        mailboxes = [(MASTER_MAILDIR, "master")]

    total_moved = 0
    total_unparseable = 0
    total_no_mid = 0
    total_files = 0

    for maildir, slug in mailboxes:
        sent_base = maildir / ".Sent"
        dupe_base = maildir / ".SentDuplicates"
        files = _list_message_files(sent_base)
        log("INFO", f"Dedupe {slug}: .Sent has {len(files)} file(s)")
        total_files += len(files)

        m, u, n = _dedupe_one_mailbox(sent_base, dupe_base, registered)
        total_moved += m
        total_unparseable += u
        total_no_mid += n
        if m:
            log("INFO", f"  → moved {m} duplicate(s) to {slug}/.SentDuplicates")

    summary = f"Sent dedupe finished — {total_files} files, {total_moved} duplicate(s) moved"
    if total_unparseable:
        summary += f", {total_unparseable} unparseable"
    if total_no_mid:
        summary += f", {total_no_mid} without Message-ID"
    log("INFO", summary)


if __name__ == "__main__":
    dedupe_sent()
