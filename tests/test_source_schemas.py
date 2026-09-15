"""What each source does when the upstream payload is not what we expect.

These boards are public APIs we do not control: fields get renamed, go null,
or change type without notice. A mapper must drop what it cannot read and keep
what it can, never raise — and the run must still be able to tell that
something went wrong, which is what the board-health assertions cover.
"""

from __future__ import annotations

import httpx
import pytest

from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.sources.arbeitnow import ArbeitnowSource
from opportunities_abroad.sources.ashby import AshbySource
from opportunities_abroad.sources.greenhouse import GreenhouseSource
from opportunities_abroad.sources.lever import LeverSource
from opportunities_abroad.sources.remotive import RemotiveSource

ATS_PREFS = prefs_from_dict(
    {"ats_boards": {"greenhouse": ["acme"], "lever": ["acme"], "ashby": ["acme"]}}
)
PLAIN_PREFS = prefs_from_dict({})


def serving(payload: object, status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def fetch(source_cls, payload, prefs=None, status=200):
    with serving(payload, status) as client:
        return source_cls(client).fetch(prefs if prefs is not None else ATS_PREFS)


# Each entry: source class, a payload wrapper, and a minimal valid record.
ATS_CASES = (
    pytest.param(
        GreenhouseSource,
        lambda records: {"jobs": records},
        {
            "id": 1,
            "title": "Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
            "location": {"name": "Amsterdam"},
            "content": "text",
        },
        id="greenhouse",
    ),
    pytest.param(
        LeverSource,
        lambda records: records,
        {
            "id": "1",
            "text": "Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/1",
            "categories": {"location": "Amsterdam"},
            "descriptionPlain": "text",
        },
        id="lever",
    ),
    pytest.param(
        AshbySource,
        lambda records: {"jobs": records},
        {
            "id": "1",
            "title": "Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/1",
            "location": "Amsterdam",
            "descriptionPlain": "text",
        },
        id="ashby",
    ),
)


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_valid_record_is_mapped(source_cls, wrap, record):
    jobs = fetch(source_cls, wrap([record]))
    assert len(jobs) == 1
    assert jobs[0].title == "Engineer"


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_empty_collection_is_not_an_error(source_cls, wrap, record):
    assert fetch(source_cls, wrap([])) == []


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_null_fields_do_not_raise(source_cls, wrap, record):
    nulled = dict.fromkeys(record)
    assert fetch(source_cls, wrap([nulled])) == []


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_records_missing_required_fields_are_dropped(source_cls, wrap, record):
    for field in record:
        partial = {k: v for k, v in record.items() if k != field}
        # Dropping any single field must never raise, whatever it maps to.
        fetch(source_cls, wrap([partial]))

    good_and_bad = wrap([record, {"unrelated": "shape"}])
    assert len(fetch(source_cls, good_and_bad)) == 1


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_wrong_types_do_not_raise(source_cls, wrap, record):
    mangled = dict(record)
    mangled.update({key: ["unexpected", "list"] for key in list(mangled)[:2]})
    fetch(source_cls, wrap([mangled]))


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_non_object_records_are_skipped(source_cls, wrap, record):
    assert fetch(source_cls, wrap(["a string", 42, None])) == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"jobs": None},
        {"data": "not a list"},
        [],
        "a bare string",
        42,
        None,
    ],
)
@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_unrecognised_envelopes_yield_nothing(source_cls, wrap, record, payload):
    assert fetch(source_cls, payload) == []


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_http_errors_are_reported_as_board_failures(source_cls, wrap, record):
    for status in (401, 404, 429, 500, 503):
        with serving({"error": "nope"}, status) as client:
            source = source_cls(client)
            assert source.fetch(ATS_PREFS) == []
            assert source.health(0).boards_failed == ["acme"]
            assert source.health(0).healthy is False


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_non_json_body_is_a_board_failure(source_cls, wrap, record):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>maintenance</html>")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = source_cls(client)
        assert source.fetch(ATS_PREFS) == []
        assert source.health(0).boards_failed == ["acme"]


@pytest.mark.parametrize("source_cls,wrap,record", ATS_CASES)
def test_an_unreadable_record_is_counted_not_swallowed(source_cls, wrap, record):
    """A record the mapper cannot read costs that record, not the board — but it shows."""
    mangled = dict(record)
    mangled[next(iter(mangled))] = ["unexpected", "list"]

    with serving(wrap([record, mangled])) as client:
        source = source_cls(client)
        jobs = source.fetch(ATS_PREFS)
        health = source.health(len(jobs))

    assert health.boards_ok == ["acme"]
    assert health.boards_failed == []
    if health.records_skipped:
        assert health.healthy is False
        assert "unreadable record" in health.summary()


def test_arbeitnow_survives_a_changed_schema():
    payload = {
        "data": [
            {"slug": None, "title": None, "url": None},
            {"unrelated": "shape"},
            {
                "slug": "ok",
                "title": "Engineer",
                "url": "https://www.arbeitnow.com/jobs/ok",
                "company_name": None,
                "location": None,
                "description": None,
                "tags": None,
                "job_types": None,
                "remote": "unexpected string",
                "visa_sponsorship": 1,
            },
        ],
        "links": {},
    }
    jobs = fetch(ArbeitnowSource, payload, prefs=PLAIN_PREFS)
    assert [j.source_id for j in jobs] == ["ok"]
    assert jobs[0].company == ""
    assert jobs[0].description == ""


def test_arbeitnow_missing_envelope_is_not_an_error():
    for payload in ({}, {"data": None}, {"data": "nope"}):
        assert fetch(ArbeitnowSource, payload, prefs=PLAIN_PREFS) == []


def test_remotive_survives_a_changed_schema():
    payload = {
        "jobs": [
            {"id": None, "title": None, "url": None},
            {"unrelated": "shape"},
            {
                "id": 7,
                "title": "Python Engineer",
                "url": "https://remotive.com/jobs/7",
                "company_name": None,
                "candidate_required_location": None,
                "description": None,
                "tags": None,
                "publication_date": "not a date",
                "category": "software-dev",
            },
        ]
    }
    jobs = fetch(RemotiveSource, payload, prefs=PLAIN_PREFS)
    assert [j.source_id for j in jobs] == ["7"]
    assert jobs[0].posted_at is None


def test_remotive_transport_failure_returns_nothing():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert RemotiveSource(client).fetch(PLAIN_PREFS) == []
