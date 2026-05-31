#!/usr/bin/env python3
"""SMTP / SES configuration loaded from .env."""

import ipaddress
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(ENV_PATH, override=True)
except ImportError:
    pass


def _env(name, default=None):
    return os.getenv(name, default)


def _int_env(name, default):
    return int(_env(name, str(default)))


# ── logging (same format as worker.py) ───────────────────────────────────
def log(level, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr if level == "ERROR" else sys.stdout
    print(f"[{ts}] [{level}] {msg}", file=stream)


# ── local SMTP server ────────────────────────────────────────────────────
LOCAL_SMTP_HOST = _env("LOCAL_SMTP_HOST", "0.0.0.0")
LOCAL_SMTP_PORT = _int_env("LOCAL_SMTP_PORT", 2525)
_ALLOWED_RAW = _env("LOCAL_SMTP_ALLOWED_NETWORKS", "127.0.0.1/32,10.10.10.0/24,100.64.0.0/10")
ALLOWED_NETWORKS = [
    ipaddress.ip_network(n.strip())
    for n in _ALLOWED_RAW.split(",")
    if n.strip()
]


def is_ip_allowed(ip_str):
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return any(addr in net for net in ALLOWED_NETWORKS)


# ── Amazon SES SMTP relay ────────────────────────────────────────────────
SES_SMTP_HOST = _env("SES_SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
SES_SMTP_PORT = _int_env("SES_SMTP_PORT", 587)
SES_SMTP_USERNAME = _env("SES_SMTP_USERNAME", "")
SES_SMTP_PASSWORD = _env("SES_SMTP_PASSWORD", "")
SES_STARTTLS = _env("SES_SMTP_STARTTLS", "true").lower() == "true"

DEFAULT_FROM_DOMAIN = _env("DEFAULT_FROM_DOMAIN", "inbox.ricardo.vc")

# ── paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(_env("BASE_DIR", str(PROJECT_ROOT)))
DB_PATH = BASE_DIR / "data" / "mailbox.db"
RAW_OUTBOUND_DIR = BASE_DIR / "data" / "raw-outbound"
SENT_MAILDIR_BASE = Path(
    _env("SENT_MAILDIR", str(BASE_DIR / "data" / "maildir" / "master" / ".Sent"))
)
SENT_CUR = SENT_MAILDIR_BASE / "cur"
SENT_NEW = SENT_MAILDIR_BASE / "new"
SENT_TMP = SENT_MAILDIR_BASE / "tmp"
