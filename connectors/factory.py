"""Construct connectors from application settings (single runtime source of truth)."""

from __future__ import annotations

from app.config import get_settings
from connectors.gmail import GmailConfig, GmailConnector


def get_gmail_connector() -> GmailConnector:
    """
    Build the process-wide Gmail connector from env/config.

    Uses `GMAIL_MODE` (stub|live) and `GMAIL_CREDENTIALS_PATH` for live OAuth token JSON.
    Live mode never falls back to stub: invalid live config raises when settings load.

    Workers and services should use this instead of ad-hoc GmailConnector() construction.
    """
    s = get_settings()
    return GmailConnector(
        GmailConfig(
            mode=s.gmail_mode,
            credentials_path=s.gmail_credentials_path,
        )
    )
