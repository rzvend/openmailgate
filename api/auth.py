"""Authentication helpers — password verification and session management."""

import crypt
import hmac
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Request
from fastapi.responses import RedirectResponse

from config import DB_PATH


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plain-text password against a {SHA512-CRYPT} hash."""
    if not stored_hash or not password:
        return False
    raw = stored_hash.removeprefix("{SHA512-CRYPT}")
    try:
        candidate = crypt.crypt(password, raw)
    except Exception:
        return False
    return hmac.compare_digest(candidate, raw)


def authenticate_operator(username: str, password: str) -> dict | None:
    """Return operator dict (without password_hash) if valid, else None."""
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute(
        "SELECT id, username, password_hash, is_active FROM operators WHERE username = ?",
        (username.strip().lower(),),
    ).fetchone()
    conn.close()
    if not row or not row[2] or not row[3]:
        return None
    if verify_password(password, row[2]):
        return {"id": row[0], "username": row[1], "is_active": row[3]}
    return None


def get_current_operator(request: Request) -> dict | None:
    """Return the logged-in operator dict from the session, or None."""
    op_id = request.session.get("operator_id")
    username = request.session.get("username")
    if op_id and username:
        return {"id": op_id, "username": username}
    return None


def require_login(request: Request):
    """Redirect to /auth/login if not authenticated. Returns None if OK."""
    if not get_current_operator(request):
        return RedirectResponse(url="/auth/login", status_code=302)
    return None
