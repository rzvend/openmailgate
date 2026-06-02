"""Pydantic schemas for API responses."""

from typing import Optional

from pydantic import BaseModel


# ── health ────────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str


# ── mailboxes ─────────────────────────────────────────────────────────────


class EmailAddressOut(BaseModel):
    id: int
    mailbox_id: int
    address: str
    is_primary: int
    is_active: int
    created_at: Optional[str] = None


class MailboxOut(BaseModel):
    id: int
    slug: str
    name: str
    is_active: int
    maildir_path: str
    created_at: Optional[str] = None
    total_messages: int = 0
    inbound_count: int = 0
    outbound_count: int = 0


class MailboxDetailOut(MailboxOut):
    addresses: list[EmailAddressOut] = []


# ── messages ──────────────────────────────────────────────────────────────


class MessageOut(BaseModel):
    id: int
    direction: Optional[str] = None
    sender: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None
    internal_status: Optional[str] = None
    assigned_to: Optional[int] = None
    processed_at: Optional[str] = None
    sent_at: Optional[str] = None
    role: Optional[str] = None


class MessageDetailOut(BaseModel):
    id: int
    direction: Optional[str] = None
    sender: Optional[str] = None
    recipient: Optional[str] = None
    subject: Optional[str] = None
    status: Optional[str] = None
    internal_status: Optional[str] = None
    assigned_to: Optional[int] = None
    message_id: Optional[str] = None
    thread_id: Optional[str] = None
    processed_at: Optional[str] = None
    sent_at: Optional[str] = None
    delivery_status: Optional[str] = None
    delivery_action: Optional[str] = None
    diagnostic_code: Optional[str] = None
    bounced_at: Optional[str] = None
    delivered_at: Optional[str] = None
    local_maildir_path: Optional[str] = None


class MessageMailboxOut(BaseModel):
    mailbox_id: int
    slug: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    maildir_path: Optional[str] = None
    created_at: Optional[str] = None


class MessageEventOut(BaseModel):
    id: int
    event_type: str
    event_time: Optional[str] = None
    source: Optional[str] = None
    final_recipient: Optional[str] = None
    action: Optional[str] = None
    status_code: Optional[str] = None
    diagnostic_code: Optional[str] = None
    related_message_id: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: Optional[str] = None


# ── operators ─────────────────────────────────────────────────────────────


class OperatorOut(BaseModel):
    id: int
    username: str
    is_active: int
    created_at: Optional[str] = None
    mailbox_count: int = 0


class OperatorMailboxOut(BaseModel):
    mailbox_id: int
    slug: str
    name: str
    role: str


class OperatorDetailOut(BaseModel):
    id: int
    username: str
    is_active: int
    created_at: Optional[str] = None
    mailboxes: list[OperatorMailboxOut] = []
