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
SENT_BASE = Path(
    os.getenv("SENT_MAILDIR", str(MASTER_MAILDIR / ".Sent"))
)
DUPE_BASE = Path(
    os.getenv(
        "SENT_DUPLICATES_MAILDIR",
        str(MASTER_MAILDIR / ".SentDuplicates"),
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
def _ensure_dirs():
    for p in (DUPE_BASE / "cur", DUPE_BASE / "new", DUPE_BASE / "tmp"):
        p.mkdir(parents=True, exist_ok=True)
    (DUPE_BASE / "maildirfolder").write_text("")


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
def dedupe_sent():
    _ensure_dirs()
    registered = _get_registered_paths()

    files = _list_message_files(SENT_BASE)
    log("INFO", f"Sent dedupe started — found {len(files)} message file(s)")

    # Group by Message-ID (skip messages without one)
    by_mid = {}
    unparseable = 0
    no_mid = 0

    for fpath in files:
        mid = _extract_message_id(fpath)
        if mid is None:
            if mid is False:  # parse error
                unparseable += 1
            else:
                no_mid += 1
                log("WARN", f"Message without Message-ID: {fpath}")
            continue
        by_mid.setdefault(mid, []).append(fpath)

    moved = 0

    for mid, paths in by_mid.items():
        if len(paths) <= 1:
            continue

        log("INFO", f"Found duplicate Message-ID: {mid} ({len(paths)} copies)")

        # Prefer the copy registered in SQLite
        keep = None
        for p in paths:
            if str(p) in registered:
                keep = p
                break

        # Fallback: oldest by mtime
        if keep is None:
            keep = min(paths, key=lambda p: p.stat().st_mtime)

        log("INFO", f"  Keeping: {keep}")

        for p in paths:
            if p == keep:
                continue
            dest = _move_to_dupes(p, DUPE_BASE / "cur")
            log("INFO", f"  Moved duplicate: {p.name} → {dest}")

        moved += len(paths) - 1

    summary = f"Sent dedupe finished — {moved} duplicate(s) moved"
    if unparseable:
        summary += f", {unparseable} unparseable"
    if no_mid:
        summary += f", {no_mid} without Message-ID"
    log("INFO", summary)


if __name__ == "__main__":
    dedupe_sent()
