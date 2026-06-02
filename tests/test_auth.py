"""Authentication tests."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def test_login_page_loads():
    response = client.get("/auth/login")
    assert response.status_code == 200
    assert "Login" in response.text


def test_dashboard_redirects_when_not_authenticated():
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers.get("location", "")


def test_login_invalid_credentials():
    response = client.post(
        "/auth/login", data={"username": "fake", "password": "wrong"}
    )
    assert response.status_code == 200
    assert "Invalid" in response.text


def test_login_valid_credentials():
    response = client.post(
        "/auth/login", data={"username": "ricardo", "password": "unit-test-password-only"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "/dashboard" in response.headers.get("location", "")


def test_dashboard_accessible_after_login():
    # Login first
    client.post("/auth/login", data={"username": "ricardo", "password": "unit-test-password-only"})
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard" in response.text


def test_logout():
    client.post("/auth/login", data={"username": "ricardo", "password": "unit-test-password-only"})
    response = client.post("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    # After logout, dashboard should redirect again
    response2 = client.get("/dashboard", follow_redirects=False)
    assert response2.status_code == 302
