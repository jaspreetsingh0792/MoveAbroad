from __future__ import annotations

import logging

from opportunities_abroad.matcher import match_jobs
from opportunities_abroad.models import Job, Match
from opportunities_abroad.notifiers.base import Notifier
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.store.sqlite import SqliteJobStore

logger = logging.getLogger(__name__)


def fetch_all(sources: list[JobSource], prefs: Prefs) -> list[Job]:
    jobs: list[Job] = []
    for source in sources:
        logger.info("Fetching from %s", source.name)
        try:
            batch = source.fetch(prefs)
        except Exception:
            logger.exception("Source %s crashed; continuing", source.name)
            batch = []
        logger.info("%s: %s jobs", source.name, len(batch))
        jobs.extend(batch)
    return jobs


def run(
    prefs: Prefs,
    sources: list[JobSource],
    store: SqliteJobStore,
    *,
    notifier: Notifier | None = None,
    send: bool = False,
    mark_seen: bool = False,
    limit: int | None = None,
) -> list[Match]:
    jobs = fetch_all(sources, prefs)
    matches = match_jobs(jobs, prefs)
    logger.info("Matched %s / %s fetched jobs", len(matches), len(jobs))

    new_jobs = store.filter_new([m.job for m in matches])
    new_keys = {job.key for job in new_jobs}
    fresh_matches = [m for m in matches if m.job.key in new_keys]
    cap = prefs.max_jobs
    if limit is not None:
        cap = limit if cap <= 0 else min(cap, limit)
    if cap > 0:
        fresh_matches = fresh_matches[:cap]
    logger.info("%s new matches after de-dupe", len(fresh_matches))

    if send:
        if notifier is None:
            raise RuntimeError("send=True requires a notifier")
        if fresh_matches:
            notifier.send(fresh_matches)
        else:
            logger.info("Nothing new to send")
        store.mark_seen([m.job for m in fresh_matches], notified=True)
    elif mark_seen:
        store.mark_seen([m.job for m in fresh_matches], notified=False)

    return fresh_matches
