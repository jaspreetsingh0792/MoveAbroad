from __future__ import annotations

from abc import ABC, abstractmethod

from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs


class JobSource(ABC):
    """Pluggable job source. Implementations must be polite and key-free unless documented."""

    name: str

    @abstractmethod
    def fetch(self, prefs: Prefs) -> list[Job]:
        """Return currently advertised jobs. May return an empty list on failure."""
