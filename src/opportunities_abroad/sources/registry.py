from __future__ import annotations

import logging

from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.adzuna import AdzunaSource
from opportunities_abroad.sources.arbeitnow import ArbeitnowSource
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.sources.remotive import RemotiveSource

logger = logging.getLogger(__name__)

_BUILTIN: dict[str, type[JobSource]] = {
    "remotive": RemotiveSource,
    "arbeitnow": ArbeitnowSource,
    "adzuna": AdzunaSource,
}


def build_sources(prefs: Prefs) -> list[JobSource]:
    sources: list[JobSource] = []
    for name, cls in _BUILTIN.items():
        if not prefs.source_is_enabled(name):
            logger.info("Source %s disabled in prefs", name)
            continue
        sources.append(cls())
    return sources
