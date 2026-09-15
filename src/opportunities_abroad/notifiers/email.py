from __future__ import annotations

import html
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from opportunities_abroad.models import Match
from opportunities_abroad.notifiers.base import Notifier


class EmailConfigError(RuntimeError):
    """Raised when SMTP/email settings required for --send are missing."""


class EmailNotifier(Notifier):
    name = "email"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        mail_from: str | None = None,
        mail_to: str | None = None,
        starttls: bool | None = None,
    ) -> None:
        env = os.environ
        self.host = (host if host is not None else env.get("SMTP_HOST", "")).strip()
        self.port = int(port if port is not None else env.get("SMTP_PORT", "587") or 587)
        self.user = (user if user is not None else env.get("SMTP_USER", "")).strip()
        self.password = password if password is not None else env.get("SMTP_PASSWORD", "")
        self.mail_from = (mail_from if mail_from is not None else env.get("EMAIL_FROM", "")).strip()
        self.mail_to = (mail_to if mail_to is not None else env.get("EMAIL_TO", "")).strip()
        if starttls is None:
            flag = env.get("SMTP_STARTTLS", "true").strip().lower()
            self.starttls = flag in {"1", "true", "yes", "on"}
        else:
            self.starttls = starttls

    def require_configured(self) -> None:
        missing = []
        if not self.host:
            missing.append("SMTP_HOST")
        if not self.mail_from:
            missing.append("EMAIL_FROM")
        if not self.mail_to:
            missing.append("EMAIL_TO")
        if missing:
            raise EmailConfigError(
                "Email notifier is not configured. Missing: "
                + ", ".join(missing)
                + ". Set them in the environment or a .env file (see .env.example). "
                "SMTP_USER / SMTP_PASSWORD are optional for unauthenticated relays. "
                "Dry-run mode does not require email settings."
            )

    def send(self, matches: list[Match]) -> None:
        self.require_configured()
        subject = (
            f"[opportunities-abroad] {len(matches)} matching role"
            f"{'s' if len(matches) != 1 else ''} "
            f"({datetime.now(timezone.utc).date().isoformat()})"
        )
        text_body = render_text(matches)
        html_body = render_html(matches)

        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.mail_from
        message["To"] = self.mail_to
        message.attach(MIMEText(text_body, "plain", "utf-8"))
        message.attach(MIMEText(html_body, "html", "utf-8"))

        if self.port == 465 and not self.starttls:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=context, timeout=30) as smtp:
                self._login(smtp)
                smtp.sendmail(self.mail_from, _split_addrs(self.mail_to), message.as_string())
            return

        with smtplib.SMTP(self.host, self.port, timeout=30) as smtp:
            smtp.ehlo()
            if self.starttls:
                context = ssl.create_default_context()
                smtp.starttls(context=context)
                smtp.ehlo()
            self._login(smtp)
            smtp.sendmail(self.mail_from, _split_addrs(self.mail_to), message.as_string())

    def _login(self, smtp: smtplib.SMTP) -> None:
        if self.user:
            smtp.login(self.user, self.password or "")


def _split_addrs(value: str) -> list[str]:
    return [part.strip() for part in value.replace(";", ",").split(",") if part.strip()]


def render_text(matches: list[Match]) -> str:
    if not matches:
        return "No new matching jobs this run.\n"
    lines = [
        "Opportunities Abroad — new matching jobs",
        f"{len(matches)} listing(s). Apply on the original posting (source is credited).",
        "",
    ]
    for match in matches:
        job = match.job
        lines.extend(
            [
                f"- {job.title} @ {job.company}",
                f"  {job.location or 'Location n/a'} | {job.source} | score {match.score}",
                f"  {job.url}",
                f"  why: {', '.join(match.reasons) or 'matched prefs'}",
                "",
            ]
        )
    lines.append("This digest is for personal use. It is not a job board.")
    return "\n".join(lines)


def render_html(matches: list[Match]) -> str:
    rows = []
    for match in matches:
        job = match.job
        title = html.escape(job.title)
        company = html.escape(job.company or "Unknown company")
        location = html.escape(job.location or "n/a")
        url = html.escape(job.url, quote=True)
        source = html.escape(job.source)
        reasons = html.escape(", ".join(match.reasons) or "matched prefs")
        rows.append(
            "<tr>"
            f"<td style='padding:10px;border-bottom:1px solid #eee;'>"
            f"<a href='{url}'>{title}</a><br>"
            f"<span style='color:#444;'>{company} · {location}</span><br>"
            f"<span style='color:#666;font-size:12px;'>{source} · score {match.score} · {reasons}</span>"
            "</td></tr>"
        )
    body = (
        "<p>No new matching jobs this run.</p>"
        if not matches
        else "<table width='100%' cellpadding='0' cellspacing='0'>" + "".join(rows) + "</table>"
    )
    return f"""<!DOCTYPE html>
<html><body style="font-family:sans-serif;max-width:720px;">
  <h2>Opportunities Abroad</h2>
  <p>{len(matches)} matching listing(s). Open the original posting — sources are credited; this is a personal digest, not a job board.</p>
  {body}
</body></html>
"""
