"""FastAPI application — SES S3 Mailbox read-only API + dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates

from config import SESSION_SECRET
from api.routes import auth, dashboard, health, mailboxes, messages, operators

app = FastAPI(title="SES S3 Mailbox API", version="0.2.0")

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
