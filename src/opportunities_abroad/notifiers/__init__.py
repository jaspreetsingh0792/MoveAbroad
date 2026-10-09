from __future__ import annotations

import os

from opportunities_abroad.notifiers.base import Notifier
from opportunities_abroad.notifiers.email import EmailConfigError, EmailNotifier
from opportunities_abroad.notifiers.ntfy import NtfyEmailNotifier
from opportunities_abroad.notifiers.telegram import TelegramNotifier
from opportunities_abroad.notifiers.whatsapp import WhatsAppNotifier

EMAIL_PROVIDERS = ("smtp", "ntfy")


def build_email_notifier() -> EmailNotifier | NtfyEmailNotifier:
    """Pick the email channel from the environment.

    ``EMAIL_PROVIDER`` forces one. Otherwise SMTP is used when ``SMTP_HOST`` is
    set, and the free keyless ntfy delivery when it is not, so ``EMAIL_TO`` is
    the only setting a new user needs.
    """
    provider = os.environ.get("EMAIL_PROVIDER", "").strip().lower()
    if provider and provider not in EMAIL_PROVIDERS:
        raise EmailConfigError(
            f"EMAIL_PROVIDER={provider!r} is not supported. "
            f"Use one of: {', '.join(EMAIL_PROVIDERS)}, or leave it unset."
        )
    if provider == "smtp" or (not provider and os.environ.get("SMTP_HOST", "").strip()):
        return EmailNotifier()
    return NtfyEmailNotifier()


__all__ = [
    "Notifier",
    "EmailNotifier",
    "EmailConfigError",
    "NtfyEmailNotifier",
    "TelegramNotifier",
    "WhatsAppNotifier",
    "build_email_notifier",
]
