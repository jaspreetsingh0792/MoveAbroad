from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from opportunities_abroad.models import Job
from opportunities_abroad.textutil import fingerprint, normalize_url


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
                fingerprint TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                notified INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_seen_url_norm ON seen_jobs(url_norm);

            CREATE TABLE IF NOT EXISTS visa_verdicts (
                job_key TEXT PRIMARY KEY,
                verdict TEXT NOT NULL,
                reason TEXT,
                model TEXT,
                checked_at TEXT NOT NULL
            );
            """
        )
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        """Bring a database written by an older version up to the current schema."""
        columns = {row["name"] for row in self._conn.execute("PRAGMA table_info(seen_jobs)")}
        if "fingerprint" not in columns:
            self._conn.execute("ALTER TABLE seen_jobs ADD COLUMN fingerprint TEXT")
            self._backfill_fingerprints()
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_seen_fingerprint ON seen_jobs(fingerprint)"
        )

    def _backfill_fingerprints(self) -> None:
        rows = self._conn.execute("SELECT job_key, company, title, url FROM seen_jobs").fetchall()
        updates = [
            (fingerprint(row["company"], row["title"], row["url"]), row["job_key"]) for row in rows
        ]
        self._conn.executemany(
            "UPDATE seen_jobs SET fingerprint = ? WHERE job_key = ?",
            [u for u in updates if u[0]],
        )

    def is_seen(self, job: Job) -> bool:
        url_norm = normalize_url(job.url)
        identity = fingerprint(job.company, job.title, job.url)
        row = self._conn.execute(
            """
            SELECT 1 FROM seen_jobs
            WHERE job_key = ?
               OR (? != '' AND url_norm = ?)
               OR (? != '' AND fingerprint = ?)
            LIMIT 1
            """,
            (job.key, url_norm, url_norm, identity, identity),
        ).fetchone()
        return row is not None

    def filter_new(self, jobs: list[Job]) -> list[Job]:
        """Return jobs not previously stored, de-duplicated within this batch too."""
        fresh: list[Job] = []
        seen_keys: set[str] = set()
        seen_urls: set[str] = set()
        seen_prints: set[str] = set()
        for job in jobs:
            url_norm = normalize_url(job.url)
            identity = fingerprint(job.company, job.title, job.url)
            if job.key in seen_keys:
                continue
            if url_norm and url_norm in seen_urls:
                continue
            if identity and identity in seen_prints:
                continue
            if self.is_seen(job):
                continue
            seen_keys.add(job.key)
            if url_norm:
                seen_urls.add(url_norm)
            if identity:
                seen_prints.add(identity)
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
                    fingerprint(job.company, job.title, job.url),
                    now,
                    now,
                    1 if notified else 0,
                )
            )
        self._conn.executemany(
            """
            INSERT INTO seen_jobs (
                job_key, source, source_id, url, url_norm, title, company, fingerprint,
                first_seen, last_seen, notified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_key) DO UPDATE SET
                last_seen = excluded.last_seen,
                notified = MAX(seen_jobs.notified, excluded.notified),
                url = excluded.url,
                url_norm = excluded.url_norm,
                fingerprint = excluded.fingerprint
            """,
            rows,
        )
        self._conn.commit()

    def count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) AS n FROM seen_jobs").fetchone()
        return int(row["n"]) if row else 0

    def get_visa_verdict(self, job_key: str) -> tuple[str, str] | None:
        """Cached classifier verdict as (verdict, reason), or None if unseen."""
        row = self._conn.execute(
            "SELECT verdict, reason FROM visa_verdicts WHERE job_key = ?",
            (job_key,),
        ).fetchone()
        if row is None:
            return None
        return row["verdict"], row["reason"] or ""

    def save_visa_verdict(self, job_key: str, verdict: str, reason: str, model: str) -> None:
        self._conn.execute(
            """
            INSERT INTO visa_verdicts (job_key, verdict, reason, model, checked_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(job_key) DO UPDATE SET
                verdict = excluded.verdict,
                reason = excluded.reason,
                model = excluded.model,
                checked_at = excluded.checked_at
            """,
            (job_key, verdict, reason, model, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
