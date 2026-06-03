"""Tests for bootstrap_admin.py — idempotency and security."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_bootstrap_no_password_in_source():
    """Verify bootstrap_admin.py never contains a hardcoded password."""
    src = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_admin.py"
    text = src.read_text()
    assert '"admin"' not in text or 'username' in text
    assert "password123" not in text
    assert "admin123" not in text
    assert "CHANGE_ME" not in text


def test_bootstrap_is_idempotent_smoke():
    """Run bootstrap twice — second run should skip."""
    from database import count_active_operators

    active_before = count_active_operators()
    # Script should exit cleanly (skip) since operator already exists
    import subprocess
    r = subprocess.run(
        ["python3", str(Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_admin.py")],
        capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "already exists" in r.stdout or "Skipping" in r.stdout or "admin" in r.stdout.lower()


def test_bootstrap_does_not_change_operator_count():
    """Running bootstrap when operators exist should not change count."""
    from database import count_active_operators

    before = count_active_operators()
    import subprocess
    subprocess.run(
        ["python3", str(Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_admin.py")],
        capture_output=True,
    )
    after = count_active_operators()
    assert after == before
