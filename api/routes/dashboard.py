"""Dashboard web routes — read-only HTML views."""

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

import subprocess

from api.auth import require_login
from config import MAILDIR_BASE
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
