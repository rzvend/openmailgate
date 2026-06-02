"""Admin write tests — create mailbox via dashboard."""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _login():
    client.post("/auth/login", data={"username": "ricardo", "password": "unit-test-password-only"})


def test_new_mailbox_requires_login():
    response = client.get("/dashboard/mailboxes/new", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers.get("location", "")


def test_new_mailbox_form_loads():
    _login()
    response = client.get("/dashboard/mailboxes/new")
    assert response.status_code == 200
    assert "New Mailbox" in response.text


def test_create_mailbox_invalid_slug():
    _login()
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": "../etc", "name": "Bad", "address": "bad@test.com"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "invalid slug" in response.text.lower()


def test_create_mailbox_duplicate_slug():
    import uuid
    _login()
    slug = f"testdup2{uuid.uuid4().hex[:6]}"
    client.post("/dashboard/mailboxes/new",
                data={"slug": slug, "name": "S", "address": f"{slug}@test.com"})
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": slug, "name": "S2", "address": f"other@{slug}.com"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "already exists" in response.text


def test_create_mailbox_success():
    import uuid
    _login()
    slug = f"test{uuid.uuid4().hex[:6]}"
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": slug, "name": "Test", "address": f"{slug}@test.com"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert f"/dashboard/mailboxes/{slug}" in response.headers.get("location", "")


def test_create_mailbox_duplicate_address():
    import uuid
    _login()
    slug = f"testdup{uuid.uuid4().hex[:6]}"
    # Create first mailbox with this address
    client.post("/dashboard/mailboxes/new",
                data={"slug": slug, "name": "D1", "address": f"{slug}@test.com"})
    # Try to create another with same address
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": slug + "x", "name": "D2", "address": f"{slug}@test.com"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "already exists" in response.text


# ── IMAP password tests ──────────────────────────────────────────────


def test_imap_password_form_requires_login():
    client.post("/auth/logout")
    response = client.get("/dashboard/addresses/1/imap-password", follow_redirects=False)
    assert response.status_code == 302


def test_imap_password_form_loads():
    _login()
    response = client.get("/dashboard/addresses/1/imap-password")
    assert response.status_code == 200
    assert "IMAP Password" in response.text


def test_imap_password_mismatch():
    _login()
    response = client.post(
        "/dashboard/addresses/1/imap-password",
        data={"password": "12345678", "confirm": "87654321"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "do not match" in response.text


def test_imap_password_empty():
    _login()
    response = client.post(
        "/dashboard/addresses/1/imap-password",
        data={"password": "", "confirm": ""},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "cannot be empty" in response.text


def test_imap_password_too_short():
    _login()
    response = client.post(
        "/dashboard/addresses/1/imap-password",
        data={"password": "1234567", "confirm": "1234567"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "at least 8" in response.text


def test_imap_password_unknown_address():
    _login()
    response = client.get("/dashboard/addresses/99999/imap-password")
    assert response.status_code == 404


def test_mailbox_page_shows_imap_links():
    _login()
    response = client.get("/dashboard/mailboxes/master")
    assert response.status_code == 200
    assert "Set" in response.text or "Change" in response.text
    assert "IMAP Password" in response.text
    assert "imap_password_hash" not in response.text
    assert "{SHA512-CRYPT}$6$" not in response.text


# ── IMAP sync tests ──────────────────────────────────────────────────


def test_imap_sync_requires_login():
    client.post("/auth/logout")
    response = client.get("/dashboard/imap-sync", follow_redirects=False)
    assert response.status_code == 302


def test_imap_sync_page_loads():
    _login()
    response = client.get("/dashboard/imap-sync")
    assert response.status_code == 200
    assert "IMAP Sync" in response.text
    assert "Dry-Run" in response.text


def test_imap_sync_dry_run():
    _login()
    from unittest.mock import patch
    with patch("worker.dovecot_users.parse_dovecot_users", return_value={}):
        response = client.post("/dashboard/imap-sync/dry-run", follow_redirects=False)
    assert response.status_code == 200
    assert "Summary" in response.text


def test_imap_sync_apply_permission_error():
    _login()
    response = client.post("/dashboard/imap-sync/apply", follow_redirects=False)
    assert response.status_code == 200
    assert "sudo" in response.text.lower() or "Apply" in response.text


def test_imap_sync_dry_run_hashes_masked():
    _login()
    from unittest.mock import patch
    with patch("worker.dovecot_users.parse_dovecot_users", return_value={}):
        response = client.post("/dashboard/imap-sync/dry-run", follow_redirects=False)
    assert response.status_code == 200
    text = response.text
    import re
    # Any SHA512-CRYPT hash that is NOT masked (no ****) is a problem
    unmasked = re.findall(r'\{SHA512-CRYPT\}\$6\$[^:*]{30,}', text)
    assert len(unmasked) == 0, f"Unmasked hashes found: {unmasked[:3]}"
