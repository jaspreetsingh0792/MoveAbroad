from __future__ import annotations

import html
import logging
from datetime import datetime, timezone
from pathlib import Path

from opportunities_abroad.matcher.engine import country_for_location
from opportunities_abroad.models import Match, RunResult

logger = logging.getLogger(__name__)

FOOTER = "This digest is for personal use. It is not a job board."
INTRO = "Open the original posting — sources are credited."


def header_line(result: RunResult) -> str:
    """One-line account of the run, including what never made the digest."""
    return (
        f"{result.new_count} new · "
        f"{result.already_seen} already seen · "
        f"{result.too_old} too old · "
        f"{result.rejected} rejected (US-only / title / visa)"
    )


def source_lines(result: RunResult) -> list[str]:
    """Per-source accounting, so a dead source cannot hide behind a normal digest."""
    return [health.summary() for health in result.sources]


def health_warning(result: RunResult) -> str:
    broken = result.unhealthy_sources
    if not broken:
        return ""
    names = ", ".join(h.name for h in broken)
    return f"⚠ Source problems this run: {names}. Coverage may be incomplete."


def relative_age(posted_at: datetime | None, now: datetime | None = None) -> str:
    """Human-readable posting age, or an empty string when the date is unknown."""
    if posted_at is None:
        return ""
    reference = now or datetime.now(timezone.utc)
    posted = posted_at if posted_at.tzinfo else posted_at.replace(tzinfo=timezone.utc)
    seconds = (reference - posted).total_seconds()
    if seconds < 3600:
        return "just now"
    hours = int(seconds // 3600)
    if hours < 24:
        return f"{hours}h ago"
    return f"{hours // 24}d ago"


def is_remote(match: Match) -> bool:
    return match.job.remote is True or "remote" in match.reasons


def group_by_country(matches: list[Match]) -> list[tuple[str, list[Match]]]:
    """Bucket matches by country, best-scoring bucket first and "Other" last."""
    buckets: dict[str, list[Match]] = {}
    for match in matches:
        bucket = country_for_location(match.job.location, remote=is_remote(match))
        buckets.setdefault(bucket, []).append(match)
    for entries in buckets.values():
        entries.sort(key=lambda m: (-m.score, m.job.title.lower()))
    return sorted(
        buckets.items(),
        key=lambda item: (item[0] == "Other", -item[1][0].score, item[0]),
    )


def _facts(match: Match, now: datetime | None = None) -> list[str]:
    """The short metadata line shared by every rendering."""
    job = match.job
    parts = [job.location or "Location n/a", job.source]
    age = relative_age(job.posted_at, now)
    if age:
        parts.append(age)
    if job.salary:
        parts.append(job.salary)
    parts.append(f"score {match.score}")
    return parts


def _sponsorship_line(match: Match) -> str:
    if not match.sponsorship:
        return ""
    reason = (match.sponsorship_reason or "").strip()
    return f"sponsorship: {match.sponsorship}" + (f" — {reason}" if reason else "")


def _why(match: Match) -> str:
    return ", ".join(match.reasons) or "matched prefs"


def render_text(result: RunResult) -> str:
    lines = ["Opportunities Abroad — new matching jobs", header_line(result), ""]
    warning = health_warning(result)
    if warning:
        lines.extend([warning, ""])
    if not result.matches:
        lines.append("No new matching jobs this run.")
        lines.extend(["", *_sources_block(result), FOOTER])
        return "\n".join(lines)

    lines.append(INTRO)
    lines.append("")
    for country, entries in group_by_country(result.matches):
        lines.append(f"{country} ({len(entries)})")
        lines.append("-" * len(f"{country} ({len(entries)})"))
        for match in entries:
            job = match.job
            lines.append(f"- {job.title} @ {job.company or 'Unknown company'}")
            lines.append(f"  {' | '.join(_facts(match))}")
            sponsorship = _sponsorship_line(match)
            if sponsorship:
                lines.append(f"  {sponsorship}")
            lines.append(f"  why: {_why(match)}")
            lines.append(f"  {job.url}")
            lines.append("")
    lines.extend(_sources_block(result))
    lines.append(FOOTER)
    return "\n".join(lines)


def _sources_block(result: RunResult) -> list[str]:
    if not result.sources:
        return []
    return ["Sources", "-------", *source_lines(result), ""]


def render_console(result: RunResult, *, dry_run: bool) -> str:
    """Terminal digest. Same grouping as the email, without the boilerplate."""
    mode = "DRY-RUN matches (not emailed)" if dry_run else "Sent matches"
    lines = ["", f"{mode}: {header_line(result)}"]
    warning = health_warning(result)
    if warning:
        lines.append(warning)
    if not result.matches:
        lines.append("  (none)")
        lines.extend(_console_sources(result))
        return "\n".join(lines)
    for country, entries in group_by_country(result.matches):
        lines.append("")
        lines.append(f"{country} ({len(entries)})")
        for match in entries:
            job = match.job
            lines.append(f"- {job.title} @ {job.company or 'Unknown company'}")
            lines.append(f"    {'  '.join(_facts(match))}")
            sponsorship = _sponsorship_line(match)
            if sponsorship:
                lines.append(f"    {sponsorship}")
            lines.append(f"    why: {_why(match)}")
            lines.append(f"    {job.url}")
    lines.extend(_console_sources(result))
    return "\n".join(lines)


def _console_sources(result: RunResult) -> list[str]:
    if not result.sources:
        return []
    return ["", "Sources", *[f"  {line}" for line in source_lines(result)]]


def render_html(result: RunResult) -> str:
    sections = []
    for country, entries in group_by_country(result.matches):
        rows = []
        for match in entries:
            job = match.job
            sponsorship = _sponsorship_line(match)
            sponsorship_html = (
                f"<br><span style='color:#0b6b3a;font-size:12px;'>{html.escape(sponsorship)}</span>"
                if sponsorship
                else ""
            )
            rows.append(
                "<tr>"
                "<td style='padding:10px;border-bottom:1px solid #eee;'>"
                f"<a href='{html.escape(job.url, quote=True)}'>{html.escape(job.title)}</a><br>"
                f"<span style='color:#444;'>"
                f"{html.escape(job.company or 'Unknown company')}</span><br>"
                f"<span style='color:#666;font-size:12px;'>"
                f"{html.escape(' · '.join(_facts(match)))}</span>"
                f"{sponsorship_html}"
                f"<br><span style='color:#666;font-size:12px;'>"
                f"why: {html.escape(_why(match))}</span>"
                "</td></tr>"
            )
        sections.append(
            f"<h3 style='margin:24px 0 4px;'>{html.escape(country)} ({len(entries)})</h3>"
            "<table width='100%' cellpadding='0' cellspacing='0'>" + "".join(rows) + "</table>"
        )

    body = "".join(sections) if sections else "<p>No new matching jobs this run.</p>"

    warning = health_warning(result)
    warning_html = (
        f"<p style='padding:8px;background:#fff4e5;border-left:3px solid #d97706;'>"
        f"{html.escape(warning)}</p>"
        if warning
        else ""
    )
    sources_html = (
        "<h3 style='margin:24px 0 4px;'>Sources</h3><ul style='color:#666;font-size:12px;'>"
        + "".join(f"<li>{html.escape(line)}</li>" for line in source_lines(result))
        + "</ul>"
        if result.sources
        else ""
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Opportunities Abroad</title></head>
<body style="font-family:sans-serif;max-width:720px;">
  <h2>Opportunities Abroad</h2>
  <p style="color:#444;">{html.escape(header_line(result))}</p>
  {warning_html}
  <p style="color:#444;">{html.escape(INTRO)}</p>
  {body}
  {sources_html}
  <p style="color:#888;font-size:12px;">{html.escape(FOOTER)}</p>
</body></html>
"""


def save_html(result: RunResult, path: str | Path) -> Path:
    target = Path(path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(result), encoding="utf-8")
    logger.info("Wrote HTML digest to %s", target)
    return target
