#!/usr/bin/env python3
"""Bootstrap the initial admin operator.

Creates an 'admin' operator with a random password if no active operator
exists yet.  Idempotent — does nothing if at least one active operator
is already present.

Intended for first-run / Docker deployment (install.sh).
"""

import secrets
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database import count_active_operators, create_operator  # noqa: E402


def main():
    if count_active_operators() > 0:
        print("Active operator already exists. Skipping admin bootstrap.")
        return

    username = "admin"
    password = secrets.token_urlsafe(18)

    # Generate hash — same method used by the dashboard
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
    except FileNotFoundError:
        print("ERROR: doveadm not found — install dovecot-core", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: failed to generate password hash: {e}", file=sys.stderr)
        sys.exit(1)

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


if __name__ == "__main__":
    main()
