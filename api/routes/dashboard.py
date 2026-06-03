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
from config import DB_PATH, MAILDIR_BASE
from database import (
    clear_catch_all_mailbox,
    count_active_operators,
    create_mailbox_with_address,
    create_operator,
    get_catch_all_mailbox,
    get_email_address,
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
    grant_operator_mailbox,
    revoke_operator_mailbox,
    set_catch_all_mailbox,
    set_email_address_active,
    set_mailbox_active,
    set_operator_active,
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
        wrapper = Path(__file__).resolve().parents[2] / "scripts" / "sync_imap_users_apply.sh"
        try:
            sync_proc = subprocess.run(
                ["sudo", str(wrapper)],
                capture_output=True, text=True, timeout=30, shell=False,
            )
            result["sync_output"] = sync_proc.stdout + sync_proc.stderr
            if sync_proc.returncode == 0:
                result["sync_applied"] = True
        except Exception as e:
            result["sync_output"] = f"Sync failed: {e}"

    return request.app.state.templates.TemplateResponse(
        request, "mailbox_wizard.html", {"error": None, "result": result}
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
        existing = du.parse_dovecot_users("/etc/dovecot/users")
    except (PermissionError, FileNotFoundError) as e:
        warning = (
            "Cannot read /etc/dovecot/users — showing database-backed users only. "
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

    wrapper = Path(__file__).resolve().parents[2] / "scripts" / "sync_imap_users_apply.sh"
    try:
        result = subprocess.run(
            ["sudo", str(wrapper)],
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
             "error": "sudo not available. Configure sudoers for scripts/sync_imap_users_apply.sh or run manually."}
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
