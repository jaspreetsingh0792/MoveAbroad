from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from opportunities_abroad.digest import render_html, render_text
from opportunities_abroad.models import RunResult
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

    def send(self, result: RunResult) -> None:
        self.require_configured()
        count = result.new_count
        subject = (
            f"[opportunities-abroad] {count} matching role"
            f"{'s' if count != 1 else ''} "
            f"({datetime.now(timezone.utc).date().isoformat()})"
        )
        text_body = render_text(result)
        html_body = render_html(result)

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
