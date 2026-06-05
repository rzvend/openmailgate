"""GET/POST /auth/login, POST /auth/logout, GET/POST /setup (first admin)."""

import subprocess

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from api.auth import authenticate_operator

router = APIRouter(tags=["auth"])


# ── login / logout ────────────────────────────────────────────────────────


@router.get("/auth/login")
def login_page(request: Request):
    if request.session.get("operator_id"):
        return RedirectResponse(url="/dashboard", status_code=302)
    return request.app.state.templates.TemplateResponse(
        request, "login.html", {"error": None}
    )


@router.post("/auth/login")
def login_submit(request: Request, username: str = Form(""), password: str = Form("")):
    op = authenticate_operator(username, password)
    if op:
        request.session["operator_id"] = op["id"]
        request.session["username"] = op["username"]
        return RedirectResponse(url="/dashboard", status_code=302)
    return request.app.state.templates.TemplateResponse(
        request, "login.html", {"error": "Invalid username or password"}
    )


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/auth/login", status_code=302)


# ── first-admin bootstrap ─────────────────────────────────────────────────


def _gen_operator_hash(password):
    """Generate a SHA512-CRYPT hash using doveadm pw."""
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


@router.get("/setup")
def setup_admin_page(request: Request):
    from database import count_active_operators

    if count_active_operators() > 0:
        return RedirectResponse(url="/auth/login", status_code=302)
    return request.app.state.templates.TemplateResponse(
        request, "setup_admin.html", {"error": None}
    )


@router.post("/setup")
def setup_admin_submit(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    confirm: str = Form(""),
):
    from database import count_active_operators, create_operator

    if count_active_operators() > 0:
        return RedirectResponse(url="/auth/login", status_code=302)

    username = username.strip().lower()
    if not username or not password:
        return request.app.state.templates.TemplateResponse(
            request, "setup_admin.html", {"error": "All fields are required."}
        )
    if len(password) < 8:
        return request.app.state.templates.TemplateResponse(
            request, "setup_admin.html",
            {"error": "Password must be at least 8 characters."},
        )
    if password != confirm:
        return request.app.state.templates.TemplateResponse(
            request, "setup_admin.html", {"error": "Passwords do not match."}
        )

    # Race guard — re-check before creating
    if count_active_operators() > 0:
        return RedirectResponse(url="/auth/login", status_code=302)

    try:
        hashed = _gen_operator_hash(password)
        create_operator(username, hashed, active=True)
    except ValueError as e:
        return request.app.state.templates.TemplateResponse(
            request, "setup_admin.html", {"error": str(e)}
        )
    except RuntimeError as e:
        return request.app.state.templates.TemplateResponse(
            request, "setup_admin.html",
            {"error": f"Failed to generate password hash: {e}"},
        )

    return RedirectResponse(url="/auth/login", status_code=302)
