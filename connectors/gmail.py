"""Gmail connector: thin read → draft → gated send path (stub or live API)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from connectors import gmail_live
from connectors.base import Connector
from connectors.errors import AuthError, PermanentProviderError


@dataclass
class GmailConfig:
    """Connector configuration; prefer `connectors.factory.get_gmail_connector()` at runtime."""

    mode: Literal["stub", "live"] = "stub"
    default_sender: str | None = None
    credentials_path: str | None = None


class GmailConnector(Connector):
    name = "gmail"

    def __init__(self, config: GmailConfig | None = None) -> None:
        self.config = config or GmailConfig()

    def health_check(self) -> dict[str, Any]:
        ok = self.config.mode == "stub" or (
            self.config.credentials_path and os.path.isfile(self.config.credentials_path)
        )
        return {
            "provider": "gmail",
            "mode": self.config.mode,
            "status": "ok" if ok else "not_configured",
        }

    def refresh_credentials(self) -> None:
        raise AuthError("OAuth refresh not implemented", provider="gmail")

    def read_thread(self, thread_id: str) -> dict[str, Any]:
        if self.config.mode == "stub":
            tid = thread_id.strip() or "unknown"
            return {
                "thread_id": tid,
                "snippet": "stub_thread",
                "message_count": 0,
                "messages": [],
            }
        service = gmail_live.build_gmail_service(self.config.credentials_path)
        return gmail_live.live_read_thread(service, thread_id)

    def create_draft(
        self,
        *,
        thread_id: str | None,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> str:
        if self.config.mode == "stub":
            _ = (thread_id, subject, body, in_reply_to)
            return f"draft:stub:{uuid.uuid4()}"
        service = gmail_live.build_gmail_service(self.config.credentials_path)
        return gmail_live.live_create_draft(
            service,
            thread_id=thread_id,
            subject=subject,
            body=body,
            sender=self.config.default_sender,
        )

    def send_approved_draft(self, draft_id: str) -> str:
        """Operator-approved send path; use only after explicit approval."""
        return self.send_message(draft_id, approved=True)

    def send_message(self, draft_id: str, *, approved: bool = False) -> str:
        if not approved:
            raise PermanentProviderError(
                "Send is gated: set approved=True only after operator approval.",
                provider="gmail",
                details={"draft_id": draft_id},
            )
        if self.config.mode == "stub":
            return f"msg:stub:{uuid.uuid4()}"
        service = gmail_live.build_gmail_service(self.config.credentials_path)
        return gmail_live.live_send_draft(service, draft_id)
