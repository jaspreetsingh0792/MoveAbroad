from __future__ import annotations

from abc import ABC, abstractmethod

from opportunities_abroad.models import Job, SourceHealth
from opportunities_abroad.prefs import Prefs


class JobSource(ABC):
    """Pluggable job source. Implementations must be polite and key-free unless documented."""

    name: str

    @abstractmethod
    def fetch(self, prefs: Prefs) -> list[Job]:
        """Return currently advertised jobs. May return an empty list on failure."""

    def health(self, fetched: int) -> SourceHealth:
        """Report what this source did on the run that just finished.

        Sources that swallow partial failures internally should override this
        so the digest can tell "nothing matched" apart from "nothing worked".
        """
        return SourceHealth(name=self.name, fetched=fetched)
