"""FastAPI application — SES S3 Mailbox read-only API."""

from fastapi import FastAPI

from api.routes import health, mailboxes, messages, operators

app = FastAPI(title="SES S3 Mailbox API", version="0.1.0")

app.include_router(health.router)
app.include_router(mailboxes.router)
app.include_router(messages.router)
app.include_router(operators.router)
