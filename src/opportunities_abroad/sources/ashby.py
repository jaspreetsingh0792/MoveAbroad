from __future__ import annotations

from opportunities_abroad.models import Job
from opportunities_abroad.sources.ats import AtsBoardSource, parse_datetime
from opportunities_abroad.textutil import strip_html

ASHBY_BOARD = "https://api.ashbyhq.com/posting-api/job-board/{board}"


class AshbySource(AtsBoardSource):
    """Ashby job boards. Public posting API, no key required.

    Board slugs are the organisation segment of a jobs.ashbyhq.com URL.
    """

    name = "ashby"

    def board_url(self, board: str) -> str:
        return ASHBY_BOARD.format(board=board)

    def to_job(self, item: dict, board: str) -> Job | None:
        job_id = item.get("id")
        title = (item.get("title") or "").strip()
        url = (item.get("jobUrl") or item.get("applyUrl") or "").strip()
        if not job_id or not title or not url:
            return None
        location = (item.get("location") or "").strip()
        description = (item.get("descriptionPlain") or "").strip()
        if not description:
            description = strip_html(item.get("descriptionHtml") or "")
        remote = item.get("isRemote")
        if remote is None:
            remote = "remote" in location.lower()
        tags = [str(value) for key in ("department", "team") if (value := item.get(key))]
        compensation = item.get("compensation") or {}
        salary = (compensation.get("compensationTierSummary") or "").strip() or None
        return Job(
            source="ashby",
            source_id=f"{board}:{job_id}",
            title=title,
            company=(item.get("organizationName") or "").strip() or board,
            url=url,
            location=location,
            description=description,
            tags=tags,
            remote=bool(remote),
            posted_at=parse_datetime(item.get("publishedAt") or item.get("updatedAt")),
            salary=salary,
            job_type=(item.get("employmentType") or None),
            extra={"board": board},
        )
