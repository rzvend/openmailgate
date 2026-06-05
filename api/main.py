"""FastAPI application — SES S3 Mailbox read-only API + dashboard."""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from config import SESSION_SECRET
from api.routes import auth, dashboard, health, mailboxes, messages, operators

app = FastAPI(title="SES S3 Mailbox API", version="0.2.0")


class AdminSetupMiddleware(BaseHTTPMiddleware):
    """Ensure admin setup is completed before allowing dashboard access."""

    async def dispatch(self, request: Request, call_next):
        from api.auth import require_admin_setup

        redirect = require_admin_setup(request)
        if redirect is not None:
            return redirect
        return await call_next(request)


app.add_middleware(AdminSetupMiddleware)

# Session (login)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

# Jinja2 templates with bytecode cache disabled (avoids unhashable dict errors)
env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")), cache_size=0)
templates = Jinja2Templates(env=env)
app.state.templates = templates

# Auth routes (public)
app.include_router(auth.router)

# API routes (public — JSON read-only)
app.include_router(health.router)
app.include_router(mailboxes.router)
app.include_router(messages.router)
app.include_router(operators.router)

# Dashboard routes (protected)
app.include_router(dashboard.router)

# Static files (must come after all routers)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
