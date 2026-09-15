from __future__ import annotations

import sqlite3

from opportunities_abroad.store.sqlite import SqliteJobStore
from opportunities_abroad.textutil import fingerprint

from tests.conftest import make_job

LEGACY_SCHEMA = """
CREATE TABLE seen_jobs (
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
CREATE INDEX idx_seen_url_norm ON seen_jobs(url_norm);
"""


def test_mark_and_is_seen(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    job = make_job()
    assert store.is_seen(job) is False
    store.mark_seen([job], notified=True)
    assert store.is_seen(job) is True
    assert store.count() == 1
    store.close()


def test_filter_new_skips_seen_keys(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    first = make_job(source_id="1", url="https://example.com/1")
    second = make_job(source_id="2", url="https://example.com/2", title="Staff Data Engineer")
    store.mark_seen([first])
    fresh = store.filter_new([first, second])
    assert [j.source_id for j in fresh] == ["2"]
    store.close()


def test_url_dedupe_across_sources(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    remotive = make_job(
        source="remotive",
        source_id="abc",
        url="https://jobs.example.com/role?utm=1",
    )
    arbeitnow = make_job(
        source="arbeitnow",
        source_id="xyz",
        url="https://jobs.example.com/role/",
    )
    store.mark_seen([remotive])
    assert store.is_seen(arbeitnow) is True
    assert store.filter_new([arbeitnow]) == []
    store.close()


def test_filter_new_dedupes_within_batch(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    a = make_job(source="remotive", source_id="1", url="https://jobs.example.com/role")
    b = make_job(source="arbeitnow", source_id="2", url="https://jobs.example.com/role/")
    fresh = store.filter_new([a, b])
    assert len(fresh) == 1
    assert fresh[0].source_id == "1"
    store.close()


def test_mark_seen_is_idempotent(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    job = make_job()
    store.mark_seen([job], notified=False)
    store.mark_seen([job], notified=True)
    assert store.count() == 1
    store.close()


def test_fingerprint_dedupes_same_role_on_different_urls(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    greenhouse = make_job(
        source="greenhouse",
        source_id="acme:1",
        url="https://boards.greenhouse.io/acme/jobs/1",
    )
    reposted = make_job(
        source="arbeitnow",
        source_id="acme-python-software-engineer",
        url="https://boards.greenhouse.io/acme/jobs/9999",
    )
    store.mark_seen([greenhouse])
    assert store.is_seen(reposted) is True
    assert store.filter_new([reposted]) == []
    store.close()


def test_same_title_in_two_countries_stays_two_jobs(tmp_path):
    """Databricks hiring a Software Engineer in Amsterdam and Berlin is two openings."""
    store = SqliteJobStore(tmp_path / "seen.db")
    amsterdam = make_job(
        company="Databricks",
        source_id="1",
        title="Software Engineer",
        location="Amsterdam, Netherlands",
        url="https://boards.greenhouse.io/databricks/jobs/1",
    )
    berlin = make_job(
        company="Databricks",
        source_id="2",
        title="Software Engineer",
        location="Berlin, Germany",
        url="https://boards.greenhouse.io/databricks/jobs/2",
    )
    store.mark_seen([amsterdam])
    assert store.is_seen(berlin) is False
    assert [j.source_id for j in store.filter_new([amsterdam, berlin])] == ["2"]
    store.close()


def test_same_title_in_two_cities_of_one_country_stays_two_jobs(tmp_path):
    """Amsterdam and Rotterdam are separate openings, not one duplicated."""
    store = SqliteJobStore(tmp_path / "seen.db")
    amsterdam = make_job(
        company="Databricks",
        source_id="1",
        title="Software Engineer",
        location="Amsterdam, Netherlands",
        url="https://boards.greenhouse.io/databricks/jobs/1",
    )
    rotterdam = make_job(
        company="Databricks",
        source_id="2",
        title="Software Engineer",
        location="Rotterdam, Netherlands",
        url="https://boards.greenhouse.io/databricks/jobs/2",
    )
    store.mark_seen([amsterdam])
    assert store.is_seen(rotterdam) is False
    store.close()


def test_location_spelling_differences_still_collapse(tmp_path):
    """The whole point of the fingerprint: one role, two sources, two spellings."""
    store = SqliteJobStore(tmp_path / "seen.db")
    board = make_job(
        source="greenhouse",
        source_id="acme:1",
        location="Amsterdam",
        url="https://boards.greenhouse.io/acme/jobs/1",
    )
    aggregator = make_job(
        source="arbeitnow",
        source_id="acme-python-software-engineer",
        location="Amsterdam, Netherlands",
        url="https://boards.greenhouse.io/acme/jobs/9999",
    )
    store.mark_seen([board])
    assert store.is_seen(aggregator) is True
    store.close()


def test_fingerprint_is_scoped_to_host(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    store.mark_seen([make_job(url="https://boards.greenhouse.io/acme/jobs/1")])
    elsewhere = make_job(
        source="lever",
        source_id="other:2",
        url="https://jobs.lever.co/acme/2",
    )
    assert store.is_seen(elsewhere) is False
    store.close()


def test_jobs_without_company_are_not_fingerprint_matched(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    first = make_job(source_id="1", company="", url="https://example.com/1")
    second = make_job(source_id="2", company="", url="https://example.com/2")
    store.mark_seen([first])
    assert store.is_seen(second) is False
    assert [j.source_id for j in store.filter_new([second])] == ["2"]
    store.close()


def test_batch_dedupe_uses_fingerprint(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    a = make_job(source="greenhouse", source_id="1", url="https://acme.com/jobs/1")
    b = make_job(source="lever", source_id="2", url="https://acme.com/careers/2")
    fresh = store.filter_new([a, b])
    assert [j.source for j in fresh] == ["greenhouse"]
    store.close()


def test_migrates_legacy_database_and_backfills(tmp_path):
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(LEGACY_SCHEMA)
    legacy.execute(
        """
        INSERT INTO seen_jobs (
            job_key, source, source_id, url, url_norm, title, company,
            first_seen, last_seen, notified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "remotive:1",
            "remotive",
            "1",
            "https://example.com/jobs/1",
            "https://example.com/jobs/1",
            "Python Software Engineer",
            "Acme",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
            1,
        ),
    )
    legacy.commit()
    legacy.close()

    store = SqliteJobStore(path)
    assert store.count() == 1
    row = store._conn.execute("SELECT fingerprint, location FROM seen_jobs").fetchone()

    # A legacy row has no stored location, so its fingerprint is computed with
    # the "Other" bucket. Key and URL matching still protect it.
    assert row["location"] is None
    assert row["fingerprint"] == fingerprint(
        "Acme", "Python Software Engineer", "example.com", "Other"
    )
    assert store.is_seen(make_job(source="remotive", source_id="1")) is True
    assert store.is_seen(make_job(source="lever", source_id="9")) is True
    store.close()


def test_rewritten_rows_gain_full_fingerprint_protection(tmp_path):
    """A legacy row re-seen with a location dedupes across sources again."""
    path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(path)
    legacy.executescript(LEGACY_SCHEMA)
    legacy.execute(
        """
        INSERT INTO seen_jobs (
            job_key, source, source_id, url, url_norm, title, company,
            first_seen, last_seen, notified
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "remotive:1",
            "remotive",
            "1",
            "https://example.com/jobs/1",
            "https://example.com/jobs/1",
            "Python Software Engineer",
            "Acme",
            "2026-01-01T00:00:00+00:00",
            "2026-01-01T00:00:00+00:00",
            1,
        ),
    )
    legacy.commit()
    legacy.close()

    store = SqliteJobStore(path)
    store.mark_seen([make_job(source="remotive", source_id="1")])
    reposted = make_job(source="lever", source_id="9", url="https://example.com/jobs/other")
    assert store.is_seen(reposted) is True
    store.close()


def test_migration_is_idempotent(tmp_path):
    path = tmp_path / "seen.db"
    SqliteJobStore(path).close()
    store = SqliteJobStore(path)
    store.mark_seen([make_job()])
    assert store.count() == 1
    store.close()


def test_visa_verdict_cache_roundtrip(tmp_path):
    store = SqliteJobStore(tmp_path / "seen.db")
    assert store.get_visa_verdict("test:1") is None
    store.save_visa_verdict("test:1", "yes", "Mentions Dutch work permit support.", "model-x")
    assert store.get_visa_verdict("test:1") == ("yes", "Mentions Dutch work permit support.")
    store.save_visa_verdict("test:1", "no", "EU nationals only.", "model-x")
    assert store.get_visa_verdict("test:1") == ("no", "EU nationals only.")
    store.close()
