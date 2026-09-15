from __future__ import annotations

import logging

from opportunities_abroad.models import RunResult
from opportunities_abroad.notifiers.base import Notifier

logger = logging.getLogger(__name__)


class TelegramNotifier(Notifier):
    """Telegram digest — stub.

    Planned integration is the official Telegram Bot API (HTTPS to api.telegram.org)
    using a bot token stored in the environment. Not implemented in this MVP.

    ``send`` is a documented no-op so the notifier can sit in the pipeline
    without crashing. Callers that require delivery should use EmailNotifier.
    """

    name = "telegram"

    def send(self, result: RunResult) -> None:
        logger.warning(
            "TelegramNotifier is a stub (no-op). %s match(es) not sent. "
            "Use email until the Telegram Bot API is wired up.",
            result.new_count,
        )
