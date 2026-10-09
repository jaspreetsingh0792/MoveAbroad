from __future__ import annotations

import httpx
import pytest

from opportunities_abroad.pipeline import fetch_all
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.sources.registry import build_sources
from opportunities_abroad.sources.remoteok import RemoteOKSource

LEGAL = {"last_updated": 1760000000, "legal": "API Terms of Service: credit Remote OK."}


def a_record(**overrides) -> dict:
    item = {
        "slug": "remote-python-engineer-acme-1",
        "id": "1",
        "epoch": 1760000000,
        "date": "2025-10-09T08:00:00+00:00",
        "company": "Acme",
        "position": "Python Engineer",
        "tags": ["python", "backend"],
        "description": "<p>Build services.</p>",
        "location": "Europe",
        "salary_min": 70000,
        "salary_max": 90000,
        "url": "https://remoteOK.com/remote-jobs/remote-python-engineer-acme-1",
    }
    item.update(overrides)
    return item


def fetch(payload: object, status: int = 200) -> list:
    transport = httpx.MockTransport(lambda r: httpx.Response(status, json=payload))
    with httpx.Client(transport=transport) as client:
        return RemoteOKSource(client).fetch(prefs_from_dict({}))


def test_record_is_mapped_and_legal_notice_skipped():
    jobs = fetch([LEGAL, a_record()])
    assert len(jobs) == 1
    job = jobs[0]
    assert job.key == "remoteok:1"
    assert job.title == "Python Engineer"
    assert job.company == "Acme"
    assert job.location == "Europe"
    assert job.remote is True
    assert job.description == "Build services."
    assert job.tags == ["python", "backend"]
    assert job.salary == "$70,000–$90,000"
    assert job.posted_at is not None and job.posted_at.year == 2025


def test_epoch_is_used_when_date_is_missing():
    job = fetch([LEGAL, a_record(date=None)])[0]
    assert job.posted_at is not None
    assert int(job.posted_at.timestamp()) == 1760000000


def test_blank_location_reads_as_remote_and_zero_salary_is_dropped():
    job = fetch([a_record(location="", salary_min=0, salary_max=0)])[0]
    assert job.location == "Remote"
    assert job.salary is None


@pytest.mark.parametrize("missing", ["id", "position", "url"])
def test_records_missing_required_fields_are_dropped(missing):
    record = a_record(apply_url=None)
    record[missing] = None
    assert fetch([record]) == []


def test_wrong_types_do_not_raise():
    jobs = fetch([a_record(tags="python", salary_min="lots", date=12, epoch="x")])
    assert jobs[0].tags == []
    assert jobs[0].salary == "$90,000"
    assert jobs[0].posted_at is None


def test_http_error_marks_the_source_failed():
    transport = httpx.MockTransport(lambda r: httpx.Response(503))
    with httpx.Client(transport=transport) as client:
        jobs, health = fetch_all([RemoteOKSource(client)], prefs_from_dict({}))
    assert jobs == []
    assert health[0].failed is True


def test_enabled_by_default_and_can_be_disabled():
    assert "remoteok" in [s.name for s in build_sources(prefs_from_dict({}))]
    disabled = prefs_from_dict({"sources": {"remoteok": False}})
    assert "remoteok" not in [s.name for s in build_sources(disabled)]
