"""Shared IaC configuration helpers — domain, placeholders, env vars.

Used by both api/routes/dashboard.py and api/iac_recovery.py to avoid
circular imports.
"""

import os

_PLACEHOLDER_VALUES = frozenset({
    "change_me", "changeme", "fill_me", "fill_after_terraform_apply",
    "todo", "replace_me", "example", "example_com", "your_value",
    "your_domain_com", "your-domain.com",
})


def is_placeholder(value):
    """Return True if *value* is a known placeholder that should be treated as unset."""
    if not value:
        return True
    v = value.strip().lower().replace("-", "_").replace(" ", "_")
    return v in _PLACEHOLDER_VALUES or "change_me" in v or "fill_me" in v


def env_or_none(name):
    """Return the env var value, or None if empty or a placeholder."""
    value = os.getenv(name)
    if value and not is_placeholder(value):
        return value.strip()
    return None


def iac_mail_domain():
    """Return the canonical mail domain for IaC operations, or empty string.

    Priority: MAIL_DOMAIN > DEFAULT_FROM_DOMAIN.
    Strips inline comments (# ...) and rejects placeholder values.
    """
    mail = os.getenv("MAIL_DOMAIN")
    default_from = os.getenv("DEFAULT_FROM_DOMAIN")

    def _clean(raw):
        if not raw:
            return ""
        return raw.split("#", 1)[0].strip()

    mail = _clean(mail)
    default_from = _clean(default_from)

    def _valid(d):
        if not d:
            return False
        d_lower = d.lower()
        bad_markers = ("example.com", "e.g.", "change_me", "changeme",
                       "fill_me", "todo", "replace_me", "your-domain")
        return not any(p in d_lower for p in bad_markers)

    if _valid(mail):
        return mail
    if _valid(default_from):
        return default_from
    return ""
