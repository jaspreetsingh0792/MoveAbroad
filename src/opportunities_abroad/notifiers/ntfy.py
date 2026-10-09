from __future__ import annotations

import os
import secrets

import httpx

from opportunities_abroad.digest import email_subject, render_compact_text
from opportunities_abroad.http import make_client
from opportunities_abroad.models import RunResult
from opportunities_abroad.notifiers.base import Notifier
from opportunities_abroad.notifiers.email import EmailConfigError, split_addrs

DEFAULT_NTFY_URL = "https://ntfy.sh"

# ntfy turns a message body over 4096 bytes into an attachment, which an email
# then only links to. Staying under it keeps the digest in the email itself.
MAX_BODY_BYTES = 4000


class NtfyEmailNotifier(Notifier):
    """Keyless email delivery through ntfy's email forwarding.

    No account, API key or SMTP server: the only setting is the recipient,
    ``EMAIL_TO``. Each run publishes to a fresh random topic with caching
    turned off, so the digest is not left readable on the public server, and
    ntfy emails it to each recipient. The public ntfy.sh server rate-limits
    email per sender IP (a small daily burst), which is plenty for one digest
    a day; set ``NTFY_URL`` to use a self-hosted server instead.
    """

    name = "ntfy-email"

    def __init__(
        self,
        mail_to: str | None = None,
        base_url: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        env = os.environ
        self.mail_to = (mail_to if mail_to is not None else env.get("EMAIL_TO", "")).strip()
        url = base_url if base_url is not None else env.get("NTFY_URL", "")
        self.base_url = (url.strip() or DEFAULT_NTFY_URL).rstrip("/")
        self._client = client

    def require_configured(self) -> None:
        if not self.mail_to:
            raise EmailConfigError(
                "Email notifier is not configured. Missing: EMAIL_TO. "
                "That is the only setting the free keyless delivery needs; "
                "set it in the environment or a .env file (see .env.example). "
                "Dry-run mode does not require email settings."
            )

    def send(self, result: RunResult) -> None:
        self.require_configured()
        title = email_subject(result)
        body = render_compact_text(result, max_bytes=MAX_BODY_BYTES)
        client = self._client or make_client()
        owns_client = self._client is None
        try:
            for address in split_addrs(self.mail_to):
                topic = f"moveabroad-{secrets.token_urlsafe(18)}"
                response = client.post(
                    f"{self.base_url}/{topic}",
                    content=body.encode("utf-8"),
                    headers={
                        "Title": title,
                        "Email": address,
                        "Cache": "no",
                        "Tags": "briefcase",
                        "Content-Type": "text/plain; charset=utf-8",
                    },
                )
                if response.status_code == 429:
                    raise RuntimeError(
                        f"{self.base_url} rate-limited the email to {address}. The public "
                        "server allows a few emails per day per IP; try again later, "
                        "set NTFY_URL to a self-hosted server, or configure SMTP_HOST."
                    )
                response.raise_for_status()
        finally:
            if owns_client:
                client.close()
