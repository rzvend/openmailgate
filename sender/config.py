#!/usr/bin/env python3
"""SMTP / SES sender config — imports from root config.py."""

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import (  # noqa: E402
    ALLOWED_NETWORKS,
    DB_PATH,
    DEFAULT_FROM_DOMAIN,
    LOCAL_SMTP_HOST,
    LOCAL_SMTP_PORT,
    RAW_OUTBOUND_DIR,
    SENT_CUR,
    SENT_MAILDIR_BASE,
    SENT_NEW,
    SENT_TMP,
    SES_SMTP_HOST,
    SES_SMTP_PASSWORD,
    SES_SMTP_PORT,
    SES_SMTP_USERNAME,
    SES_STARTTLS,
    is_ip_allowed,
)


def log(level, msg):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    stream = sys.stderr if level == "ERROR" else sys.stdout
    print(f"[{ts}] [{level}] {msg}", file=stream)
