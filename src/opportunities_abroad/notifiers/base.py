from __future__ import annotations

from abc import ABC, abstractmethod

from opportunities_abroad.models import RunResult


class Notifier(ABC):
    """Delivery channel for a matching-job digest."""

    name: str

    @abstractmethod
    def send(self, result: RunResult) -> None:
        """Deliver the digest. Implementations should be a no-op or raise if stubbed."""
