#!/usr/bin/env python3
"""Bootstrap the initial admin operator or reset the admin password.

Without flags, creates an 'admin' operator with a random password if no
active operator exists yet.  Idempotent — does nothing if at least one
active operator is already present.

With --reset, resets the password for the 'admin' operator and prints a
new random password once.

Intended for first-run / Docker deployment (install.sh).
"""

import argparse
import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import (  # noqa: E402
    count_active_operators,
    create_operator,
    get_operator_detail,
    update_operator_password_hash,
)


def _generate_hash(password):
    """Return a SHA512-CRYPT hash for *password* via doveadm pw."""
    try:
        result = subprocess.run(
            ["doveadm", "pw", "-s", "SHA512-CRYPT"],
            input=f"{password}\n{password}",
            capture_output=True, text=True, timeout=10,
        )
        hashed = result.stdout.strip().split("\n")[-1]
        if not hashed.startswith("{"):
            print("ERROR: doveadm pw returned unexpected output", file=sys.stderr)
            sys.exit(1)
        return hashed
    except FileNotFoundError:
        print("ERROR: doveadm not found — install dovecot-core", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: failed to generate password hash: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_reset():
    """Reset the password for the 'admin' operator."""
    username = "admin"
    op = get_operator_detail(username)
    if not op:
        print(f"ERROR: operator '{username}' not found. Run bootstrap first.", file=sys.stderr)
        sys.exit(1)

    password = secrets.token_urlsafe(18)
    hashed = _generate_hash(password)
    update_operator_password_hash(username, hashed)

    print("Admin password reset.")
    print("")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print("")
    print("Save this password now. It will not be shown again.")
    print("Log in and change it immediately from the dashboard.")


def cmd_bootstrap():
    """Create the initial admin operator if none exists."""
    if count_active_operators() > 0:
        print("Active operator already exists. Skipping admin bootstrap.")
        print("Use --reset to change the admin password.")
        return

    username = "admin"
    password = secrets.token_urlsafe(18)
    hashed = _generate_hash(password)

    try:
        create_operator(username, hashed, active=True)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("Initial admin operator created.")
    print("")
    print(f"  Username: {username}")
    print(f"  Password: {password}")
    print("")
    print("Save this password now. It will not be shown again.")
    print("Log in and change it immediately from the dashboard.")


def main():
    parser = argparse.ArgumentParser(description="Bootstrap or reset admin operator")
    parser.add_argument("--reset", action="store_true", help="Reset admin password")
    args = parser.parse_args()

    if args.reset:
        cmd_reset()
    else:
        cmd_bootstrap()


if __name__ == "__main__":
    main()
