"""Dashboard HTML view tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _login():
    client.post("/auth/login", data={"username": "ricardo", "password": "unit-test-password-only"})


def test_dashboard_home():
    _login()
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "master" in response.text


def test_dashboard_mailbox():
    _login()
    response = client.get("/dashboard/mailboxes/master")
    assert response.status_code == 200
    assert "Master" in response.text


def test_dashboard_mailbox_not_found():
    _login()
    response = client.get("/dashboard/mailboxes/naoexiste")
    assert response.status_code == 404


def test_dashboard_message_not_found():
    _login()
    response = client.get("/dashboard/messages/99999")
    assert response.status_code == 404


def test_dashboard_operators():
    _login()
    response = client.get("/dashboard/operators")
    assert response.status_code == 200
    assert "Operators" in response.text
    assert "ricardo" in response.text
    assert "password_hash" not in response.text


def test_root_redirects():
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
