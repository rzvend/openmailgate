"""Centralized configuration loaded once from .env.

All modules should import from here instead of calling load_dotenv() or
os.getenv() directly.  This ensures one source of truth for config values.
"""

import ipaddress
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
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


# ── AWS / S3 ─────────────────────────────────────────────────────────────
AWS_REGION = _env("AWS_REGION", "us-east-1")
S3_BUCKET = _env("S3_BUCKET", "ricardo-vc-ses-mailbox")
S3_INCOMING_PREFIX = _env("S3_INCOMING_PREFIX", "incoming/")
S3_PROCESSED_PREFIX = _env("S3_PROCESSED_PREFIX", "processed/")
S3_FAILED_PREFIX = _env("S3_FAILED_PREFIX", "failed/")
SETUP_NOTIFICATION_KEY = f"{S3_INCOMING_PREFIX.rstrip('/')}/AMAZON_SES_SETUP_NOTIFICATION"

# ── SQS ──────────────────────────────────────────────────────────────────
SQS_QUEUE_URL = _env("SQS_QUEUE_URL", "")
SQS_WAIT_TIME = int(_env("SQS_WAIT_TIME_SECONDS", "20"))
SQS_MAX_MESSAGES = int(_env("SQS_MAX_MESSAGES", "10"))

# ── paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(_env("BASE_DIR", str(PROJECT_ROOT)))
DB_PATH = BASE_DIR / "data" / "mailbox.db"
RAW_EMAILS_DIR = BASE_DIR / "data" / "raw-emails"
RAW_OUTBOUND_DIR = BASE_DIR / "data" / "raw-outbound"

MASTER_MAILDIR = Path(
    _env("MASTER_MAILDIR", str(BASE_DIR / "data" / "maildir" / "master"))
)
MAILDIR_NEW = MASTER_MAILDIR / "new"

MAILDIR_BASE = MASTER_MAILDIR.parent  # data/maildir

SENT_MAILDIR_BASE = Path(
    _env("SENT_MAILDIR", str(MASTER_MAILDIR / ".Sent"))
)
SENT_CUR = SENT_MAILDIR_BASE / "cur"
SENT_NEW = SENT_MAILDIR_BASE / "new"
SENT_TMP = SENT_MAILDIR_BASE / "tmp"

SENT_DUPES_MAILDIR = Path(
    _env("SENT_DUPLICATES_MAILDIR", str(MASTER_MAILDIR / ".SentDuplicates"))
)

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


# ── SES SMTP relay ───────────────────────────────────────────────────────
SES_SMTP_HOST = _env("SES_SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
SES_SMTP_PORT = _int_env("SES_SMTP_PORT", 587)
SES_SMTP_USERNAME = _env("SES_SMTP_USERNAME", "")
SES_SMTP_PASSWORD = _env("SES_SMTP_PASSWORD", "")
SES_STARTTLS = _env("SES_SMTP_STARTTLS", "true").lower() == "true"

DEFAULT_FROM_DOMAIN = _env("DEFAULT_FROM_DOMAIN", "inbox.ricardo.vc")

# ── session ──────────────────────────────────────────────────────────────
SESSION_SECRET = _env("SESSION_SECRET", "dev-change-me-in-production")
