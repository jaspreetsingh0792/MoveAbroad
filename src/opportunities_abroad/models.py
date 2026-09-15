from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class Job:
    """Normalized job posting from any source."""

    source: str
    source_id: str
    title: str
    company: str
    url: str
    location: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    remote: bool | None = None
    posted_at: datetime | None = None
    salary: str | None = None
    job_type: str | None = None
    visa_sponsorship: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    @property
    def searchable_text(self) -> str:
        parts = [
            self.title,
            self.company,
            self.location,
            self.description,
            " ".join(self.tags),
            self.salary or "",
            self.job_type or "",
        ]
        return " ".join(p for p in parts if p)


@dataclass(slots=True)
class Match:
    job: Job
    score: int
    reasons: list[str] = field(default_factory=list)
    sponsorship: str | None = None
    sponsorship_reason: str | None = None


@dataclass(slots=True)
class SourceHealth:
    """What one source did on this run.

    A source that fails is indistinguishable from one that legitimately had
    nothing, unless the run says so out loud.
    """

    name: str
    fetched: int = 0
    failed: bool = False
    error: str = ""
    boards_ok: list[str] = field(default_factory=list)
    boards_failed: list[str] = field(default_factory=list)

    @property
    def healthy(self) -> bool:
        return not self.failed and not self.boards_failed

    def summary(self) -> str:
        if self.failed:
            return f"{self.name}: FAILED ({self.error or 'unknown error'})"
        total_boards = len(self.boards_ok) + len(self.boards_failed)
        if total_boards:
            detail = f"{len(self.boards_ok)}/{total_boards} boards OK"
            if self.boards_failed:
                detail += f" — failed: {', '.join(sorted(self.boards_failed))}"
            return f"{self.name}: {self.fetched} fetched, {detail}"
        return f"{self.name}: {self.fetched} fetched"


@dataclass(slots=True)
class RunResult:
    """Outcome of one pipeline run: the digest plus why everything else was dropped."""

    matches: list[Match] = field(default_factory=list)
    fetched: int = 0
    matched: int = 0
    already_seen: int = 0
    too_old: int = 0
    rejected_location: int = 0
    rejected_title: int = 0
    rejected_visa: int = 0
    sources: list[SourceHealth] = field(default_factory=list)

    @property
    def unhealthy_sources(self) -> list[SourceHealth]:
        return [s for s in self.sources if not s.healthy]

    @property
    def new_count(self) -> int:
        return len(self.matches)

    @property
    def rejected(self) -> int:
        return self.rejected_location + self.rejected_title + self.rejected_visa
