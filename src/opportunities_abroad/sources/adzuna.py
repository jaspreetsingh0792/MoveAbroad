from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.textutil import strip_html

logger = logging.getLogger(__name__)

ADZUNA_SEARCH = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"


class AdzunaSource(JobSource):
    """Optional Adzuna search. Skips live calls unless both env keys are set."""

    name = "adzuna"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def credentials(self) -> tuple[str, str] | None:
        app_id = (os.environ.get("ADZUNA_APP_ID") or "").strip()
        app_key = (os.environ.get("ADZUNA_API_KEY") or "").strip()
        if not app_id or not app_key:
            return None
        return app_id, app_key

    def fetch(self, prefs: Prefs) -> list[Job]:
        creds = self.credentials()
        if creds is None:
            logger.info("Adzuna skipped: ADZUNA_APP_ID / ADZUNA_API_KEY not set")
            return []
        app_id, app_key = creds
        countries = prefs.adzuna_countries or ["nl"]
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        jobs: list[Job] = []
        try:
            for country in countries:
                for page in range(1, max(1, prefs.adzuna_max_pages) + 1):
                    params = {
                        "app_id": app_id,
                        "app_key": app_key,
                        "results_per_page": prefs.adzuna_results_per_page,
                        "what": prefs.adzuna_what,
                        "content-type": "application/json",
                    }
                    url = ADZUNA_SEARCH.format(country=country, page=page)
                    try:
                        response = client.get(url, params=params)
                        response.raise_for_status()
                        payload = response.json()
                    except Exception:
                        logger.exception("Adzuna fetch failed for %s page %s", country, page)
                        break
                    for item in payload.get("results") or []:
                        job = self._to_job(item, country)
                        if job is not None:
                            jobs.append(job)
        finally:
            if owns_client:
                client.close()
        logger.info("Adzuna returned %s jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_job(item: dict, country: str) -> Job | None:
        source_id = item.get("id")
        url = (item.get("redirect_url") or item.get("adref") or "").strip()
        title = (item.get("title") or "").strip()
        if source_id is None or not url or not title:
            return None
        loc_obj = item.get("location") or {}
        display = loc_obj.get("display_name") or ""
        area = ", ".join(str(a) for a in (loc_obj.get("area") or []) if a)
        location = display or area or country.upper()
        company_obj = item.get("company") or {}
        company = company_obj.get("display_name") or ""
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        salary = None
        if salary_min or salary_max:
            salary = f"{salary_min or '?'}–{salary_max or '?'}"
        posted = _parse_dt(item.get("created"))
        description = strip_html(item.get("description") or "")
        remote = "remote" in f"{title} {location} {description}".lower()
        return Job(
            source="adzuna",
            source_id=str(source_id),
            title=title,
            company=company,
            url=url,
            location=location,
            description=description,
            tags=[country],
            remote=remote,
            posted_at=posted,
            salary=salary,
            extra={"country": country, "category": (item.get("category") or {}).get("label")},
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
