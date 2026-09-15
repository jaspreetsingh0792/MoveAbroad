from __future__ import annotations

import logging

from opportunities_abroad.classifier import VisaClassifier
from opportunities_abroad.matcher import match_jobs_with_stats
from opportunities_abroad.models import Job, RunResult, SourceHealth
from opportunities_abroad.notifiers.base import Notifier
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.sources.base import JobSource
from opportunities_abroad.store.sqlite import SqliteJobStore

logger = logging.getLogger(__name__)


def fetch_all(sources: list[JobSource], prefs: Prefs) -> tuple[list[Job], list[SourceHealth]]:
    """Fetch every source, reporting what each one managed.

    A crashing source never sinks the run, but the run has to say so —
    otherwise a dead source looks exactly like a quiet one.
    """
    jobs: list[Job] = []
    health: list[SourceHealth] = []
    for source in sources:
        logger.info("Fetching from %s", source.name)
        try:
            batch = source.fetch(prefs)
        except Exception as exc:
            logger.exception("Source %s crashed; continuing", source.name)
            health.append(SourceHealth(name=source.name, failed=True, error=repr(exc)))
            continue
        logger.info("%s: %s jobs", source.name, len(batch))
        jobs.extend(batch)
        health.append(source.health(len(batch)))
    return jobs, health


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
    jobs, source_health = fetch_all(sources, prefs)
    for report in source_health:
        if not report.healthy:
            logger.warning("Source health: %s", report.summary())
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
        rejected_seniority=stats.rejected_seniority,
        rejected_visa=stats.rejected_visa,
        sources=source_health,
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
