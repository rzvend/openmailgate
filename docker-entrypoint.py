#!/usr/bin/env python3
"""Docker entrypoint — run database migrations, then start the application.

For the API service this ensures tables exist before the app accepts requests.
When used with ``docker compose run`` it also runs migrations before ad-hoc
commands (bootstrap_admin, shell, etc.).
"""

import os
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# ── Ensure the SQLite database file exists ──────────────────────────────
DB_PATH = Path(os.getenv("DB_PATH", "/app/data/mailbox.db"))
if not DB_PATH.exists():
    print("[entrypoint] Creating database...", flush=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.close()

# ── Run migrations (idempotent — safe to run multiple times) ─────────────
print("[entrypoint] Running migrations...", flush=True)
from worker import migrate  # noqa: E402

try:
    migrate.main()
except SystemExit as e:
    if e.code is not None and e.code != 0:
        print("[entrypoint] Migration failed!", file=sys.stderr)
        sys.exit(e.code)
print("[entrypoint] Migrations applied.", flush=True)

# ── Normalize Maildir ownership for existing mailboxes ─────────────────
_MAILDIR_ROOT = Path(os.getenv("DOVECOT_MAIL_ROOT", "/app/data/maildir"))
_DOVECOT_UID = int(os.getenv("DOVECOT_UID", "1000"))
_DOVECOT_GID = int(os.getenv("DOVECOT_GID", "1000"))
if _MAILDIR_ROOT.exists():
    print("[entrypoint] Normalizing Maildir ownership...", flush=True)
    for entry in _MAILDIR_ROOT.iterdir():
        if entry.is_dir() and not entry.name.startswith("."):
            try:
                os.chown(entry, _DOVECOT_UID, _DOVECOT_GID)
            except OSError:
                pass
            for root, dirs, files in os.walk(entry):
                for d in dirs:
                    try:
                        os.chown(os.path.join(root, d), _DOVECOT_UID, _DOVECOT_GID)
                    except OSError:
                        pass
                for f in files:
                    try:
                        os.chown(os.path.join(root, f), _DOVECOT_UID, _DOVECOT_GID)
                    except OSError:
                        pass
    print("[entrypoint] Maildir ownership normalized.", flush=True)

# ── Start the application ────────────────────────────────────────────────
# Strip leading python3 / python if the compose command string includes it
args = sys.argv[1:]
while args and args[0] in ("python3", "python", sys.executable):
    args = args[1:]
if not args:
    args = ["-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

os.execvp(sys.executable, [sys.executable] + args)
