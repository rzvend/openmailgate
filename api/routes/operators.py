"""GET /operators, GET /operators/{username}."""

from fastapi import APIRouter, HTTPException

from api.schemas import OperatorDetailOut, OperatorMailboxOut, OperatorOut
from database import (
    get_operator_by_username,
    get_operator_mailboxes,
    get_operators,
)

router = APIRouter(prefix="/operators", tags=["operators"])


@router.get("", response_model=list[OperatorOut])
def list_operators():
    return [OperatorOut(**o) for o in get_operators()]


@router.get("/{username}", response_model=OperatorDetailOut)
def get_operator(username: str):
    op = get_operator_by_username(username.lower().strip())
    if not op:
        raise HTTPException(status_code=404, detail="operator not found")
    mailboxes = get_operator_mailboxes(op["id"])
    return OperatorDetailOut(
        **op,
        mailboxes=[OperatorMailboxOut(**m) for m in mailboxes],
    )
