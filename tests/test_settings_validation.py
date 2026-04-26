from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import get_settings


def test_live_mode_requires_credentials_path(monkeypatch):
    monkeypatch.setenv("GMAIL_MODE", "live")
    monkeypatch.delenv("GMAIL_CREDENTIALS_PATH", raising=False)
    get_settings.cache_clear()
    with pytest.raises(ValidationError) as exc:
        get_settings()
    assert "GMAIL_CREDENTIALS_PATH" in str(exc.value)


def test_live_mode_requires_existing_file(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("GMAIL_MODE", "live")
    missing = tmp_path / "missing-token.json"
    monkeypatch.setenv("GMAIL_CREDENTIALS_PATH", str(missing))
    get_settings.cache_clear()
    with pytest.raises(ValidationError) as exc:
        get_settings()
    assert "not found" in str(exc.value).lower() or "existing" in str(exc.value).lower()
