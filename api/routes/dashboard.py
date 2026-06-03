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
    create_mailbox_with_address,
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
    get_operator_mailboxes,
    get_operator_name,
    get_operators,
    update_email_address_imap_password_hash,
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
