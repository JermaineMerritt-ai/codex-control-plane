"""Gmail API (live) helpers; requires `pip install -e .[gmail]` and OAuth user token file."""

from __future__ import annotations

import base64
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from connectors.errors import AuthError, PermanentProviderError


def _require_deps() -> None:
    try:
        import google.auth.transport.requests  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError as exc:  # pragma: no cover - env dependent
        raise AuthError(
            "Gmail live mode requires optional deps: pip install 'codex-control-plane[gmail]'",
            provider="gmail",
            details={"import_error": str(exc)},
        ) from exc


SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
)


def _load_credentials(credentials_path: str | None):
    _require_deps()
    from google.oauth2.credentials import Credentials

    if not credentials_path:
        raise AuthError(
            "Set GMAIL_CREDENTIALS_PATH to a Gmail OAuth user token JSON file.",
            provider="gmail",
        )
    path = Path(credentials_path)
    if not path.is_file():
        raise AuthError(f"Gmail credentials file not found: {path}", provider="gmail")
    return Credentials.from_authorized_user_file(str(path), SCOPES)


def build_gmail_service(credentials_path: str | None):
    _require_deps()
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = _load_credentials(credentials_path)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def live_read_thread(service: Any, thread_id: str) -> dict[str, Any]:
    tid = thread_id.strip()
    if not tid or tid.startswith("session:"):
        raise PermanentProviderError(
            "Live read requires a real Gmail thread id, not a virtual session hint.",
            provider="gmail",
            details={"thread_id": thread_id},
        )
    t = service.users().threads().get(userId="me", id=tid, format="metadata").execute()
    return {
        "thread_id": t.get("id"),
        "snippet": t.get("snippet"),
        "message_count": len(t.get("messages") or []),
        "messages": t.get("messages") or [],
    }


def live_create_draft(
    service: Any,
    *,
    thread_id: str | None,
    subject: str,
    body: str,
    sender: str | None,
) -> str:
    msg = MIMEText(body, "plain", "utf-8")
    msg["subject"] = subject
    if sender:
        msg["from"] = sender
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    draft_body: dict[str, Any] = {"message": {"raw": raw}}
    if thread_id and not thread_id.startswith("session:"):
        draft_body["message"]["threadId"] = thread_id
    draft = service.users().drafts().create(userId="me", body=draft_body).execute()
    return str(draft["id"])


def live_send_draft(service: Any, draft_id: str) -> str:
    if draft_id.startswith("draft:stub:"):
        raise PermanentProviderError(
            "Cannot send stub draft id in live mode.",
            provider="gmail",
            details={"draft_id": draft_id},
        )
    sent = service.users().drafts().send(userId="me", body={"id": draft_id}).execute()
    mid = sent.get("id")
    if not mid:
        raise PermanentProviderError("Gmail send returned no message id", provider="gmail", details=sent)
    return str(mid)
