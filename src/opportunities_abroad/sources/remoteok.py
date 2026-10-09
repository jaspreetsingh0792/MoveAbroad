from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.sources.payload import records
from opportunities_abroad.textutil import strip_html

logger = logging.getLogger(__name__)

REMOTEOK_URL = "https://remoteok.com/api"


class RemoteOKSource(JobSource):
    """Remote OK public feed. No key required.

    Listed under Jobs in public-apis/public-apis. The feed is a JSON array whose
    first element is a legal notice rather than a job; their terms ask that
    Remote OK is credited and linked, which the digest does by naming the
    source and linking each posting back to remoteok.com.

    Transport errors are raised, not swallowed, so the run records the source
    as failed instead of quietly empty.
    """

    name = "remoteok"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, prefs: Prefs) -> list[Job]:
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        try:
            response = client.get(REMOTEOK_URL)
            response.raise_for_status()
            payload = response.json()
        finally:
            if owns_client:
                client.close()

        jobs: list[Job] = []
        for item in records(payload, "jobs"):
            try:
                job = self._to_job(item)
            except Exception:
                logger.exception("Remote OK could not map a record")
                continue
            if job is not None:
                jobs.append(job)
        logger.info("Remote OK returned %s jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_job(item: dict) -> Job | None:
        # The legal-notice element has no id/position and is dropped here.
        source_id = item.get("id")
        title = str(item.get("position") or "").strip()
        url = str(item.get("url") or item.get("apply_url") or "").strip()
        if source_id in (None, "") or not title or not url:
            return None
        tags = item.get("tags")
        return Job(
            source="remoteok",
            source_id=str(source_id),
            title=title,
            company=str(item.get("company") or "").strip(),
            url=url,
            location=str(item.get("location") or "").strip() or "Remote",
            description=strip_html(str(item.get("description") or "")),
            tags=[str(t) for t in tags] if isinstance(tags, list) else [],
            remote=True,
            posted_at=_parse_posted(item.get("date"), item.get("epoch")),
            salary=_salary(item.get("salary_min"), item.get("salary_max")),
        )


def _parse_posted(date: object, epoch: object) -> datetime | None:
    if isinstance(date, str) and date:
        text = date[:-1] + "+00:00" if date.endswith("Z") else date
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            parsed = None
        if parsed is not None:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
    if isinstance(epoch, (int, float)) and not isinstance(epoch, bool):
        try:
            return datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _salary(low: object, high: object) -> str | None:
    def amount(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
        return int(value)

    lo, hi = amount(low), amount(high)
    if lo and hi:
        return f"${lo:,}–${hi:,}"
    if lo or hi:
        return f"${lo or hi:,}"
    return None
