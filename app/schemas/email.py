"""Email workflow shapes for artifacts and classification."""

from __future__ import annotations

from enum import Enum


class EmailIntent(str, Enum):
    """High-level email workflow intent (stub classifier)."""

    inbox_read = "inbox_read"
    draft_reply = "draft_reply"
    outbound_send = "outbound_send"
