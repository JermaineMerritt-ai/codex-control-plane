"""Central application settings (env-backed)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gmail_mode: Literal["stub", "live"] = Field(default="stub")
    gmail_credentials_path: str | None = Field(default=None)
    operator_api_key: str | None = Field(
        default=None,
        description="If set, clients must send X-Operator-Key for operator routes.",
    )

    @model_validator(mode="after")
    def live_gmail_requires_credentials_file(self) -> Settings:
        """
        Never silently run "live" without a real token file: misconfiguration fails at startup
        (first `get_settings()`), not as stub-like behavior at send time.
        """
        if self.gmail_mode != "live":
            return self
        path_raw = (self.gmail_credentials_path or "").strip()
        if not path_raw:
            raise ValueError(
                "GMAIL_MODE=live requires GMAIL_CREDENTIALS_PATH to point to an OAuth token JSON file"
            )
        path = Path(path_raw).expanduser()
        if not path.is_file():
            raise ValueError(
                f"GMAIL_MODE=live requires an existing file at GMAIL_CREDENTIALS_PATH (not found: {path})"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
