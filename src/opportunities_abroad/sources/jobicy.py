from __future__ import annotations

import logging
import re

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.ats import parse_datetime
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.sources.payload import records
from opportunities_abroad.textutil import strip_html

logger = logging.getLogger(__name__)

JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"
PAGE_SIZE = 100


class JobicySource(JobSource):
    """Jobicy remote jobs. No key required.

    Documented at https://github.com/Jobicy/remote-jobs-api. Each job carries
    ``jobGeo``, the region its hires must live in, which the relocation check
    reads as the eligible regions. Fair use asks for at most one sync pass an
    hour and for the Jobicy URL to be kept, which the digest links to.
    """

    name = "jobicy"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client

    def fetch(self, prefs: Prefs) -> list[Job]:
        client = self._client or make_client(prefs.http_timeout_seconds)
        owns_client = self._client is None
        jobs: list[Job] = []
        raw = 0
        try:
            cursor: str | None = None
            for _ in range(max(1, prefs.jobicy_max_pages)):
                params: dict[str, str | int] = {"count": PAGE_SIZE}
                if cursor:
                    params["cursor"] = cursor
                response = client.get(JOBICY_URL, params=params)
                response.raise_for_status()
                payload = response.json()
                items = records(payload, "jobs")
                raw += len(items)
                for item in items:
                    try:
                        job = self._to_job(item)
                    except Exception:
                        logger.exception("Jobicy could not map a record")
                        continue
                    if job is not None:
                        jobs.append(job)
                next_cursor = payload.get("nextCursor") if isinstance(payload, dict) else None
                if not isinstance(next_cursor, str) or not next_cursor:
                    break
                cursor = next_cursor
        finally:
            if owns_client:
                client.close()
        if raw and not jobs:
            # Records arrived but none could be read: the schema moved.
            raise ValueError(f"Jobicy returned {raw} records but none could be mapped")
        logger.info("Jobicy returned %s jobs", len(jobs))
        return jobs

    @staticmethod
    def _to_job(item: dict) -> Job | None:
        source_id = item.get("id")
        title = str(item.get("jobTitle") or item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if source_id in (None, "") or not title or not url:
            return None
        geo = str(item.get("jobGeo") or "").strip()
        regions = [part.strip() for part in re.split(r"[,/;|&]", geo) if part.strip()]
        level = str(item.get("jobLevel") or "").strip()
        job_types = item.get("jobType")
        industries = item.get("jobIndustry")
        return Job(
            source="jobicy",
            source_id=str(source_id),
            title=title,
            company=str(item.get("companyName") or "").strip(),
            url=url,
            location=geo or "Anywhere",
            description=strip_html(
                str(item.get("jobDescription") or item.get("jobExcerpt") or "")
            ),
            tags=[str(t) for t in industries] if isinstance(industries, list) else [],
            remote=True,
            posted_at=parse_datetime(item.get("pubDate")),
            salary=format_salary(
                item.get("salaryMin", item.get("annualSalaryMin")),
                item.get("salaryMax", item.get("annualSalaryMax")),
                item.get("salaryCurrency"),
                item.get("salaryPeriod"),
            ),
            job_type=", ".join(str(t) for t in job_types) if isinstance(job_types, list) else None,
            extra={
                "eligible_regions": regions or ["Anywhere"],
                **({"level": level} if level and level.lower() != "any" else {}),
            },
        )


def format_salary(
    low: object, high: object, currency: object = None, period: object = None
) -> str | None:
    """"USD 90,000–125,000 / year" from whichever bounds are real numbers."""

    def amount(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            return None
        return int(value)

    lo, hi = amount(low), amount(high)
    if not lo and not hi:
        return None
    figure = f"{lo:,}–{hi:,}" if lo and hi and lo != hi else f"{lo or hi:,}"
    code = str(currency).strip().upper() if isinstance(currency, str) and currency.strip() else ""
    text = f"{code} {figure}".strip()
    unit = {"yearly": "year", "annual": "year", "monthly": "month", "hourly": "hour"}.get(
        str(period or "").strip().lower()
    )
    return f"{text} / {unit}" if unit else text
