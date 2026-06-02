"""FastAPI application — SES S3 Mailbox read-only API + dashboard."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader
from starlette.templating import Jinja2Templates

from api.routes import dashboard, health, mailboxes, messages, operators

app = FastAPI(title="SES S3 Mailbox API", version="0.1.0")

# Jinja2 templates with bytecode cache disabled (avoids unhashable dict errors)
env = Environment(loader=FileSystemLoader(str(Path(__file__).parent / "templates")), cache_size=0)
templates = Jinja2Templates(env=env)
app.state.templates = templates

# API routes
app.include_router(health.router)
app.include_router(mailboxes.router)
app.include_router(messages.router)
app.include_router(operators.router)

# Dashboard routes
app.include_router(dashboard.router)

# Static files (must come after all routers)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
