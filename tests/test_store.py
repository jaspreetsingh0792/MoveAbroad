from __future__ import annotations

from opportunities_abroad.store.sqlite import SqliteJobStore

from tests.conftest import make_job


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
    second = make_job(source_id="2", url="https://example.com/2")
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
