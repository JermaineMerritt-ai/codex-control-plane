from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_sqlite_db(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings
    from db.session import get_engine, init_db

    get_settings.cache_clear()
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.delenv("OPERATOR_API_KEY", raising=False)
    monkeypatch.delenv("GMAIL_MODE", raising=False)
    monkeypatch.delenv("GMAIL_CREDENTIALS_PATH", raising=False)
    get_settings.cache_clear()
    init_db(get_engine())
    yield
    get_settings.cache_clear()
