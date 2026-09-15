from __future__ import annotations

import logging

from opportunities_abroad.models import Match
from opportunities_abroad.notifiers.base import Notifier

logger = logging.getLogger(__name__)


class WhatsAppNotifier(Notifier):
    """WhatsApp digest — stub.

    Planned integration is an official Business API (Meta Cloud API or Twilio),
    never WhatsApp Web scraping or unofficial clients.

    ``send`` is a documented no-op so the notifier can sit in the pipeline
    without crashing. Callers that require delivery should use EmailNotifier.
    """

    name = "whatsapp"

    def send(self, matches: list[Match]) -> None:
        logger.warning(
            "WhatsAppNotifier is a stub (no-op). %s match(es) not sent. "
            "Use email until an official WhatsApp Business API is wired up.",
            len(matches),
        )
