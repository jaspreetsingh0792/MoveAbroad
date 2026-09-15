from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.sources.payload import records
from opportunities_abroad.textutil import strip_html

logger = logging.getLogger(__name__)

ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(JobSource):
    """Europe-focused public job board API. No key required.

    Be conservative with pagination: the public API is rate-limited.
    Documented `remote=true` filtering has been unreliable; we filter locally.
    """

    name = "arbeitnow"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, prefs: Prefs) -> list[Job]:
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        jobs: list[Job] = []
        try:
            max_pages = max(1, prefs.arbeitnow_max_pages)
            for page in range(1, max_pages + 1):
                params: dict[str, str | int] = {"page": page}
                if prefs.arbeitnow_visa_sponsorship is True:
                    params["visa_sponsorship"] = "true"
                elif prefs.arbeitnow_visa_sponsorship is False:
                    params["visa_sponsorship"] = "false"
                try:
                    response = client.get(ARBEITNOW_URL, params=params)
                    response.raise_for_status()
                    payload = response.json()
                except Exception:
                    logger.exception("Arbeitnow fetch failed on page %s", page)
                    break
                items = records(payload, "data")
                if not items:
                    break
                for item in items:
                    try:
                        job = self._to_job(item)
                    except Exception:
                        logger.exception("Arbeitnow could not map a record")
                        continue
                    if job is not None:
                        jobs.append(job)
                links = payload.get("links") if isinstance(payload, dict) else None
                next_link = (links or {}).get("next") if isinstance(links, dict) else None
                if not next_link:
                    break
                if page < max_pages:
                    time.sleep(1.0)
        finally:
            if owns_client:
                client.close()
        logger.info("Arbeitnow returned %s jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_job(item: dict) -> Job | None:
        slug = item.get("slug") or item.get("url")
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if not slug or not url or not title:
            return None
        remote = _as_bool(item.get("remote"))
        visa_sponsorship = _as_bool(item.get("visa_sponsorship"))
        posted = _parse_created(item.get("created_at") or item.get("createdAt"))
        tags = [str(t) for t in (item.get("tags") or [])]
        job_types = item.get("job_types") or item.get("job_type") or []
        if isinstance(job_types, str):
            job_type = job_types
        elif job_types:
            job_type = ", ".join(str(t) for t in job_types)
        else:
            job_type = None
        return Job(
            source="arbeitnow",
            source_id=str(slug),
            title=title,
            company=(item.get("company_name") or "").strip(),
            url=url,
            location=(item.get("location") or "").strip(),
            description=strip_html(item.get("description") or ""),
            tags=tags,
            remote=remote,
            posted_at=posted,
            job_type=job_type,
            visa_sponsorship=visa_sponsorship,
        )


def _as_bool(value: object) -> bool | None:
    """Arbeitnow sends these flags as booleans or as strings depending on the field."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "remote"}
    return bool(value)


def _parse_created(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(int(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    text = str(value)
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None
