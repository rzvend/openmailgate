"""Basic API tests using FastAPI TestClient."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_mailboxes():
    response = client.get("/mailboxes")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(b["slug"] == "master" for b in data)


def test_get_mailbox_financeiro():
    response = client.get("/mailboxes/financeiro")
    assert response.status_code == 200
    data = response.json()
    assert data["slug"] == "financeiro"
    assert "addresses" in data


def test_get_mailbox_not_found():
    response = client.get("/mailboxes/naoexiste")
    assert response.status_code == 404


def test_get_message_not_found():
    response = client.get("/messages/99999")
    assert response.status_code == 404


def test_list_operators():
    response = client.get("/operators")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # No password_hash exposed
    for op in data:
        assert "password_hash" not in op


def test_get_operator_ricardo():
    response = client.get("/operators/ricardo")
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "ricardo"
    assert "password_hash" not in data
