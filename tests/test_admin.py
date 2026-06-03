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
    unmasked = re.findall(r'\{SHA512-CRYPT\}\$6\$[^:*]{30,}', text)
    assert len(unmasked) == 0, f"Unmasked hashes found: {unmasked[:3]}"


# ── operator management tests ─────────────────────────────────────────


def test_operator_new_route_not_captured():
    _login()
    r = client.get("/dashboard/operators/new")
    assert r.status_code == 200
    assert "New Operator" in r.text


def test_operator_new_requires_login():
    client.post("/auth/logout")
    r = client.get("/dashboard/operators/new", follow_redirects=False)
    assert r.status_code == 302


def test_create_operator_success():
    import uuid
    _login()
    u = f"testop{uuid.uuid4().hex[:6]}"
    r = client.post("/dashboard/operators/new", data={
        "username": u, "password": "12345678", "confirm": "12345678", "active": "1",
    }, follow_redirects=False)
    assert r.status_code == 302
    assert f"/dashboard/operators/{u}" in r.headers.get("location", "")


def test_create_operator_password_mismatch():
    _login()
    r = client.post("/dashboard/operators/new", data={
        "username": "testop2", "password": "12345678", "confirm": "87654321",
    }, follow_redirects=False)
    assert r.status_code == 200
    assert "do not match" in r.text


def test_create_operator_duplicate():
    _login()
    r = client.post("/dashboard/operators/new", data={
        "username": "ricardo", "password": "12345678", "confirm": "12345678",
    }, follow_redirects=False)
    assert r.status_code == 200
    assert "already exists" in r.text


def test_operator_detail_loads():
    _login()
    r = client.get("/dashboard/operators/ricardo")
    assert r.status_code == 200
    assert "ricardo" in r.text
    assert "password_hash" not in r.text


def test_grant_mailbox_success():
    _login()
    r = client.post("/dashboard/operators/ricardo/grant", data={
        "mailbox_id": "1", "role": "viewer",
    }, follow_redirects=False)
    assert r.status_code == 302


def test_revoke_mailbox_success():
    _login()
    # Grant first
    client.post("/dashboard/operators/ricardo/grant", data={"mailbox_id": "1", "role": "viewer"})
    r = client.post("/dashboard/operators/ricardo/revoke", data={
        "mailbox_id": "1",
    }, follow_redirects=False)
    assert r.status_code == 302


def test_operator_templates_no_password_hash():
    _login()
    r = client.get("/dashboard/operators/ricardo")
    assert "password_hash" not in r.text
    assert "{SHA512-CRYPT}" not in r.text


# ── catch-all tests ───────────────────────────────────────────────────


def test_catch_all_page_requires_login():
    client.post("/auth/logout")
    r = client.get("/dashboard/catch-all", follow_redirects=False)
    assert r.status_code == 302


def test_catch_all_page_loads():
    _login()
    r = client.get("/dashboard/catch-all")
    assert r.status_code == 200
    assert "Catch-all" in r.text


def test_set_catch_all_success():
    _login()
    r = client.post("/dashboard/catch-all", data={"mailbox_id": "1"}, follow_redirects=False)
    assert r.status_code == 302


def test_set_catch_all_rejects_invalid_mailbox():
    _login()
    r = client.post("/dashboard/catch-all", data={"mailbox_id": "99999"}, follow_redirects=False)
    assert r.status_code == 200
    assert "Invalid" in r.text


def test_clear_catch_all_success():
    _login()
    client.post("/dashboard/catch-all", data={"mailbox_id": "1"})
    r = client.post("/dashboard/catch-all/clear", follow_redirects=False)
    assert r.status_code == 302


def test_get_catch_all_returns_none_when_not_configured():
    from database import clear_catch_all_mailbox, get_catch_all_mailbox
    clear_catch_all_mailbox()
    assert get_catch_all_mailbox() is None


def test_resolver_uses_catch_all():
    from database import get_catch_all_mailbox, set_catch_all_mailbox
    # Set catch-all to master (id=1)
    set_catch_all_mailbox(1)
    mb = get_catch_all_mailbox()
    assert mb is not None
    assert mb["slug"] == "master"
    # Clean up
    from database import clear_catch_all_mailbox
    clear_catch_all_mailbox()


def test_main_create_link_points_to_wizard():
    _login()
    r = client.get("/dashboard")
    assert r.status_code == 200
    # The main create link should point to the wizard
    assert '/dashboard/mailboxes/wizard' in r.text


# ── system status tests ───────────────────────────────────────────────


def test_status_page_requires_login():
    client.post("/auth/logout")
    r = client.get("/dashboard/status", follow_redirects=False)
    assert r.status_code == 302


def test_status_page_loads():
    _login()
    r = client.get("/dashboard/status")
    assert r.status_code == 200
    assert "System Status" in r.text
    assert "SQLite" in r.text


def test_status_page_shows_version():
    _login()
    r = client.get("/dashboard/status")
    assert "0.1.0-dev" in r.text


def test_status_page_no_secrets():
    _login()
    r = client.get("/dashboard/status")
    for secret in ("password_hash", "imap_password_hash", "AWS_SECRET", "CLOUDFLARE_API_TOKEN"):
        assert secret not in r.text


# ── archive mailbox tests ──────────────────────────────────────────────


def test_archive_page_requires_login():
    client.post("/auth/logout")
    r = client.get("/dashboard/archive", follow_redirects=False)
    assert r.status_code == 302


def test_archive_page_loads():
    _login()
    r = client.get("/dashboard/archive")
    assert r.status_code == 200
    assert "Archive" in r.text


def test_set_inbound_archive_success():
    _login()
    r = client.post("/dashboard/archive/inbound", data={"mailbox_id": "1"}, follow_redirects=False)
    assert r.status_code == 302


def test_clear_inbound_archive():
    _login()
    client.post("/dashboard/archive/inbound", data={"mailbox_id": "1"})
    r = client.post("/dashboard/archive/inbound/clear", follow_redirects=False)
    assert r.status_code == 302


def test_set_outbound_archive_success():
    _login()
    r = client.post("/dashboard/archive/outbound", data={"mailbox_id": "1"}, follow_redirects=False)
    assert r.status_code == 302


def test_clear_outbound_archive():
    _login()
    client.post("/dashboard/archive/outbound", data={"mailbox_id": "1"})
    r = client.post("/dashboard/archive/outbound/clear", follow_redirects=False)
    assert r.status_code == 302


def test_reject_inactive_archive_mailbox():
    _login()
    r = client.post("/dashboard/archive/inbound", data={"mailbox_id": "2"}, follow_redirects=False)
    assert r.status_code == 200
    assert "Invalid" in r.text or "inactive" in r.text.lower()


# ── mailbox wizard tests ──────────────────────────────────────────────


def test_mailbox_wizard_route_not_captured_by_slug():
    _login()
    r = client.get("/dashboard/mailboxes/wizard")
    assert r.status_code == 200
    assert "Create Mailbox" in r.text


def test_mailbox_wizard_requires_login():
    client.post("/auth/logout")
    r = client.get("/dashboard/mailboxes/wizard", follow_redirects=False)
    assert r.status_code == 302


def test_mailbox_wizard_form_loads():
    _login()
    r = client.get("/dashboard/mailboxes/wizard")
    assert r.status_code == 200
    assert "Create Mailbox" in r.text
    assert "IMAP password" in r.text


def test_mailbox_wizard_password_mismatch():
    _login()
    r = client.post("/dashboard/mailboxes/wizard", data={
        "slug": "wiz1", "name": "W1", "address": "wiz1@test.com",
        "password": "12345678", "confirm": "87654321",
    }, follow_redirects=False)
    assert r.status_code == 200
    assert "do not match" in r.text


def test_mailbox_wizard_success_without_sync():
    import uuid
    _login()
    slug = f"wiz{uuid.uuid4().hex[:6]}"
    r = client.post("/dashboard/mailboxes/wizard", data={
        "slug": slug, "name": "W Test", "address": f"{slug}@test.com",
        "password": "12345678", "confirm": "12345678",
    }, follow_redirects=False)
    assert r.status_code == 200
    assert "Mailbox Created" in r.text or "mailbox_created" in r.text.lower()


def test_mailbox_wizard_does_not_expose_password():
    import uuid
    _login()
    slug = f"wiz2{uuid.uuid4().hex[:6]}"
    r = client.post("/dashboard/mailboxes/wizard", data={
        "slug": slug, "name": "W2", "address": f"{slug}@test.com",
        "password": "12345678", "confirm": "12345678",
    }, follow_redirects=False)
    assert "12345678" not in r.text
    assert "imap_password_hash" not in r.text


# ── enable/disable tests ──────────────────────────────────────────────


def test_disable_mailbox_requires_login():
    client.post("/auth/logout")
    r = client.post("/dashboard/mailboxes/financeiro/disable", follow_redirects=False)
    assert r.status_code == 302


def test_disable_mailbox_success():
    _login()
    r = client.post("/dashboard/mailboxes/financeiro/disable", follow_redirects=False)
    assert r.status_code == 302
    r2 = client.get("/dashboard/mailboxes/financeiro")
    assert "inactive" in r2.text.lower()


def test_enable_mailbox_success():
    _login()
    client.post("/dashboard/mailboxes/financeiro/enable", follow_redirects=False)
    r = client.get("/dashboard/mailboxes/financeiro")
    assert "active" in r.text.lower()


def test_disable_address_success():
    _login()
    r = client.post("/dashboard/addresses/1/disable", follow_redirects=False)
    assert r.status_code == 302


def test_enable_address_success():
    _login()
    r = client.post("/dashboard/addresses/1/enable", follow_redirects=False)
    assert r.status_code == 302

