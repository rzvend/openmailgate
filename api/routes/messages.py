"""GET /messages/{id}, /messages/{id}/mailboxes, /messages/{id}/events, /messages/{id}/notes."""

from fastapi import APIRouter, HTTPException

from api.schemas import (
    MessageDetailOut,
    MessageEventOut,
    MessageMailboxOut,
)
from database import (
    get_message,
    get_message_events,
    get_message_mailboxes,
    get_message_notes,
)

router = APIRouter(prefix="/messages", tags=["messages"])


@router.get("/{message_id}", response_model=MessageDetailOut)
def get_message_detail(message_id: int):
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    return MessageDetailOut(**msg)


@router.get("/{message_id}/mailboxes", response_model=list[MessageMailboxOut])
def list_message_mailboxes(message_id: int):
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    return [MessageMailboxOut(**m) for m in get_message_mailboxes(message_id)]


@router.get("/{message_id}/events", response_model=list[MessageEventOut])
def list_message_events(message_id: int):
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    return [MessageEventOut(**e) for e in get_message_events(message_id)]


@router.get("/{message_id}/notes", response_model=list[MessageEventOut])
def list_message_notes(message_id: int):
    msg = get_message(message_id)
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    notes = get_message_notes(message_id)
    return [MessageEventOut(**n) for n in notes]
