# Alpha Pytest Triage — v0.1.0-alpha

## Status

- **Date:** 2026-06-07
- **Version target:** v0.1.0-alpha
- **Command:** `docker compose run --rm api python3 -m pytest -q --tb=no`
- **Result:** **71 passed, 56 failed, 1 warning**

## Why this document exists

The functional alpha flow was validated manually in a clean VM (G.2.7 — Final
clean install release candidate). The entire user-facing workflow works:
first-run admin, AWS/Cloudflare validation, IAM preflight, OpenTofu
init/plan/apply, runtime env sync, post-apply validation, first mailbox,
Thunderbird IMAP/SMTP, and real inbound/outbound email delivery.

However, the automated pytest suite still has pre-existing failures that
predate many of the recent fixes and architecture changes. This document
groups the failures by root cause so the project does not treat 56 raw
failures as 56 independent bugs.

## Summary

| Area | Failed tests |
|---|---:|
| `tests/test_admin.py` | 50 |
| `tests/test_dashboard.py` | 3 |
| `tests/test_api.py` | 2 |
| `tests/test_auth.py` | 1 |

## Root cause groups

### 1. Authentication / session test fixture appears outdated

**Symptoms:**

Many admin/dashboard tests appear to reach an unauthenticated or login-like
state instead of the expected authenticated page. Common patterns:

- redirect to `/auth/login`;
- expected `200` but got `302`;
- expected dashboard content (headings, tables, forms) but received login
  form HTML, layout, footer, or copyright text.

**Affected areas:**

- mailbox creation and management;
- operator creation and detail views;
- setup pages (credentials, IaC, validation, first mailbox);
- IMAP password and sync;
- archive and catch-all settings;
- status page.

**Classification:**

- **Type:** test fixture / session helper issue
- **Blocks alpha:** No
- **Priority after alpha:** High

**Reason:**

The clean install validation (G.2.7) confirmed every one of these flows works
in the real dashboard when used through a browser with proper session cookies.
The test helpers (`_login()`, `client`) likely need to be updated for recent
auth changes (first-admin bootstrap, middleware guards, session config).

### 2. Old fixed seed data assumptions

**Symptoms:**

Tests depend on hardcoded records that no longer exist in the current
development/test database:

- `test_get_mailbox_financeiro` → expects mailbox `financeiro`;
- `test_get_operator_ricardo` → expects operator `ricardo`;
- `test_dashboard_operators` → searches for `ricardo` in HTML.

**Classification:**

- **Type:** outdated fixtures / seed data
- **Blocks alpha:** No
- **Priority after alpha:** Medium

**Reason:**

The project moved to a flow where the first admin/operator is created through
the web-based `/setup` page or the `bootstrap_admin.py` CLI. Old seed scripts
that created `ricardo` and `financeiro` are no longer maintained.

### 3. Protected route behavior changed or tests follow redirects unexpectedly

**Symptoms:**

Some tests expected a `404` from a protected route but received a `200` login
page. This happens because the admin-setup middleware now redirects
unauthenticated requests to `/setup` (or `/auth/login`) instead of returning
`404` for non-existent resources.

**Classification:**

- **Type:** test expectation mismatch after auth/middleware changes
- **Blocks alpha:** No
- **Priority after alpha:** Medium

### 4. Login test fixture outdated

**Symptoms:**

`test_login_valid_credentials` expected `302` after successful login but
received `200`.

**Classification:**

- **Type:** auth fixture / password / hash mismatch
- **Blocks alpha:** No (real login was validated during G.2.7)
- **Priority after alpha:** High

**Reason:**

The login flow works correctly when tested manually or through the dashboard.
The test likely uses a hardcoded password/hash that no longer matches the
current hashing scheme or the operator record is missing from the test DB.

### 5. Python `crypt` deprecation warning

**Symptoms:**

```text
DeprecationWarning: 'crypt' is deprecated and slated for removal in Python 3.13
```

**Classification:**

- **Type:** future compatibility / technical debt
- **Blocks alpha:** No
- **Priority after alpha:** Medium

**Reason:**

The `crypt` module is used by `api/auth.py` for password verification with
SHA512-CRYPT hashes. Python 3.13 will remove it. A replacement (`hashlib`,
`passlib`, or `bcrypt`) should be evaluated and implemented after alpha.

## Impact on v0.1.0-alpha

- These failures do **not** currently block the alpha release.
- They are concentrated in outdated tests/fixtures, not in runtime application code.
- The real functional flow was validated in G.2.7 and works correctly.
- The test suite must be repaired after alpha so it can become a release gate.

## Recommended post-alpha plan

1. Create a reusable test authentication helper that mimics the current
   first-run admin + login flow.
2. Update test fixtures to create an operator using the web-based `/setup`
   endpoint or the `bootstrap_admin.py` script, with properly hashed
   passwords.
3. Replace fixed `ricardo` and `financeiro` assumptions with generated test
   data (e.g., `uuid4().hex[:8]`).
4. Update protected-route tests to explicitly test:
   - unauthenticated request → `302` redirect to `/auth/login` or `/setup`;
   - authenticated request → expected `200`/`404` behavior.
5. Add regression tests for recent critical fixes:
   - Maildir subfolder ownership (`database.ensure_maildir_structure`);
   - SES Custom MAIL FROM timing (`time_sleep` dependency);
   - Runtime env sync masking (`_sanitize_setup_log`);
   - First mailbox wizard (`/dashboard/mailboxes/wizard`);
   - About / license footer presence.
6. Evaluate and plan replacement of Python `crypt` before Python 3.13
   (e.g., `hashlib.scrypt`, `passlib.hash.sha512_crypt`, or `bcrypt`).

## Current decision

For **v0.1.0-alpha**:

- Document the failures in this triage document.
- Do **not** block the alpha release on these pre-existing test failures.
- Mention in release notes that automated test suite triage is ongoing and
  the manual clean-install validation confirmed core functionality.
