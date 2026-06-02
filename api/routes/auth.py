"""GET/POST /auth/login, POST /auth/logout."""

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from api.auth import authenticate_operator

router = APIRouter(tags=["auth"])


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
