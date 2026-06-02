"""GET /mailboxes, GET /mailboxes/{slug}, GET /mailboxes/{slug}/messages."""

from fastapi import APIRouter, HTTPException

from api.schemas import MailboxDetailOut, MailboxOut, MessageOut
from database import (
    get_mailbox_addresses,
    get_mailbox_by_slug,
    get_mailbox_counts,
    get_mailboxes,
    get_messages_by_mailbox,
)

router = APIRouter(prefix="/mailboxes", tags=["mailboxes"])


@router.get("", response_model=list[MailboxOut])
def list_mailboxes():
    boxes = get_mailboxes()
    result = []
    for b in boxes:
        total, inbound, outbound = get_mailbox_counts(b["id"])
        result.append(
            MailboxOut(
                **b,
                total_messages=total,
                inbound_count=inbound,
                outbound_count=outbound,
            )
        )
    return result


@router.get("/{slug}", response_model=MailboxDetailOut)
def get_mailbox(slug: str):
    mb = get_mailbox_by_slug(slug)
    if not mb:
        raise HTTPException(status_code=404, detail="mailbox not found")
    total, inbound, outbound = get_mailbox_counts(mb["id"])
    addresses = get_mailbox_addresses(mb["id"])
    return MailboxDetailOut(
        **mb,
        total_messages=total,
        inbound_count=inbound,
        outbound_count=outbound,
        addresses=addresses,
    )


@router.get("/{slug}/messages", response_model=list[MessageOut])
def list_mailbox_messages(slug: str, limit: int = 50, offset: int = 0, direction: str | None = None):
    mb = get_mailbox_by_slug(slug)
    if not mb:
        raise HTTPException(status_code=404, detail="mailbox not found")
    msgs = get_messages_by_mailbox(mb["id"], limit=limit, offset=offset)
    result = []
    for m in msgs:
        if direction and m.get("direction") != direction:
            continue
        result.append(
            MessageOut(
                id=m["id"],
                direction=m.get("direction"),
                sender=m.get("sender"),
                recipient=m.get("recipient"),
                subject=m.get("subject"),
                status=m.get("status"),
                internal_status=m.get("internal_status"),
                assigned_to=m.get("assigned_to"),
                processed_at=m.get("processed_at"),
                sent_at=m.get("sent_at"),
                role=m.get("mm_role"),
            )
        )
    return result
