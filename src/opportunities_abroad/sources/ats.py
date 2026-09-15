from __future__ import annotations

import logging
import time
from abc import abstractmethod
from datetime import datetime, timezone

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job, SourceHealth
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource

logger = logging.getLogger(__name__)

# One request per board, so space them out rather than bursting through a long list.
REQUEST_DELAY_SECONDS = 0.3


class AtsBoardSource(JobSource):
    """Base for applicant-tracking systems that publish one JSON board per company.

    Boards come from ``prefs.ats_boards[name]``. A board that errors or returns an
    unexpected shape is skipped so one bad slug cannot lose the whole run.
    """

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client
        self._boards_ok: list[str] = []
        self._boards_failed: list[str] = []

    def health(self, fetched: int) -> SourceHealth:
        return SourceHealth(
            name=self.name,
            fetched=fetched,
            boards_ok=list(self._boards_ok),
            boards_failed=list(self._boards_failed),
        )

    @abstractmethod
    def board_url(self, board: str) -> str:
        """Public JSON endpoint for one board slug."""

    @abstractmethod
    def to_job(self, item: dict, board: str) -> Job | None:
        """Map one posting onto a Job, or None when required fields are missing."""

    @staticmethod
    def extract_items(payload: object) -> list[dict]:
        """Boards return either a bare list or an object with a ``jobs`` list."""
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict):
            items = payload.get("jobs") or []
        else:
            items = []
        return [item for item in items if isinstance(item, dict)]

    def fetch(self, prefs: Prefs) -> list[Job]:
        boards = prefs.boards_for(self.name)
        if not boards:
            logger.info("%s skipped: no boards configured in ats_boards", self.name)
            return []
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        jobs: list[Job] = []
        self._boards_ok = []
        self._boards_failed = []
        try:
            for index, board in enumerate(boards):
                if index:
                    time.sleep(REQUEST_DELAY_SECONDS)
                jobs.extend(self._fetch_board(client, board))
        finally:
            if owns_client:
                client.close()
        logger.info("%s returned %s jobs from %s board(s)", self.name, len(jobs), len(boards))
        return jobs

    def _fetch_board(self, client: httpx.Client, board: str) -> list[Job]:
        try:
            response = client.get(self.board_url(board))
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception("%s fetch failed for board %s", self.name, board)
            self._boards_failed.append(board)
            return []
        jobs = []
        for item in self.extract_items(payload):
            job = self.to_job(item, board)
            if job is not None:
                jobs.append(job)
        self._boards_ok.append(board)
        logger.debug("%s/%s: %s jobs", self.name, board, len(jobs))
        return jobs


def parse_datetime(value: object) -> datetime | None:
    """Parse the ISO-8601 strings and epoch milliseconds these boards mix freely."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        seconds = float(value)
        # Lever reports epoch milliseconds; anything this large cannot be seconds.
        if abs(seconds) > 1e11:
            seconds /= 1000.0
        try:
            return datetime.fromtimestamp(seconds, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
