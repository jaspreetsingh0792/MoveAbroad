from __future__ import annotations

import html

from opportunities_abroad.models import Job
from opportunities_abroad.sources.ats import AtsBoardSource, parse_datetime
from opportunities_abroad.textutil import strip_html

GREENHOUSE_BOARD = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


class GreenhouseSource(AtsBoardSource):
    """Greenhouse job boards. Public, documented, no key required.

    Board slugs are the last path segment of a company's public board URL.
    """

    name = "greenhouse"

    def board_url(self, board: str) -> str:
        return GREENHOUSE_BOARD.format(board=board)

    def to_job(self, item: dict, board: str) -> Job | None:
        job_id = item.get("id")
        title = (item.get("title") or "").strip()
        url = (item.get("absolute_url") or "").strip()
        if job_id is None or not title or not url:
            return None
        location = ((item.get("location") or {}).get("name") or "").strip()
        # `content` is HTML that Greenhouse returns HTML-escaped, so unescape first.
        description = strip_html(html.unescape(item.get("content") or ""))
        posted = parse_datetime(item.get("first_published") or item.get("updated_at"))
        departments = [
            str(d.get("name")) for d in (item.get("departments") or []) if d.get("name")
        ]
        company = (item.get("company_name") or "").strip() or board
        return Job(
            source="greenhouse",
            source_id=f"{board}:{job_id}",
            title=title,
            company=company,
            url=url,
            location=location,
            description=description,
            tags=departments,
            remote="remote" in location.lower(),
            posted_at=posted,
            extra={"board": board},
        )
