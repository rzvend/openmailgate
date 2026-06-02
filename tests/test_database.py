"""Basic tests for database.py read-only queries."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_get_mailboxes():
    from database import get_mailboxes

    boxes = get_mailboxes()
    assert len(boxes) >= 1
    master = [b for b in boxes if b["slug"] == "master"]
    assert len(master) == 1
    assert master[0]["is_active"] == 1


def test_get_messages_by_mailbox():
    from database import get_messages_by_mailbox

    msgs = get_messages_by_mailbox(1, limit=5)
    assert len(msgs) >= 1
    assert all(m["mailbox_id"] is not None for m in msgs)


def test_get_message():
    from database import get_message, get_messages_by_mailbox

    msgs = get_messages_by_mailbox(1, limit=1)
    if not msgs:
        return  # no messages, skip
    msg = get_message(msgs[0]["id"])
    assert msg is not None
    assert msg["id"] == msgs[0]["id"]
