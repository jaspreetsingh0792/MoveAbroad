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
