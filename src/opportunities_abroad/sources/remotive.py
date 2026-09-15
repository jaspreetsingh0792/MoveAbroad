from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.textutil import strip_html

logger = logging.getLogger(__name__)

REMOTIVE_URL = "https://remotive.com/api/remote-jobs"

# Fetch the full feed and filter locally. Remotive's query params are documented
# but have been observed to be ignored by Cloudflare caching of the path only.
SOFTWARE_CATEGORIES = {"software-dev", "software development"}


class RemotiveSource(JobSource):
    name = "remotive"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, prefs: Prefs) -> list[Job]:
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        try:
            response = client.get(REMOTIVE_URL)
            response.raise_for_status()
            payload = response.json()
        except Exception:
            logger.exception("Remotive fetch failed")
            return []
        finally:
            if owns_client:
                client.close()

        logger.info(
            "Remotive job-count=%s total-job-count=%s",
            payload.get("job-count"),
            payload.get("total-job-count"),
        )
        jobs: list[Job] = []
        for item in payload.get("jobs") or []:
            job = self._to_job(item)
            if job is None:
                continue
            category = str(item.get("category") or "").lower()
            tags = [t.lower() for t in (item.get("tags") or [])]
            if SOFTWARE_CATEGORIES and category.replace(" ", "-") not in {
                "software-dev"
            } and "software" not in category:
                # Keep non-software roles only if they still look technical.
                blob = f"{job.title} {' '.join(tags)}".lower()
                if not any(
                    token in blob
                    for token in ("engineer", "developer", "software", "devops", "python", "data")
                ):
                    continue
            jobs.append(job)
        logger.info("Remotive returned %s usable jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_job(item: dict) -> Job | None:
        source_id = item.get("id")
        url = (item.get("url") or "").strip()
        title = (item.get("title") or "").strip()
        if source_id is None or not url or not title:
            return None
        location = (item.get("candidate_required_location") or item.get("job_type") or "").strip()
        posted = _parse_dt(item.get("publication_date"))
        return Job(
            source="remotive",
            source_id=str(source_id),
            title=title,
            company=(item.get("company_name") or "").strip(),
            url=url,
            location=location,
            description=strip_html(item.get("description") or ""),
            tags=[str(t) for t in (item.get("tags") or [])],
            remote=True,
            posted_at=posted,
            salary=(item.get("salary") or None),
            job_type=item.get("job_type"),
            extra={"category": item.get("category")},
        )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None
