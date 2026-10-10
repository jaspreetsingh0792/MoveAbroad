from __future__ import annotations

import logging
import time

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.ats import parse_datetime
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.sources.jobicy import format_salary
from opportunities_abroad.sources.payload import records
from opportunities_abroad.textutil import strip_html

logger = logging.getLogger(__name__)

HIMALAYAS_URL = "https://himalayas.app/jobs/api"
# The public API serves at most 20 jobs per request.
PAGE_SIZE = 20
PAGE_DELAY_SECONDS = 1.0


class HimalayasSource(JobSource):
    """Himalayas remote jobs. No key required; credit and link back to Himalayas.

    Every job lists ``locationRestrictions``, the countries its hires may live
    in (empty means anywhere), which is exactly what the relocation check
    needs. Field names have varied between API versions, so the mapper accepts
    the known spellings, and a page whose records all fail to map is reported
    as a failure rather than as an empty board.
    """

    name = "himalayas"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, prefs: Prefs) -> list[Job]:
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        jobs: list[Job] = []
        raw = 0
        try:
            offset = 0
            cursor: str | None = None
            for page in range(max(1, prefs.himalayas_max_pages)):
                if page:
                    time.sleep(PAGE_DELAY_SECONDS)
                params: dict[str, str | int] = {"limit": PAGE_SIZE}
                if cursor:
                    params["cursor"] = cursor
                else:
                    params["offset"] = offset
                response = client.get(HIMALAYAS_URL, params=params)
                response.raise_for_status()
                payload = response.json()
                items = records(payload, "jobs")
                raw += len(items)
                for item in items:
                    try:
                        job = self._to_job(item)
                    except Exception:
                        logger.exception("Himalayas could not map a record")
                        continue
                    if job is not None:
                        jobs.append(job)
                if len(items) < PAGE_SIZE:
                    break
                next_cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
                cursor = next_cursor if isinstance(next_cursor, str) and next_cursor else None
                offset += len(items)
        finally:
            if owns_client:
                client.close()
        if raw and not jobs:
            raise ValueError(f"Himalayas returned {raw} records but none could be mapped")
        logger.info("Himalayas returned %s jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_job(item: dict) -> Job | None:
        title = str(item.get("title") or "").strip()
        url = str(
            item.get("applicationLink") or item.get("applicationUrl") or item.get("url") or ""
        ).strip()
        source_id = item.get("guid") or item.get("id") or item.get("slug") or url
        if not title or not url or not source_id:
            return None
        regions = _names(item.get("locationRestrictions"))
        seniority = _names(item.get("seniority"))
        categories = _names(item.get("categories"))
        return Job(
            source="himalayas",
            source_id=str(source_id),
            title=title,
            company=str(item.get("companyName") or "").strip(),
            url=url,
            location=", ".join(regions) if regions else "Worldwide",
            description=strip_html(str(item.get("description") or item.get("excerpt") or "")),
            tags=categories,
            remote=True,
            posted_at=parse_datetime(item.get("pubDate") or item.get("publishedAt")),
            salary=format_salary(
                item.get("minSalary"),
                item.get("maxSalary"),
                item.get("currency"),
                item.get("salaryPeriod"),
            ),
            job_type=str(item.get("employmentType") or "").strip() or None,
            extra={
                "eligible_regions": regions or ["Worldwide"],
                **({"level": ", ".join(seniority)} if seniority else {}),
            },
        )


def _names(value: object) -> list[str]:
    """Strings, or the ``name`` of objects, from a list of either."""
    if not isinstance(value, list):
        return []
    names = []
    for entry in value:
        if isinstance(entry, dict):
            entry = entry.get("name")
        if isinstance(entry, str) and entry.strip():
            names.append(entry.strip())
    return names
