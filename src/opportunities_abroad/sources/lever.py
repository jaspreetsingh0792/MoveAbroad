from __future__ import annotations

from opportunities_abroad.models import Job
from opportunities_abroad.sources.ats import AtsBoardSource, parse_datetime
from opportunities_abroad.textutil import strip_html

LEVER_POSTINGS = "https://api.lever.co/v0/postings/{board}?mode=json"


class LeverSource(AtsBoardSource):
    """Lever job boards. Public, documented, no key required.

    Board slugs are the company segment of a jobs.lever.co URL.
    """

    name = "lever"

    def board_url(self, board: str) -> str:
        return LEVER_POSTINGS.format(board=board)

    def to_job(self, item: dict, board: str) -> Job | None:
        job_id = item.get("id")
        title = (item.get("text") or "").strip()
        url = (item.get("hostedUrl") or item.get("applyUrl") or "").strip()
        if not job_id or not title or not url:
            return None
        categories = item.get("categories") or {}
        location = (categories.get("location") or "").strip()
        workplace = str(item.get("workplaceType") or "").lower()
        description = (item.get("descriptionPlain") or "").strip()
        if not description:
            description = strip_html(item.get("description") or "")
        tags = [
            str(value)
            for key in ("team", "department", "commitment")
            if (value := categories.get(key))
        ]
        return Job(
            source="lever",
            source_id=f"{board}:{job_id}",
            title=title,
            company=board,
            url=url,
            location=location,
            description=description,
            tags=tags,
            remote=workplace == "remote" or "remote" in location.lower(),
            posted_at=parse_datetime(item.get("createdAt")),
            salary=_salary(item),
            job_type=(categories.get("commitment") or None),
            extra={"board": board, "workplace_type": workplace or None},
        )


def _salary(item: dict) -> str | None:
    described = (item.get("salaryDescription") or "").strip()
    if described:
        return described
    salary_range = item.get("salaryRange") or {}
    low = salary_range.get("min")
    high = salary_range.get("max")
    if low is None and high is None:
        return None
    currency = (salary_range.get("currency") or "").strip()
    amounts = f"{low if low is not None else '?'}–{high if high is not None else '?'}"
    return f"{currency} {amounts}".strip()
