from __future__ import annotations

import logging

from opportunities_abroad.classifier import VisaClassifier
from opportunities_abroad.matcher import match_jobs_with_stats
from opportunities_abroad.models import Job, RunResult
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
    classifier: VisaClassifier | None = None,
    send: bool = False,
    mark_seen: bool = False,
    limit: int | None = None,
) -> RunResult:
    jobs = fetch_all(sources, prefs)
    matches, stats = match_jobs_with_stats(jobs, prefs)
    logger.info("Matched %s / %s fetched jobs", len(matches), len(jobs))

    new_jobs = store.filter_new([m.job for m in matches])
    new_keys = {job.key for job in new_jobs}
    fresh_matches = [m for m in matches if m.job.key in new_keys]
    already_seen = len(matches) - len(fresh_matches)

    cap = prefs.max_jobs
    if limit is not None:
        cap = limit if cap <= 0 else min(cap, limit)
    if cap > 0:
        fresh_matches = fresh_matches[:cap]
    logger.info("%s new matches after de-dupe", len(fresh_matches))

    if classifier is not None:
        classifier.annotate(fresh_matches)

    result = RunResult(
        matches=fresh_matches,
        fetched=len(jobs),
        matched=len(matches),
        already_seen=already_seen,
        too_old=stats.too_old,
        rejected_location=stats.rejected_location,
        rejected_title=stats.rejected_title,
        rejected_visa=stats.rejected_visa,
    )

    if send:
        if notifier is None:
            raise RuntimeError("send=True requires a notifier")
        if fresh_matches:
            notifier.send(result)
        else:
            logger.info("Nothing new to send")
        store.mark_seen([m.job for m in fresh_matches], notified=True)
    elif mark_seen:
        store.mark_seen([m.job for m in fresh_matches], notified=False)

    return result
