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
    _login()
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": "master", "name": "X", "address": "x@test.com"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "already exists" in response.text


def test_create_mailbox_success():
    _login()
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": "testw3", "name": "Test W3", "address": "testw3@test.com"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard/mailboxes/testw3" in response.headers.get("location", "")


def test_create_mailbox_duplicate_address():
    _login()
    response = client.post(
        "/dashboard/mailboxes/new",
        data={"slug": "testw4", "name": "T4", "address": "testw3@test.com"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "already exists" in response.text
