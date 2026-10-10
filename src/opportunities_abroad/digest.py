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
DISCLAIMER = "Visa notes are signals read from the posting, not immigration advice."


def header_line(result: RunResult) -> str:
    """One-line account of the run, including what never made the digest."""
    parts = [
        f"{result.new_count} new",
        f"{result.already_seen} already seen",
        f"{result.too_old} too old",
        f"{result.rejected} rejected (US-only / title / seniority / visa)",
    ]
    if result.backlog:
        parts.insert(1, f"{result.backlog} held for next run")
    if result.rejected_relocation:
        place = result.based_in.title() if result.based_in else "your country"
        parts.insert(-1, f"{result.rejected_relocation} not workable from {place}")
    return " · ".join(parts)


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
    if match.seniority and match.seniority != "unknown":
        parts.append(match.seniority)
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


# --- Shared pieces for the email renderings ----------------------------------

SOURCE_NAMES = {
    "remotive": "Remotive",
    "arbeitnow": "Arbeitnow",
    "remoteok": "Remote OK",
    "jobicy": "Jobicy",
    "himalayas": "Himalayas",
    "adzuna": "Adzuna",
    "greenhouse": "Greenhouse",
    "lever": "Lever",
    "ashby": "Ashby",
}

COUNTRY_FLAGS = {
    "Netherlands": "🇳🇱",
    "Germany": "🇩🇪",
    "Belgium": "🇧🇪",
    "Austria": "🇦🇹",
    "Ireland": "🇮🇪",
    "France": "🇫🇷",
    "Spain": "🇪🇸",
    "Portugal": "🇵🇹",
    "Sweden": "🇸🇪",
    "Denmark": "🇩🇰",
    "Finland": "🇫🇮",
    "Norway": "🇳🇴",
    "Poland": "🇵🇱",
    "Czech Republic": "🇨🇿",
    "Switzerland": "🇨🇭",
    "Luxembourg": "🇱🇺",
    "Estonia": "🇪🇪",
    "Europe": "🇪🇺",
    "Remote": "🌍",
}


def source_name(source: str) -> str:
    return SOURCE_NAMES.get(source, source)


def country_label(country: str) -> str:
    return f"{COUNTRY_FLAGS.get(country, '📍')} {country}"


def work_mode(match: Match) -> str:
    if "hybrid" in match.reasons:
        return "Hybrid"
    if is_remote(match):
        return "Remote"
    if "onsite" in match.reasons:
        return "On-site"
    return ""


def visa_note(match: Match) -> str:
    """The one line that says why this job works for someone moving abroad."""
    if match.sponsorship == "yes":
        reason = (match.sponsorship_reason or "").strip()
        return "Visa sponsorship likely" + (f" — {reason}" if reason else "")
    if match.sponsorship == "no":
        reason = (match.sponsorship_reason or "").strip()
        return "Sponsorship unlikely" + (f" — {reason}" if reason else "")
    if match.highlight:
        return match.highlight
    if "visa:sponsor-register" in match.reasons:
        return "Employer is a licensed visa sponsor"
    return ""


def note_icon(match: Match) -> str:
    """🌍 for a remote role open where the reader lives, ✈ for a move."""
    return "🌍" if match.highlight.startswith("Open ") and not match.sponsorship else "✈"


def job_details(match: Match, now: datetime | None = None) -> list[str]:
    """Work mode, level, age and pay: the facts a reader scans for."""
    job = match.job
    parts = [work_mode(match)]
    if match.seniority and match.seniority != "unknown":
        parts.append(match.seniority.title())
    parts.append(relative_age(job.posted_at, now))
    parts.append(job.salary or "")
    return [p for p in parts if p]


def digest_title(result: RunResult) -> str:
    count = result.new_count
    return f"{count} new job{'s' if count != 1 else ''} abroad"


def email_subject(result: RunResult) -> str:
    """ASCII-safe subject: some relays reject non-ASCII header values."""
    today = datetime.now(timezone.utc).strftime("%d %b")
    visa, _ = summary_counts(result)
    extra = f", {visa} with visa support" if visa else ""
    return f"MoveAbroad: {digest_title(result)}{extra} ({today})"


def summary_counts(result: RunResult) -> tuple[int, int]:
    """How many new jobs carry visa/relocation evidence, and how many are remote."""
    visa = sum(1 for m in result.matches if _has_visa_evidence(m))
    remote = sum(1 for m in result.matches if is_remote(m))
    return visa, remote


def _has_visa_evidence(match: Match) -> bool:
    if match.sponsorship == "yes":
        return True
    if match.sponsorship == "no":
        return False
    return any(r.startswith("visa:") and r != "visa:restricted" for r in match.reasons)


def _numbered(result: RunResult) -> list[tuple[str, list[tuple[int, Match]]]]:
    """Country groups with jobs numbered 1..N across the whole digest."""
    groups = []
    counter = 0
    for country, matches in group_by_country(result.matches):
        numbered = []
        for match in matches:
            counter += 1
            numbered.append((counter, match))
        groups.append((country, numbered))
    return groups


def _text_job(number: int, match: Match) -> str:
    job = match.job
    lines = [f"{number}. {job.title}"]
    where = " · ".join(p for p in (job.company or "Unknown company", job.location) if p)
    lines.append(f"   {where}")
    details = job_details(match)
    if details:
        lines.append(f"   {' · '.join(details)}")
    note = visa_note(match)
    if note:
        lines.append(f"   {note_icon(match)} {note}")
    lines.append(f"   → {job.url}  (via {source_name(job.source)})")
    return "\n".join(lines) + "\n"


def _text_heading(country: str, count: int) -> str:
    label = f"{country_label(country)} · {count}"
    return f"{label}\n{'─' * 28}\n"


def _text_intro(result: RunResult) -> list[str]:
    today = datetime.now(timezone.utc).strftime("%a %d %b %Y")
    lines = [f"MoveAbroad — {digest_title(result)} · {today}"]
    if result.matches:
        visa, remote = summary_counts(result)
        lines.append(f"{visa} with visa or relocation support · {remote} remote-friendly")
    warning = health_warning(result)
    if warning:
        lines.append(warning)
    return lines


def render_text(result: RunResult) -> str:
    """Plain-text email, the alternative part of the HTML message."""
    lines = [*_text_intro(result), ""]
    if not result.matches:
        lines.append("No new matching jobs this run.")
    for country, numbered in _numbered(result):
        lines.append(_text_heading(country, len(numbered)))
        lines.extend(_text_job(number, match) for number, match in numbered)
    lines.extend(["", "Run summary", "-----------", header_line(result), ""])
    lines.extend(_sources_block(result))
    lines.extend([INTRO, FOOTER])
    return "\n".join(lines)


def render_compact_text(result: RunResult, max_bytes: int) -> str:
    """Plain-text digest that fits in ``max_bytes`` of UTF-8.

    For channels with a hard body limit. Same layout as the full text email,
    best groups first; whatever does not fit is counted rather than cut
    mid-line.
    """
    head = "\n".join([*_text_intro(result), ""]) + "\n"
    tail = f"\n{header_line(result)}\n{FOOTER}"
    if not result.matches:
        return f"{head}No new matching jobs this run.\n{tail}"

    blocks: list[str] = []
    for country, numbered in _numbered(result):
        heading = _text_heading(country, len(numbered))
        for index, (number, match) in enumerate(numbered):
            entry = _text_job(number, match) + "\n"
            blocks.append((heading if index == 0 else "") + entry)

    def size(text: str) -> int:
        return len(text.encode("utf-8"))

    body = head
    kept = 0
    for index, block in enumerate(blocks):
        remaining = len(blocks) - index - 1
        # Reserve room for the "more" line any later cut would need.
        more = f"…and {remaining} more not shown.\n" if remaining else ""
        if size(body + block + more + tail) > max_bytes:
            break
        body += block
        kept += 1
    dropped = len(blocks) - kept
    if dropped:
        body += f"…and {dropped} more not shown.\n"
    return body + tail


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


# Email clients ignore <style> blocks and modern CSS unevenly, so everything is
# inline and laid out with tables.
_INK = "#0f172a"
_MUTED = "#64748b"
_LINE = "#e2e8f0"
_ACCENT = "#0f766e"
_PAGE = "#f1f5f9"
_FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

_S_CARD = f"margin:0 0 12px;background:#ffffff;border:1px solid {_LINE};border-radius:12px;"
_S_TITLE = f"font-size:17px;font-weight:700;color:{_INK};text-decoration:none;line-height:1.35;"
_S_BUTTON = (
    "display:inline-block;padding:9px 16px;font-size:14px;font-weight:600;"
    "color:#ffffff;text-decoration:none;"
)
_S_VIA = f"padding-left:12px;font-size:12px;color:{_MUTED};"
_S_BRAND = "font-size:13px;letter-spacing:.08em;text-transform:uppercase;opacity:.85;"
_S_FOOT = (
    f"padding:20px 4px 0;border-top:1px solid {_LINE};font-size:12px;"
    f"color:{_MUTED};line-height:1.6;"
)

_BADGE_STYLES = {
    "mode": ("#eef2ff", "#3730a3"),
    "visa": ("#dcfce7", "#166534"),
    "warn": ("#fee2e2", "#991b1b"),
    "plain": ("#f1f5f9", "#334155"),
}


def _badge(text: str, kind: str = "plain") -> str:
    background, color = _BADGE_STYLES[kind]
    return (
        f"<span style='display:inline-block;margin:0 6px 6px 0;padding:3px 10px;"
        f"border-radius:999px;background:{background};color:{color};font-size:12px;"
        f"font-weight:600;line-height:18px;'>{html.escape(text)}</span>"
    )


def _html_job(number: int, match: Match) -> str:
    job = match.job
    url = html.escape(job.url, quote=True)
    badges = []
    mode = work_mode(match)
    if mode:
        badges.append(_badge(mode, "mode"))
    note = visa_note(match)
    if note:
        kind = "warn" if match.sponsorship == "no" else "visa"
        badges.append(_badge(f"{note_icon(match)} {note}", kind))
    for fact in job_details(match)[1 if mode else 0 :]:
        badges.append(_badge(fact))
    where = " · ".join(p for p in (job.company or "Unknown company", job.location) if p)
    return f"""
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="{_S_CARD}">
  <tr><td style="padding:16px 18px;">
    <div style="font-size:12px;color:{_MUTED};margin-bottom:4px;">#{number}</div>
    <a href="{url}" style="{_S_TITLE}">{html.escape(job.title)}</a>
    <div style="font-size:14px;color:#475569;margin:4px 0 10px;">{html.escape(where)}</div>
    <div>{''.join(badges)}</div>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:8px;"><tr>
      <td style="border-radius:8px;background:{_ACCENT};">
        <a href="{url}" style="{_S_BUTTON}">View job →</a>
      </td>
      <td style="{_S_VIA}">via {html.escape(source_name(job.source))}</td>
    </tr></table>
  </td></tr>
</table>"""


def _stat(value: int, label: str) -> str:
    return (
        f"<td width='33%' style='padding:12px 8px;text-align:center;background:#ffffff;"
        f"border:1px solid {_LINE};border-radius:10px;'>"
        f"<div style='font-size:22px;font-weight:700;color:{_INK};'>{value}</div>"
        f"<div style='font-size:12px;color:{_MUTED};'>{html.escape(label)}</div></td>"
    )


def render_html(result: RunResult) -> str:
    visa, remote = summary_counts(result)
    today = datetime.now(timezone.utc).strftime("%A %d %B %Y")
    title = digest_title(result)
    subtitle = (
        f"Workable from {result.based_in.title()} · {today}" if result.based_in else today
    )

    sections = []
    for country, numbered in _numbered(result):
        cards = "".join(_html_job(number, match) for number, match in numbered)
        sections.append(
            f"<h2 style='margin:28px 0 12px;font-size:16px;color:{_INK};'>"
            f"{html.escape(country_label(country))} "
            f"<span style='color:{_MUTED};font-weight:400;'>· {len(numbered)}</span></h2>"
            + cards
        )
    body = (
        "".join(sections)
        if sections
        else "<p style='margin:24px 0;color:#475569;'>No new matching jobs this run.</p>"
    )

    stats = ""
    if result.matches:
        gap = "<td width='8'></td>"
        stats = (
            "<table role='presentation' width='100%' cellpadding='0' cellspacing='0' "
            "style='margin-top:20px;'><tr>"
            + _stat(result.new_count, "new jobs")
            + gap
            + _stat(visa, "visa / relocation")
            + gap
            + _stat(remote, "remote-friendly")
            + "</tr></table>"
        )

    warning = health_warning(result)
    warning_html = (
        f"<p style='margin:20px 0 0;padding:10px 14px;background:#fff7ed;border-left:4px solid "
        f"#ea580c;border-radius:6px;color:#9a3412;font-size:14px;'>{html.escape(warning)}</p>"
        if warning
        else ""
    )
    sources_html = (
        f"<p style='margin:8px 0 0;font-size:12px;color:{_MUTED};'>Sources: "
        + html.escape(" · ".join(source_lines(result)))
        + "</p>"
        if result.sources
        else ""
    )
    preheader = f"{title} · {visa} with visa or relocation support · {remote} remote-friendly"

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>MoveAbroad — {html.escape(title)}</title></head>
<body style="margin:0;padding:0;background:{_PAGE};font-family:{_FONT};">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_PAGE};">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:640px;">
  <tr><td style="padding:24px;background:{_ACCENT};border-radius:14px;color:#ffffff;">
    <div style="{_S_BRAND}">✈ MoveAbroad</div>
    <div style="font-size:26px;font-weight:700;margin-top:6px;">{html.escape(title)}</div>
    <div style="font-size:14px;opacity:.9;margin-top:4px;">{html.escape(subtitle)}</div>
  </td></tr>
  <tr><td>
    {stats}
    {warning_html}
    {body}
  </td></tr>
  <tr><td style="{_S_FOOT}">
    <p style="margin:0;">{html.escape(header_line(result))}</p>
    {sources_html}
    <p style="margin:8px 0 0;">{html.escape(INTRO)} {html.escape(DISCLAIMER)}</p>
    <p style="margin:8px 0 0;">{html.escape(FOOTER)}</p>
  </td></tr>
</table>
</td></tr></table>
</body></html>
"""


def save_html(result: RunResult, path: str | Path) -> Path:
    target = Path(path)
    if target.parent != Path(""):
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_html(result), encoding="utf-8")
    logger.info("Wrote HTML digest to %s", target)
    return target
