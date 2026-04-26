"""Base connector: auth, retries, and rate limits implemented per integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    """External API boundary; no business rules — those live in services/."""

    name: str

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Lightweight reachability / token validity probe."""

    @abstractmethod
    def refresh_credentials(self) -> None:
        """Refresh OAuth tokens or rotate secrets as needed."""
