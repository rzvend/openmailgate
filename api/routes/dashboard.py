"""Dashboard web routes — read-only HTML views."""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

import worker.dovecot_users as du

from api.auth import require_login
from config import DB_PATH, DOVECOT_USERS_FILE, IMAP_BIND, IMAP_PORT, MAILDIR_BASE, S3_BUCKET, S3_PROCESSED_PREFIX, SMTP_BIND, SMTP_PORT
from database import (
    clear_catch_all_mailbox,
    clear_inbound_archive_mailbox,
    clear_outbound_archive_mailbox,
    count_active_operators,
    create_mailbox_with_address,
    create_operator,
    get_catch_all_mailbox,
    get_email_address,
    get_inbound_archive_mailbox,
    get_mailbox_addresses,
    get_mailbox_by_slug,
    get_mailbox_counts,
    get_mailboxes,
    get_message,
    get_message_events,
    get_message_mailboxes,
    get_message_notes,
    get_messages_by_mailbox,
    get_operator_detail,
    get_operator_mailboxes,
    get_operator_name,
    get_operators,
    get_outbound_archive_mailbox,
    grant_operator_mailbox,
    revoke_operator_mailbox,
    set_catch_all_mailbox,
    set_email_address_active,
    set_inbound_archive_mailbox,
    set_mailbox_active,
    set_operator_active,
    set_outbound_archive_mailbox,
    update_email_address_imap_password_hash,
    update_operator_password_hash,
)

router = APIRouter(tags=["dashboard"])


@router.get("/")
def root():
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard")
def dashboard(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    boxes = get_mailboxes()
    ops = get_operators()
    result = []
    for b in boxes:
        total, inbound, outbound = get_mailbox_counts(b["id"])
        result.append({**b, "total_messages": total, "inbound_count": inbound, "outbound_count": outbound})
    return request.app.state.templates.TemplateResponse(
        request, "dashboard.html", {"mailboxes": result, "operators": ops}
    )


@router.get("/dashboard/mailboxes/new")
def new_mailbox_form(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "mailbox_new.html", {"error": None}
    )


@router.post("/dashboard/mailboxes/new")
def create_mailbox(request: Request, slug: str = Form(""), name: str = Form(""),
                   address: str = Form("")):
    _auth = require_login(request)
    if _auth: return _auth

    error = None
    slug = slug.strip().lower()
    name = name.strip()
    address = address.strip().lower()

    if not slug or not name or not address:
        error = "All fields are required."
    elif "@" not in address:
        error = "Invalid email address."

    if error:
        return request.app.state.templates.TemplateResponse(
            request, "mailbox_new.html", {"error": error}
        )

    try:
        mb = create_mailbox_with_address(slug, name, address, MAILDIR_BASE)
    except ValueError as e:
        return request.app.state.templates.TemplateResponse(
            request, "mailbox_new.html", {"error": str(e)}
        )

    return RedirectResponse(url=f"/dashboard/mailboxes/{mb['slug']}", status_code=302)


# ── mailbox wizard ────────────────────────────────────────────────────


@router.get("/dashboard/mailboxes/wizard")
def mailbox_wizard_form(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "mailbox_wizard.html", {"error": None, "result": None}
    )


@router.post("/dashboard/mailboxes/wizard")
def mailbox_wizard_submit(request: Request,
                          slug: str = Form(""), name: str = Form(""),
                          address: str = Form(""), password: str = Form(""),
                          confirm: str = Form(""), run_sync: bool = Form(False)):
    _auth = require_login(request)
    if _auth: return _auth

    error = _validate_wizard(slug, name, address, password, confirm)
    if error:
        return request.app.state.templates.TemplateResponse(
            request, "mailbox_wizard.html", {"error": error, "result": None}
        )

    result = {"mailbox_created": False, "address_created": False,
              "imap_configured": False, "sync_applied": False,
              "sync_output": "", "mailbox_slug": "", "address_email": ""}

    try:
        mb = create_mailbox_with_address(slug.strip().lower(), name.strip(),
                                         address.strip().lower(), MAILDIR_BASE)
        result["mailbox_created"] = True
        result["address_created"] = True
        result["mailbox_slug"] = mb["slug"]
        result["address_email"] = address.strip().lower()
    except ValueError as e:
        return request.app.state.templates.TemplateResponse(
            request, "mailbox_wizard.html", {"error": str(e), "result": None}
        )

    # Generate and save IMAP password hash
    try:
        proc = subprocess.run(
            ["doveadm", "pw", "-s", "SHA512-CRYPT"],
            input=f"{password}\n{password}",
            capture_output=True, text=True, timeout=10,
        )
        hashed = proc.stdout.strip().split("\n")[-1]
        if hashed.startswith("{"):
            from database import get_email_address
            addr_id = get_email_address(None)  # won't work, need to look up by actual address
            # Look up address by the email we just created
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute(
                "SELECT id FROM email_addresses WHERE address = ?",
                (address.strip().lower(),),
            ).fetchone()
            conn.close()
            if row:
                update_email_address_imap_password_hash(row[0], hashed)
                result["imap_configured"] = True
    except Exception:
        pass  # imap password step failed but mailbox exists

    # Run sync if requested
    if run_sync:
        try:
            sync_proc = subprocess.run(
                [sys.executable, "-m", "worker.mailbox_admin", "sync-imap-users", "--apply"],
                capture_output=True, text=True, timeout=30, shell=False,
            )
            result["sync_output"] = sync_proc.stdout + sync_proc.stderr
            if sync_proc.returncode == 0:
                result["sync_applied"] = True
        except Exception as e:
            result["sync_output"] = f"Sync failed: {e}"

    return request.app.state.templates.TemplateResponse(
        request, "mailbox_wizard.html", {"error": None, "result": result,
         "imap_bind": IMAP_BIND, "imap_port": IMAP_PORT,
         "smtp_bind": SMTP_BIND, "smtp_port": SMTP_PORT}
    )


def _validate_wizard(slug, name, address, password, confirm):
    slug = slug.strip().lower()
    name = name.strip()
    address = address.strip().lower()
    if not slug or not name or not address or not password:
        return "All fields are required."
    if not re.match(r"^[a-z0-9_-]+$", slug):
        return "Invalid slug — use lowercase letters, numbers, hyphen, underscore."
    if "@" not in address:
        return "Invalid email address."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Passwords do not match."
    return None


@router.get("/dashboard/mailboxes/{slug}")
def dashboard_mailbox(request: Request, slug: str, limit: int = 50, offset: int = 0, direction: str = ""):
    _auth = require_login(request)
    if _auth: return _auth
    mb = get_mailbox_by_slug(slug)
    if not mb:
        raise HTTPException(status_code=404, detail="mailbox not found")
    total, inbound, outbound = get_mailbox_counts(mb["id"])
    addresses = get_mailbox_addresses(mb["id"])
    msgs = get_messages_by_mailbox(mb["id"], limit=limit, offset=offset)
    return request.app.state.templates.TemplateResponse(
        request, "mailbox.html", {
            "mailbox": {**mb, "total_messages": total, "inbound_count": inbound, "outbound_count": outbound},
            "addresses": addresses, "messages": msgs,
            "limit": limit, "offset": offset, "direction": direction,
        }
    )


@router.get("/dashboard/messages/{message_id}")
def dashboard_message(request: Request, message_id: int):
    _auth = require_login(request)
    if _auth: return _auth
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    mailboxes = get_message_mailboxes(message_id)
    events = get_message_events(message_id)
    notes = get_message_notes(message_id)
    assigned_name = get_operator_name(msg.get("assigned_to"))
    return request.app.state.templates.TemplateResponse(
        request, "message.html", {
            "msg": msg, "mailboxes": mailboxes, "events": events,
            "notes": notes, "assigned_name": assigned_name,
        }
    )


# ── operator management ───────────────────────────────────────────────


@router.get("/dashboard/operators/new")
def operator_new_form(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "operator_new.html", {"error": None, "mailboxes": get_mailboxes()}
    )


@router.post("/dashboard/operators/new")
def operator_create(request: Request, username: str = Form(""), password: str = Form(""),
                    confirm: str = Form(""), active: bool = Form(True)):
    _auth = require_login(request)
    if _auth: return _auth
    error = _validate_operator(username, password, confirm, new_username=None)
    if error:
        return request.app.state.templates.TemplateResponse(
            request, "operator_new.html", {"error": error, "mailboxes": get_mailboxes()}
        )
    try:
        hashed = _gen_operator_hash(password)
    except Exception:
        return request.app.state.templates.TemplateResponse(
            request, "operator_new.html", {"error": "Failed to generate password hash.", "mailboxes": get_mailboxes()}
        )
    try:
        create_operator(username.strip().lower(), hashed, active=active)
    except ValueError as e:
        return request.app.state.templates.TemplateResponse(
            request, "operator_new.html", {"error": str(e), "mailboxes": get_mailboxes()}
        )
    return RedirectResponse(url=f"/dashboard/operators/{username.strip().lower()}", status_code=302)


@router.get("/dashboard/operators/{username}")
def operator_detail(request: Request, username: str):
    _auth = require_login(request)
    if _auth: return _auth
    op = get_operator_detail(username.lower().strip())
    if not op:
        raise HTTPException(status_code=404, detail="operator not found")
    all_mailboxes = get_mailboxes()
    return request.app.state.templates.TemplateResponse(
        request, "operator_detail.html",
        {"op": op, "mailboxes": all_mailboxes, "error": None}
    )


@router.post("/dashboard/operators/{username}/password")
def operator_set_password(request: Request, username: str,
                          password: str = Form(""), confirm: str = Form("")):
    _auth = require_login(request)
    if _auth: return _auth
    op = get_operator_detail(username.lower().strip())
    if not op:
        raise HTTPException(status_code=404, detail="operator not found")
    if len(password) < 8:
        error = "Password must be at least 8 characters."
    elif password != confirm:
        error = "Passwords do not match."
    else:
        try:
            hashed = _gen_operator_hash(password)
            update_operator_password_hash(username.lower().strip(), hashed)
            return RedirectResponse(url=f"/dashboard/operators/{username.lower().strip()}", status_code=302)
        except Exception:
            error = "Failed to generate password hash."
    return request.app.state.templates.TemplateResponse(
        request, "operator_detail.html",
        {"op": op, "mailboxes": get_mailboxes(), "error": error}
    )


@router.post("/dashboard/operators/{username}/disable")
def operator_disable(request: Request, username: str):
    _auth = require_login(request)
    if _auth: return _auth
    if count_active_operators() <= 1:
        return RedirectResponse(url=f"/dashboard/operators/{username}", status_code=302)
    set_operator_active(username.lower().strip(), False)
    return RedirectResponse(url=f"/dashboard/operators/{username.lower().strip()}", status_code=302)


@router.post("/dashboard/operators/{username}/enable")
def operator_enable(request: Request, username: str):
    _auth = require_login(request)
    if _auth: return _auth
    set_operator_active(username.lower().strip(), True)
    return RedirectResponse(url=f"/dashboard/operators/{username.lower().strip()}", status_code=302)


@router.post("/dashboard/operators/{username}/grant")
def operator_grant(request: Request, username: str,
                   mailbox_id: int = Form(...), role: str = Form("viewer")):
    _auth = require_login(request)
    if _auth: return _auth
    if role not in ("viewer", "admin"):
        role = "viewer"
    try:
        grant_operator_mailbox(username.lower().strip(), mailbox_id, role)
    except ValueError:
        raise HTTPException(status_code=404, detail="operator not found")
    return RedirectResponse(url=f"/dashboard/operators/{username.lower().strip()}", status_code=302)


@router.post("/dashboard/operators/{username}/revoke")
def operator_revoke(request: Request, username: str, mailbox_id: int = Form(...)):
    _auth = require_login(request)
    if _auth: return _auth
    try:
        revoke_operator_mailbox(username.lower().strip(), mailbox_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="operator not found")
    return RedirectResponse(url=f"/dashboard/operators/{username.lower().strip()}", status_code=302)


def _validate_operator(username, password, confirm, new_username):
    username = username.strip().lower()
    if not username or not password:
        return "All fields are required."
    if not re.match(r"^[a-z0-9_.-]+$", username):
        return "Invalid username — use lowercase letters, numbers, dot, hyphen, underscore."
    if len(username) < 3:
        return "Username must be at least 3 characters."
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password != confirm:
        return "Passwords do not match."
    return None


def _gen_operator_hash(password):
    result = subprocess.run(
        ["doveadm", "pw", "-s", "SHA512-CRYPT"],
        input=f"{password}\n{password}",
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError("doveadm pw failed")
    hashed = result.stdout.strip().split("\n")[-1]
    if not hashed.startswith("{"):
        raise RuntimeError("unexpected hash output")
    return hashed


@router.get("/dashboard/operators")
def dashboard_operators(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    ops = get_operators()
    op_mailboxes = {}
    for op in ops:
        op_mailboxes[op["id"]] = get_operator_mailboxes(op["id"])
    return request.app.state.templates.TemplateResponse(
        request, "operators.html", {"operators": ops, "op_mailboxes": op_mailboxes}
    )


# ── IMAP password ─────────────────────────────────────────────────────


@router.get("/dashboard/addresses/{address_id}/imap-password")
def imap_password_form(request: Request, address_id: int):
    _auth = require_login(request)
    if _auth: return _auth
    addr = get_email_address(address_id)
    if not addr:
        raise HTTPException(status_code=404, detail="address not found")
    return request.app.state.templates.TemplateResponse(
        request, "imap_password.html", {"addr": addr, "error": None}
    )


@router.post("/dashboard/addresses/{address_id}/imap-password")
def imap_password_set(request: Request, address_id: int,
                      password: str = Form(""), confirm: str = Form("")):
    _auth = require_login(request)
    if _auth: return _auth
    addr = get_email_address(address_id)
    if not addr:
        raise HTTPException(status_code=404, detail="address not found")

    error = None
    if not password:
        error = "Password cannot be empty."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif password != confirm:
        error = "Passwords do not match."

    if error:
        return request.app.state.templates.TemplateResponse(
            request, "imap_password.html", {"addr": addr, "error": error}
        )

    try:
        result = subprocess.run(
            ["doveadm", "pw", "-s", "SHA512-CRYPT"],
            input=f"{password}\n{password}",
            capture_output=True,
            text=True,
            timeout=10,
        )
        hashed = result.stdout.strip().split("\n")[-1]
        if not hashed.startswith("{"):
            raise ValueError("unexpected hash output")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="doveadm not available")
    except Exception:
        raise HTTPException(status_code=500, detail="failed to generate hash")

    update_email_address_imap_password_hash(address_id, hashed)

    slug = addr["mailbox_slug"]
    return RedirectResponse(url=f"/dashboard/mailboxes/{slug}", status_code=302)


# ── enable / disable ──────────────────────────────────────────────────


@router.post("/dashboard/mailboxes/{slug}/disable")
def disable_mailbox(request: Request, slug: str):
    _auth = require_login(request)
    if _auth: return _auth
    set_mailbox_active(slug, False)
    return RedirectResponse(url=f"/dashboard/mailboxes/{slug}", status_code=302)


@router.post("/dashboard/mailboxes/{slug}/enable")
def enable_mailbox(request: Request, slug: str):
    _auth = require_login(request)
    if _auth: return _auth
    set_mailbox_active(slug, True)
    return RedirectResponse(url=f"/dashboard/mailboxes/{slug}", status_code=302)


@router.post("/dashboard/addresses/{address_id}/disable")
def disable_address(request: Request, address_id: int):
    _auth = require_login(request)
    if _auth: return _auth
    addr = set_email_address_active(address_id, False)
    if not addr:
        raise HTTPException(status_code=404, detail="address not found")
    return RedirectResponse(url=f"/dashboard/mailboxes/{addr['mailbox_slug']}", status_code=302)


@router.post("/dashboard/addresses/{address_id}/enable")
def enable_address(request: Request, address_id: int):
    _auth = require_login(request)
    if _auth: return _auth
    addr = set_email_address_active(address_id, True)
    if not addr:
        raise HTTPException(status_code=404, detail="address not found")
    return RedirectResponse(url=f"/dashboard/mailboxes/{addr['mailbox_slug']}", status_code=302)


# ── catch-all ──────────────────────────────────────────────────────────


@router.get("/dashboard/catch-all")
def catch_all_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    current = get_catch_all_mailbox()
    boxes = get_mailboxes()
    return request.app.state.templates.TemplateResponse(
        request, "catch_all.html",
        {"current": current, "mailboxes": boxes, "error": None}
    )


@router.post("/dashboard/catch-all")
def catch_all_set(request: Request, mailbox_id: int = Form(...)):
    _auth = require_login(request)
    if _auth: return _auth
    mb = set_catch_all_mailbox(mailbox_id)
    if not mb:
        boxes = get_mailboxes()
        return request.app.state.templates.TemplateResponse(
            request, "catch_all.html",
            {"current": get_catch_all_mailbox(), "mailboxes": boxes,
             "error": "Invalid or inactive mailbox."}
        )
    return RedirectResponse(url="/dashboard/catch-all", status_code=302)


@router.post("/dashboard/catch-all/clear")
def catch_all_clear(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    clear_catch_all_mailbox()
    return RedirectResponse(url="/dashboard/catch-all", status_code=302)


# ── setup / first-run ──────────────────────────────────────────────────

SETUP_CHECK_VARS = [
    ("App", "APP_VERSION", False),
    ("App", "SESSION_SECRET", True),
    ("App", "DEFAULT_FROM_DOMAIN", False),
    ("AWS", "AWS_REGION", True),
    ("AWS", "S3_BUCKET", True),
    ("AWS", "SQS_QUEUE_URL", True),
    ("AWS", "S3_INCOMING_PREFIX", False),
    ("AWS", "S3_PROCESSED_PREFIX", False),
    ("AWS", "S3_FAILED_PREFIX", False),
    ("AWS", "SES_SMTP_HOST", False),
    ("AWS", "SES_SMTP_PORT", False),
    ("AWS", "SES_SMTP_USERNAME", True),
    ("Cloudflare", "CLOUDFLARE_ZONE_ID", True),
    ("Mail", "MASTER_MAILDIR", True),
    ("Mail", "DB_PATH", True),
    ("Mail", "LOCAL_SMTP_PORT", False),
    ("Mail", "SQS_WAIT_TIME", False),
    ("Mail", "SQS_MAX_MESSAGES", False),
]

SENSITIVE_VARS = {
    "SESSION_SECRET", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "CLOUDFLARE_API_TOKEN", "SES_SMTP_PASSWORD", "SES_SMTP_USERNAME",
}

SETUP_UNDERLYING_NAMES = {
    "S3_BUCKET": "S3_BUCKET", "SQS_QUEUE_URL": "SQS_QUEUE_URL",
    "AWS_REGION": "AWS_REGION", "CLOUDFLARE_ZONE_ID": "CLOUDFLARE_ZONE_ID",
    "SES_SMTP_HOST": "SES_SMTP_HOST", "SES_SMTP_USERNAME": "SES_SMTP_USERNAME",
    "SES_SMTP_PASSWORD": "SES_SMTP_PASSWORD",
    "MASTER_MAILDIR": "MASTER_MAILDIR", "DB_PATH": "DB_PATH",
    "DEFAULT_FROM_DOMAIN": "DEFAULT_FROM_DOMAIN",
}


def _get_setup_status():
    import os
    rows = []
    for group, var_name, required in SETUP_CHECK_VARS:
        env_name = SETUP_UNDERLYING_NAMES.get(var_name, var_name)
        value = os.getenv(env_name, "")
        configured = bool(value and value not in ("", "CHANGE_ME"))
        sensitive = var_name in SENSITIVE_VARS
        rows.append({
            "group": group, "var": var_name, "required": required,
            "configured": configured, "sensitive": sensitive,
        })
    return rows


@router.get("/dashboard/setup")
def setup_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    from config import APP_VERSION
    rows = _get_setup_status()
    return request.app.state.templates.TemplateResponse(
        request, "setup.html",
        {"rows": rows, "version": APP_VERSION}
    )


# ── setup credentials ──────────────────────────────────────────────────


@router.get("/dashboard/setup/credentials")
def setup_credentials_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "setup_credentials.html", {"result": None, "error": None}
    )

import re as _re
import os as _os
import subprocess as _sp
import fcntl as _fcntl


def _sanitize_setup_log(text):
    """Mask sensitive values in setup command output."""
    secrets = [
        _os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        _os.getenv("AWS_ACCESS_KEY_ID", ""),
        _os.getenv("CLOUDFLARE_API_TOKEN", ""),
        _os.getenv("SESSION_SECRET", ""),
    ]
    for s in secrets:
        if s and len(s) > 4:
            text = text.replace(s, "***MASKED***")
    # Also mask key=value patterns
    text = _re.sub(r'(AWS_SECRET_ACCESS_KEY\s*=\s*)\S+', r'\1***MASKED***', text)
    text = _re.sub(r'(CLOUDFLARE_API_TOKEN\s*=\s*)\S+', r'\1***MASKED***', text)
    return text


_IAC_LOCK_FILE = "/app/logs/setup/iac.lock"


def _acquire_iac_lock():
    try:
        lock_dir = _os.path.dirname(_IAC_LOCK_FILE)
        if lock_dir and not _os.path.exists(lock_dir):
            _os.makedirs(lock_dir, exist_ok=True)
        lf = open(_IAC_LOCK_FILE, "w")
        _fcntl.flock(lf.fileno(), _fcntl.LOCK_EX | _fcntl.LOCK_NB)
        return lf
    except (OSError, IOError):
        return None


def _release_iac_lock(lf):
    if lf:
        try:
            _fcntl.flock(lf.fileno(), _fcntl.LOCK_UN)
            lf.close()
        except Exception:
            pass


def _run_iac_command(tool, args, workdir, env):
    binary = tool  # "terraform" or "tofu"
    try:
        result = _sp.run(
            [binary] + args,
            capture_output=True, text=True, timeout=120,
            cwd=workdir, env=env, shell=False,
        )
        output = result.stdout + result.stderr
        return result.returncode, _sanitize_setup_log(output)
    except FileNotFoundError:
        return -1, f"ERROR: {binary} binary not found. Install {tool} or check IAC_TOOL."
    except Exception as e:
        return -1, f"ERROR: {e}"


_IAC_HINT_LINK = "/docs/troubleshooting-iac.md"
_IAC_ERROR_PATTERNS = [
    ("tofu: not found", "FileNotFoundError",
     "OpenTofu missing",
     "OpenTofu binary not found inside the API container.",
    ),
    ("/app/iac", "No such file",
     "IAC_WORKDIR missing",
     "IAC_WORKDIR does not exist inside the container.",
    ),
    ("registry.opentofu.org", "could not resolve host", "i/o timeout", "context deadline exceeded",
     "DNS / registry unreachable",
     "Container DNS cannot reach the OpenTofu registry.",
    ),
    ("EntityAlreadyExists", "AlreadyExists",
     "Resource already exists",
     "The resource exists in AWS/Cloudflare but is not tracked in the current OpenTofu state.",
    ),
    ("AccessDenied", "UnauthorizedOperation",
     "AWS access denied",
     "AWS credentials are missing, invalid, expired, or lack required permissions.",
    ),
    ("InvalidClientTokenId", "SignatureDoesNotMatch", "NoCredentialProviders",
     "AWS credential issue",
     "AWS credentials are invalid or not configured.",
    ),
    ("invalid zone identifier",
     "Cloudflare token / Zone ID",
     "Check your Cloudflare Zone ID and API token permissions.",
    ),
    ("Email address is not verified", "sandbox",
     "SES sandbox",
     "The AWS SES account is in sandbox mode. Verify recipient addresses for testing or request production access.",
    ),
]


def classify_iac_error(log_text: str) -> dict | None:
    """Classify known IaC error patterns and return a hint dict, or None."""
    if not log_text:
        return None
    lower = log_text.lower()
    for patterns in _IAC_ERROR_PATTERNS:
        category = patterns[-2]
        hint = patterns[-1]
        keywords = patterns[:-2]
        if any(k.lower() in lower for k in keywords if isinstance(k, str)):
            return {
                "category": category,
                "hint": hint,
                "link": _IAC_HINT_LINK,
            }
    return None


@router.get("/dashboard/setup/iac")
def setup_iac_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    tool = _os.getenv("IAC_TOOL", "tofu")
    workdir = _os.getenv("IAC_WORKDIR", "/app/iac")
    state_dir = _os.getenv("IAC_STATE_DIR", "/app/state/iac")
    log_dir = _os.getenv("IAC_LOG_DIR", "/app/logs/setup")
    return request.app.state.templates.TemplateResponse(
        request, "setup_iac.html",
        {"tool": tool, "workdir": workdir, "state_dir": state_dir, "log_dir": log_dir,
         "output": None, "error": None}
    )


@router.post("/dashboard/setup/iac/init")
def setup_iac_init(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    tool = _os.getenv("IAC_TOOL", "tofu")
    workdir = _os.getenv("IAC_WORKDIR", "/app/iac")
    lock = _acquire_iac_lock()
    if not lock:
        return _render_iac(request, tool, workdir, output=None,
                           error="Another IAC job is already running.")
    try:
        env = {**_os.environ, "TF_IN_AUTOMATION": "true"}
        code, output = _run_iac_command(tool, ["init", "-no-color"], workdir, env)
        hint = classify_iac_error(output) if code != 0 else None
        return _render_iac(request, tool, workdir, output=output, error=None, hint=hint)
    finally:
        _release_iac_lock(lock)


@router.post("/dashboard/setup/iac/plan")
def setup_iac_plan(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    tool = _os.getenv("IAC_TOOL", "tofu")
    workdir = _os.getenv("IAC_WORKDIR", "/app/iac")
    state_dir = _os.getenv("IAC_STATE_DIR", "/app/state/iac")
    lock = _acquire_iac_lock()
    if not lock:
        return _render_iac(request, tool, workdir, output=None,
                           error="Another IAC job is already running.")
    try:
        plan_file = f"{state_dir}/last.tfplan"
        env = {**_os.environ, "TF_IN_AUTOMATION": "true"}
        code, output = _run_iac_command(tool, ["plan", "-no-color", "-out", plan_file], workdir, env)
        hint = classify_iac_error(output) if code != 0 else None
        return _render_iac(request, tool, workdir, output=output, error=None, hint=hint)
    finally:
        _release_iac_lock(lock)


@router.post("/dashboard/setup/iac/apply")
def setup_iac_apply(
    request: Request,
    confirmation: str = Form(""),
):
    _auth = require_login(request)
    if _auth: return _auth
    tool = _os.getenv("IAC_TOOL", "tofu")
    workdir = _os.getenv("IAC_WORKDIR", "/app/iac")
    state_dir = _os.getenv("IAC_STATE_DIR", "/app/state/iac")
    plan_file = f"{state_dir}/last.tfplan"
    expected = "I understand this will create/update cloud resources"

    if confirmation.strip() != expected:
        return _render_iac(request, tool, workdir, output=None,
                           error="Confirmation phrase did not match. Apply was not executed.")

    if not _os.path.exists(plan_file):
        return _render_iac(request, tool, workdir, output=None,
                           error="No plan file found. Run plan before apply.")

    lock = _acquire_iac_lock()
    if not lock:
        return _render_iac(request, tool, workdir, output=None,
                           error="Another IAC job is already running.")
    try:
        env = {**_os.environ, "TF_IN_AUTOMATION": "true"}
        code, output = _run_iac_command(tool, ["apply", plan_file], workdir, env)
        hint = classify_iac_error(output) if code != 0 else None
        return _render_iac(request, tool, workdir, output=output, error=None, hint=hint)
    finally:
        _release_iac_lock(lock)


def _render_iac(request, tool, workdir, output, error, hint=None):
    state_dir = _os.getenv("IAC_STATE_DIR", "/app/state/iac")
    log_dir = _os.getenv("IAC_LOG_DIR", "/app/logs/setup")
    return request.app.state.templates.TemplateResponse(
        request, "setup_iac.html",
        {"tool": tool, "workdir": workdir, "state_dir": state_dir, "log_dir": log_dir,
         "output": output, "error": error, "hint": hint}
    )


def _run_setup_checks():
    """Run read-only validation checks against AWS/Cloudflare. Returns list of dicts."""
    results = []
    region = _os.getenv("AWS_REGION", "")
    bucket = _os.getenv("S3_BUCKET", "")
    queue_url = _os.getenv("SQS_QUEUE_URL", "")
    cf_token = _os.getenv("CLOUDFLARE_API_TOKEN", "")
    cf_zone = _os.getenv("CLOUDFLARE_ZONE_ID", "")
    mail_domain = _os.getenv("DEFAULT_FROM_DOMAIN", "")

    # AWS STS
    try:
        import boto3
        sts = boto3.client("sts", region_name=region or "us-east-1")
        sts.get_caller_identity()
        results.append({"group": "AWS", "name": "STS caller identity", "status": "ok", "detail": "Credentials valid"})
    except Exception as e:
        msg = str(e).split(":")[-1].strip()
        results.append({"group": "AWS", "name": "STS caller identity", "status": "error", "detail": msg})

    # S3
    if bucket:
        try:
            s3 = boto3.client("s3", region_name=region or "us-east-1")
            s3.head_bucket(Bucket=bucket)
            results.append({"group": "S3", "name": "Bucket", "status": "ok", "detail": bucket})
        except Exception as e:
            msg = str(e).split(":")[-1].strip()
            results.append({"group": "S3", "name": "Bucket", "status": "error", "detail": msg})
    else:
        results.append({"group": "S3", "name": "Bucket", "status": "skipped", "detail": "S3_BUCKET not configured"})

    # SQS
    if queue_url:
        try:
            sqs = boto3.client("sqs", region_name=region or "us-east-1")
            sqs.get_queue_attributes(QueueUrl=queue_url, AttributeNames=["QueueArn"])
            results.append({"group": "SQS", "name": "Queue", "status": "ok", "detail": "Queue accessible"})
        except Exception as e:
            msg = str(e).split(":")[-1].strip()
            results.append({"group": "SQS", "name": "Queue", "status": "error", "detail": msg})
    else:
        results.append({"group": "SQS", "name": "Queue", "status": "skipped", "detail": "SQS_QUEUE_URL not configured"})

    # SES
    if mail_domain:
        try:
            ses = boto3.client("ses", region_name=region or "us-east-1")
            attrs = ses.get_identity_verification_attributes(Identities=[mail_domain])
            status = attrs.get("VerificationAttributes", {}).get(mail_domain, {}).get("VerificationStatus", "unknown")
            results.append({"group": "SES", "name": "Domain identity", "status": "ok" if status == "Success" else "warning", "detail": status})
        except Exception as e:
            msg = str(e).split(":")[-1].strip()
            results.append({"group": "SES", "name": "Domain identity", "status": "error", "detail": msg})
    else:
        results.append({"group": "SES", "name": "Domain identity", "status": "skipped", "detail": "Domain not configured"})

    # Cloudflare
    if cf_token and cf_zone:
        try:
            import httpx2 as httpx
            r = httpx.get(
                f"https://api.cloudflare.com/client/v4/zones/{cf_zone}",
                headers={"Authorization": f"Bearer {cf_token}"},
                timeout=10,
            )
            if r.status_code == 200 and r.json().get("success"):
                results.append({"group": "Cloudflare", "name": "Zone", "status": "ok", "detail": "Zone accessible"})
            else:
                results.append({"group": "Cloudflare", "name": "Zone", "status": "error", "detail": f"HTTP {r.status_code}"})
        except Exception as e:
            results.append({"group": "Cloudflare", "name": "Zone", "status": "error", "detail": str(e).split(":")[-1].strip()})
    else:
        results.append({"group": "Cloudflare", "name": "Zone", "status": "skipped", "detail": "Token or zone ID missing"})

    # DNS — deferred (no dnspython dependency)
    results.append({"group": "DNS", "name": "MX/TXT records", "status": "skipped", "detail": "Advanced DNS validation deferred"})

    return results


@router.get("/dashboard/setup/validate")
def setup_validate_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "setup_validate.html", {"results": None}
    )


@router.post("/dashboard/setup/validate/run")
def setup_validate_run(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    results = _run_setup_checks()
    return request.app.state.templates.TemplateResponse(
        request, "setup_validate.html", {"results": results}
    )


# ── setup first mailbox ────────────────────────────────────────────────


@router.get("/dashboard/setup/first-mailbox")
def setup_first_mailbox_form(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "setup_first_mailbox.html", {"result": None, "error": None}
    )


@router.post("/dashboard/setup/first-mailbox")
def setup_first_mailbox_submit(
    request: Request,
    slug: str = Form(""), name: str = Form(""),
    address: str = Form(""), password: str = Form(""),
    confirm: str = Form(""), run_sync: bool = Form(False),
):
    _auth = require_login(request)
    if _auth: return _auth

    # Validation
    if not slug or not name or not address or not password:
        error = "All fields are required."
    elif not re.match(r"^[a-z0-9_-]+$", slug.strip().lower()):
        error = "Invalid slug — use lowercase letters, numbers, hyphen, underscore."
    elif "@" not in address:
        error = "Invalid email address."
    elif len(password) < 8:
        error = "Password must be at least 8 characters."
    elif password != confirm:
        error = "Passwords do not match."
    else:
        error = None

    if error:
        return request.app.state.templates.TemplateResponse(
            request, "setup_first_mailbox.html", {"result": None, "error": error}
        )

    result = {"mailbox_created": False, "imap_configured": False,
              "sync_applied": False, "sync_output": ""}

    # Create mailbox
    try:
        mb = create_mailbox_with_address(slug.strip().lower(), name.strip(),
                                         address.strip().lower(), MAILDIR_BASE)
        result["mailbox_created"] = True
        result["address"] = address.strip().lower()
        result["slug"] = mb["slug"]
    except ValueError as e:
        return request.app.state.templates.TemplateResponse(
            request, "setup_first_mailbox.html", {"result": None, "error": str(e)}
        )

    # Set IMAP password
    try:
        hashed = subprocess.run(
            ["doveadm", "pw", "-s", "SHA512-CRYPT"],
            input=f"{password}\n{password}",
            capture_output=True, text=True, timeout=10,
        ).stdout.strip().split("\n")[-1]
        if hashed.startswith("{"):
            import sqlite3
            conn = sqlite3.connect(str(DB_PATH))
            row = conn.execute(
                "SELECT id FROM email_addresses WHERE address = ?",
                (address.strip().lower(),),
            ).fetchone()
            if row:
                update_email_address_imap_password_hash(row[0], hashed)
                result["imap_configured"] = True
            conn.close()
    except Exception:
        pass

    # Run sync
    if run_sync:
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "worker.mailbox_admin", "sync-imap-users", "--apply"],
                capture_output=True, text=True, timeout=30, shell=False,
            )
            result["sync_output"] = proc.stdout + proc.stderr
            if proc.returncode == 0:
                result["sync_applied"] = True
        except Exception as e:
            result["sync_output"] = f"Sync failed: {e}"

    return request.app.state.templates.TemplateResponse(
        request, "setup_first_mailbox.html",
        {"result": result, "imap_bind": IMAP_BIND, "imap_port": IMAP_PORT,
         "smtp_bind": SMTP_BIND, "smtp_port": SMTP_PORT, "error": None}
    )
    state_dir = _os.getenv("IAC_STATE_DIR", "/app/state/iac")
    log_dir = _os.getenv("IAC_LOG_DIR", "/app/logs/setup")
    return request.app.state.templates.TemplateResponse(
        request, "setup_iac.html",
        {"tool": tool, "workdir": workdir, "state_dir": state_dir, "log_dir": log_dir,
         "output": output, "error": error}
    )
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "setup_credentials.html", {"result": None, "error": None}
    )


@router.post("/dashboard/setup/credentials/check")
def setup_credentials_check(
    request: Request,
    source: str = Form("env"),
    aws_region: str = Form(""),
    aws_key: str = Form(""),
    aws_secret: str = Form(""),
    cf_token: str = Form(""),
    cf_zone: str = Form(""),
):
    _auth = require_login(request)
    if _auth: return _auth

    result = {"aws": "missing", "cloudflare": "missing", "source": source}
    error = None

    # Determine credentials source
    if source == "temporary":
        region = aws_region.strip()
        key = aws_key.strip()
        secret = aws_secret.strip()
        token = cf_token.strip()
        zone = cf_zone.strip()
    else:
        import os
        region = os.getenv("AWS_REGION", "")
        key = os.getenv("AWS_ACCESS_KEY_ID", "")
        secret = os.getenv("AWS_SECRET_ACCESS_KEY", "")
        token = os.getenv("CLOUDFLARE_API_TOKEN", "")
        zone = os.getenv("CLOUDFLARE_ZONE_ID", "")

    # AWS local check
    if key and secret and region:
        result["aws"] = "configured"
        # Real STS read-only validation
        try:
            import boto3
            sts = boto3.client("sts", region_name=region,
                               aws_access_key_id=key, aws_secret_access_key=secret)
            sts.get_caller_identity()
            result["aws"] = "validated"
        except Exception:
            result["aws"] = "error"

    # Cloudflare local check only (real API deferred to F.1d)
    if token and zone:
        result["cloudflare"] = "configured"

    return request.app.state.templates.TemplateResponse(
        request, "setup_credentials.html",
        {"result": result, "error": error, "source_used": source}
    )


# ── S3 cleanup dry-run ─────────────────────────────────────────────────


@router.get("/dashboard/s3-cleanup")
def s3_cleanup_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "s3_cleanup.html",
        {"result": None, "error": None,
         "default_prefix": S3_PROCESSED_PREFIX,
         "default_bucket": S3_BUCKET}
    )


@router.post("/dashboard/s3-cleanup/dry-run")
def s3_cleanup_dry_run(request: Request, prefix: str = Form(S3_PROCESSED_PREFIX),
                       older_than_days: int = Form(30), limit: int = Form(20)):
    _auth = require_login(request)
    if _auth: return _auth

    from scripts.s3_cleanup_dry_run import (
        build_report, format_bytes, list_candidates, warning_for_prefix,
    )

    candidates, scanned, error = list_candidates(
        S3_BUCKET, prefix, older_than_days, limit
    )

    if error:
        return request.app.state.templates.TemplateResponse(
            request, "s3_cleanup.html",
            {"result": None, "error": f"Unable to run S3 dry-run: {error}",
             "default_prefix": S3_PROCESSED_PREFIX, "default_bucket": S3_BUCKET}
        )

    lines = build_report(S3_BUCKET, prefix, older_than_days, candidates, scanned, limit)
    result = {
        "report": lines,
        "candidates": candidates,
        "bucket": S3_BUCKET, "prefix": prefix,
        "older_than_days": older_than_days, "limit": limit,
        "total_size": sum(c["Size"] for c in candidates),
        "warning": warning_for_prefix(prefix),
    }
    return request.app.state.templates.TemplateResponse(
        request, "s3_cleanup.html",
        {"result": result, "error": None,
         "default_prefix": S3_PROCESSED_PREFIX, "default_bucket": S3_BUCKET}
    )


# ── archive / audit ────────────────────────────────────────────────────


@router.get("/dashboard/archive")
def archive_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    inbound = get_inbound_archive_mailbox()
    outbound = get_outbound_archive_mailbox()
    return request.app.state.templates.TemplateResponse(
        request, "archive.html",
        {"inbound": inbound, "outbound": outbound, "mailboxes": get_mailboxes(), "error": None}
    )


@router.post("/dashboard/archive/inbound")
def archive_set_inbound(request: Request, mailbox_id: int = Form(...)):
    _auth = require_login(request)
    if _auth: return _auth
    if not set_inbound_archive_mailbox(mailbox_id):
        return request.app.state.templates.TemplateResponse(
            request, "archive.html",
            {"inbound": get_inbound_archive_mailbox(), "outbound": get_outbound_archive_mailbox(),
             "mailboxes": get_mailboxes(), "error": "Invalid or inactive mailbox."}
        )
    return RedirectResponse(url="/dashboard/archive", status_code=302)


@router.post("/dashboard/archive/inbound/clear")
def archive_clear_inbound(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    clear_inbound_archive_mailbox()
    return RedirectResponse(url="/dashboard/archive", status_code=302)


@router.post("/dashboard/archive/outbound")
def archive_set_outbound(request: Request, mailbox_id: int = Form(...)):
    _auth = require_login(request)
    if _auth: return _auth
    if not set_outbound_archive_mailbox(mailbox_id):
        return request.app.state.templates.TemplateResponse(
            request, "archive.html",
            {"inbound": get_inbound_archive_mailbox(), "outbound": get_outbound_archive_mailbox(),
             "mailboxes": get_mailboxes(), "error": "Invalid or inactive mailbox."}
        )
    return RedirectResponse(url="/dashboard/archive", status_code=302)


@router.post("/dashboard/archive/outbound/clear")
def archive_clear_outbound(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    clear_outbound_archive_mailbox()
    return RedirectResponse(url="/dashboard/archive", status_code=302)


# ── system status ──────────────────────────────────────────────────────


def _check_systemd(service):
    try:
        result = subprocess.run(
            ["systemctl", "is-active", service],
            capture_output=True, text=True, timeout=2, shell=False,
        )
        out = result.stdout.strip()
        return out if out else "unknown"
    except Exception:
        return "unknown"


@router.get("/dashboard/status")
def system_status(request: Request):
    _auth = require_login(request)
    if _auth: return _auth

    from config import APP_VERSION, MAILDIR_BASE, DB_PATH
    from datetime import datetime, timezone
    import sqlite3

    checks = []

    # SQLite
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("SELECT 1")
        conn.close()
        checks.append({"name": "SQLite", "status": "ok", "detail": str(DB_PATH)})
    except Exception as e:
        checks.append({"name": "SQLite", "status": "error", "detail": str(e)})

    # Maildir
    try:
        if MAILDIR_BASE.exists():
            checks.append({"name": "Maildir", "status": "ok", "detail": str(MAILDIR_BASE)})
        else:
            checks.append({"name": "Maildir", "status": "error", "detail": "missing"})
    except Exception:
        checks.append({"name": "Maildir", "status": "error", "detail": "error"})

    # Systemd services
    for svc in ("ses-s3-mailbox-api", "ses-s3-mailbox-sqs-worker",
                "ses-s3-mailbox-smtp-sender", "dovecot"):
        state = _check_systemd(svc)
        checks.append({"name": svc, "status": state, "detail": state})

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    return request.app.state.templates.TemplateResponse(
        request, "status.html",
        {"checks": checks, "version": APP_VERSION, "checked_at": now}
    )


# ── about ───────────────────────────────────────────────────────────────


@router.get("/dashboard/about")
def about_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    from config import APP_VERSION
    import os as _os
    support_url = _os.getenv("APP_SUPPORT_URL", "")
    support_label = _os.getenv("APP_SUPPORT_LABEL", "Support")
    return request.app.state.templates.TemplateResponse(
        request, "about.html",
        {"version": APP_VERSION, "support_url": support_url, "support_label": support_label}
    )


# ── IMAP sync ──────────────────────────────────────────────────────────


@router.get("/dashboard/imap-sync")
def imap_sync_page(request: Request):
    _auth = require_login(request)
    if _auth: return _auth
    return request.app.state.templates.TemplateResponse(
        request, "imap_sync.html", {"output": None, "error": None}
    )


@router.post("/dashboard/imap-sync/dry-run")
def imap_sync_dry_run(request: Request):
    _auth = require_login(request)
    if _auth: return _auth

    import sqlite3

    warning = None
    try:
        existing = du.parse_dovecot_users(DOVECOT_USERS_FILE)
    except (PermissionError, FileNotFoundError) as e:
        warning = (
            f"Cannot read {DOVECOT_USERS_FILE} — showing database-backed users only. "
            "Existing file hashes from Dovecot are not compared."
        )
        existing = {}

    conn = sqlite3.connect(str(DB_PATH))
    try:
        lines, hash_source, kept, added, removed, pending = du.generate_entries(
            conn, existing, uid=1000, gid=1000, home="/home/ricardo"
        )
    finally:
        conn.close()

    # Build preview rows
    rows = []
    for addr in sorted(set(list(kept.keys()) + list(pending.keys()))):
        src = hash_source.get(addr, "missing_hash")
        if addr in kept:
            rows.append({
                "address": addr,
                "hash_source": src,
                "hash_masked": du._mask_hash(kept[addr]),
                "status": "keep",
            })
        else:
            rows.append({
                "address": addr,
                "hash_source": src,
                "hash_masked": "—",
                "status": "missing",
            })

    for addr in sorted(removed):
        rows.append({
            "address": addr,
            "hash_source": "removed",
            "hash_masked": "—",
            "status": "remove",
        })

    return request.app.state.templates.TemplateResponse(
        request, "imap_sync.html",
        {"output": rows, "error": None, "dry_run_done": True,
         "n_kept": len(kept), "n_pending": len(pending), "n_removed": len(removed),
         "warning": warning}
    )


@router.post("/dashboard/imap-sync/apply")
def imap_sync_apply(request: Request):
    _auth = require_login(request)
    if _auth: return _auth

    try:
        result = subprocess.run(
            [sys.executable, "-m", "worker.mailbox_admin", "sync-imap-users", "--apply"],
            capture_output=True, text=True, timeout=30, shell=False,
        )
        output = result.stdout + result.stderr
        if result.returncode != 0:
            return request.app.state.templates.TemplateResponse(
                request, "imap_sync.html",
                {"output": output, "error": "Apply failed (exit %d)." % result.returncode}
            )
    except FileNotFoundError:
        return request.app.state.templates.TemplateResponse(
            request, "imap_sync.html",
            {"output": "",
             "error": "sync-imap-users not available. Ensure the container image includes worker.mailbox_admin."}
        )
    except Exception as e:
        return request.app.state.templates.TemplateResponse(
            request, "imap_sync.html",
            {"output": "", "error": f"Apply failed: {e}"}
        )

    return request.app.state.templates.TemplateResponse(
        request, "imap_sync.html",
        {"output": output, "error": None, "apply_done": True}
    )
