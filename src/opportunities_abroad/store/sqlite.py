from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from opportunities_abroad.models import Job
from opportunities_abroad.textutil import normalize_url


class SqliteJobStore:
    """SQLite-backed seen-job store used to avoid duplicate alerts."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteJobStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                job_key TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                source_id TEXT NOT NULL,
                url TEXT,
                url_norm TEXT,
                title TEXT,
                company TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_seen_url_norm ON seen_jobs(url_norm);
            """
        )
        self._conn.commit()

    def is_seen(self, job: Job) -> bool:
        url_norm = normalize_url(job.url)
        row = self._conn.execute(
            "SELECT 1 FROM seen_jobs WHERE job_key = ? OR (url_norm != '' AND url_norm = ?) LIMIT 1",
            (job.key, url_norm),
        ).fetchone()
        return row is not None

    def filter_new(self, jobs: list[Job]) -> list[Job]:
        """Return jobs not previously stored, de-duplicated within this batch too."""
        fresh: list[Job] = []
        seen_keys: set[str] = set()
        seen_urls: set[str] = set()
        for job in jobs:
            url_norm = normalize_url(job.url)
            if job.key in seen_keys:
                continue
            if url_norm and url_norm in seen_urls:
                continue
            if self.is_seen(job):
                continue
            seen_keys.add(job.key)
            if url_norm:
                seen_urls.add(url_norm)
            fresh.append(job)
        return fresh

    def mark_seen(self, jobs: list[Job], notified: bool = False) -> None:
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for job in jobs:
            rows.append(
                (
                    job.key,
                    job.source,
                    job.source_id,
                    job.url,
                    normalize_url(job.url),
                    job.title,
                    job.company,
                    now,
                    now,
                    1 if notified else 0,
                )
            )
        self._conn.executemany(
            """
            INSERT INTO seen_jobs (
                job_key, source, source_id, url, url_norm, title, company,
                first_seen, last_seen, notified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_key) DO UPDATE SET
                last_seen = excluded.last_seen,
                notified = MAX(seen_jobs.notified, excluded.notified),
                url = excluded.url,
                url_norm = excluded.url_norm
            """,
            rows,
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM seen_jobs").fetchone()
        return int(row["n"]) if row else 0
