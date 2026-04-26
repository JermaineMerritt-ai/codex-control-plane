import pytest

from connectors.errors import AuthError, PermanentProviderError
from connectors.gmail import GmailConfig, GmailConnector


def test_stub_read_thread_returns_envelope():
    g = GmailConnector(GmailConfig(mode="stub"))
    data = g.read_thread("abc123")
    assert data["thread_id"] == "abc123"
    assert data["snippet"] == "stub_thread"


def test_stub_create_draft_returns_synthetic_id():
    g = GmailConnector(GmailConfig(mode="stub"))
    did = g.create_draft(thread_id="t1", subject="S", body="B")
    assert did.startswith("draft:stub:")


def test_send_message_gated_without_approval():
    g = GmailConnector(GmailConfig(mode="stub"))
    with pytest.raises(PermanentProviderError) as exc:
        g.send_message("draft:stub:x", approved=False)
    assert "gated" in str(exc.value).lower()


def test_send_message_stub_succeeds_when_approved():
    g = GmailConnector(GmailConfig(mode="stub"))
    mid = g.send_message("draft:stub:x", approved=True)
    assert mid.startswith("msg:stub:")


def test_send_approved_draft_delegates_to_gated_send():
    g = GmailConnector(GmailConfig(mode="stub"))
    mid = g.send_approved_draft("draft:stub:y")
    assert mid.startswith("msg:stub:")


def test_live_mode_not_implemented_for_read():
    g = GmailConnector(GmailConfig(mode="live"))
    with pytest.raises(AuthError):
        g.read_thread("t")


def test_live_rejects_virtual_thread_hint(monkeypatch):
    """Without real OAuth token file, live build raises AuthError first."""
    g = GmailConnector(GmailConfig(mode="live", credentials_path=None))
    with pytest.raises(AuthError):
        g.read_thread("session:not-real")


def test_live_read_uses_api_when_service_mocked(monkeypatch):
    class _Get:
        def execute(self):
            return {"id": "real-t", "snippet": "x", "messages": [{"id": "m1"}]}

    class _Threads:
        def get(self, **kwargs):
            return _Get()

    class _Users:
        def threads(self):
            return _Threads()

    class _Svc:
        def users(self):
            return _Users()

    monkeypatch.setattr(
        "connectors.gmail.gmail_live.build_gmail_service",
        lambda _path: _Svc(),
    )
    g = GmailConnector(GmailConfig(mode="live", credentials_path="/dev/null"))
    out = g.read_thread("real-t")
    assert out["thread_id"] == "real-t"
    assert out["message_count"] == 1
