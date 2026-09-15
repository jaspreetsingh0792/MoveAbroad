from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest

from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.sources.ashby import AshbySource
from opportunities_abroad.sources.ats import parse_datetime
from opportunities_abroad.sources.greenhouse import GreenhouseSource
from opportunities_abroad.sources.lever import LeverSource
from opportunities_abroad.sources.registry import build_sources

GREENHOUSE_PAYLOAD = {
    "jobs": [
        {
            "id": 4567,
            "title": "Senior Backend Engineer",
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4567",
            "location": {"name": "Amsterdam, Netherlands"},
            "first_published": "2026-09-01T10:00:00-04:00",
            "updated_at": "2026-09-09T10:00:00-04:00",
            "content": "&lt;p&gt;Build &amp;amp; run our APIs.&lt;/p&gt;",
            "departments": [{"name": "Engineering"}],
            "company_name": "Acme BV",
        },
        {"id": 999, "title": "", "absolute_url": ""},
    ]
}

LEVER_PAYLOAD = [
    {
        "id": "abc-123",
        "text": "Platform Engineer",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "applyUrl": "https://jobs.lever.co/acme/abc-123/apply",
        "createdAt": 1788998400000,
        "categories": {
            "location": "Rotterdam",
            "team": "Platform",
            "commitment": "Full-time",
        },
        "workplaceType": "remote",
        "descriptionPlain": "Run the platform.",
        "salaryRange": {"min": 70000, "max": 90000, "currency": "EUR"},
    },
    {"id": "", "text": "No identifier", "hostedUrl": "https://jobs.lever.co/acme/x"},
]

ASHBY_PAYLOAD = {
    "jobs": [
        {
            "id": "ash-1",
            "title": "Data Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/acme/ash-1",
            "location": "Berlin",
            "isRemote": False,
            "publishedAt": "2026-09-05T08:30:00Z",
            "descriptionHtml": "<p>Own the <b>pipelines</b>.</p>",
            "department": "Data",
            "employmentType": "FullTime",
            "organizationName": "Acme GmbH",
            "compensation": {"compensationTierSummary": "€70K – €90K"},
        }
    ]
}


def client_returning(payload: object, expected_host: str) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == expected_host
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def ats_prefs():
    return prefs_from_dict(
        {"ats_boards": {"greenhouse": ["acme"], "lever": ["acme"], "ashby": ["acme"]}}
    )


def test_greenhouse_mapping(ats_prefs):
    with client_returning(GREENHOUSE_PAYLOAD, "boards-api.greenhouse.io") as client:
        jobs = GreenhouseSource(client).fetch(ats_prefs)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "greenhouse"
    assert job.source_id == "acme:4567"
    assert job.key == "greenhouse:acme:4567"
    assert job.company == "Acme BV"
    assert job.location == "Amsterdam, Netherlands"
    assert job.description == "Build & run our APIs."
    assert job.tags == ["Engineering"]
    assert job.remote is False
    assert job.posted_at == datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)


def test_greenhouse_marks_remote_locations(ats_prefs):
    payload = {
        "jobs": [
            {
                "id": 1,
                "title": "SRE",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Remote - Europe"},
                "content": "text",
            }
        ]
    }
    with client_returning(payload, "boards-api.greenhouse.io") as client:
        jobs = GreenhouseSource(client).fetch(ats_prefs)
    assert jobs[0].remote is True
    assert jobs[0].posted_at is None


def test_lever_mapping(ats_prefs):
    with client_returning(LEVER_PAYLOAD, "api.lever.co") as client:
        jobs = LeverSource(client).fetch(ats_prefs)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source_id == "acme:abc-123"
    assert job.url == "https://jobs.lever.co/acme/abc-123"
    assert job.location == "Rotterdam"
    assert job.remote is True
    assert job.description == "Run the platform."
    assert job.salary == "EUR 70000–90000"
    assert job.job_type == "Full-time"
    assert job.posted_at == datetime(2026, 9, 10, 0, 0, tzinfo=timezone.utc)


def test_lever_falls_back_to_html_description(ats_prefs):
    payload = [
        {
            "id": "x1",
            "text": "Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/x1",
            "categories": {"location": "Utrecht"},
            "description": "<p>Ship <b>things</b>.</p>",
        }
    ]
    with client_returning(payload, "api.lever.co") as client:
        jobs = LeverSource(client).fetch(ats_prefs)
    assert jobs[0].description == "Ship things."
    assert jobs[0].salary is None


def test_ashby_mapping(ats_prefs):
    with client_returning(ASHBY_PAYLOAD, "api.ashbyhq.com") as client:
        jobs = AshbySource(client).fetch(ats_prefs)

    assert len(jobs) == 1
    job = jobs[0]
    assert job.source_id == "acme:ash-1"
    assert job.company == "Acme GmbH"
    assert job.description == "Own the pipelines."
    assert job.remote is False
    assert job.salary == "€70K – €90K"
    assert job.posted_at == datetime(2026, 9, 5, 8, 30, tzinfo=timezone.utc)


def test_board_without_configuration_makes_no_calls():
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover - must not run
        raise AssertionError("no request expected without configured boards")

    prefs = prefs_from_dict({})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert GreenhouseSource(client).fetch(prefs) == []
        assert LeverSource(client).fetch(prefs) == []
        assert AshbySource(client).fetch(prefs) == []


def test_one_failing_board_does_not_sink_the_rest():
    prefs = prefs_from_dict({"ats_boards": {"greenhouse": ["broken", "acme"]}})

    def handler(request: httpx.Request) -> httpx.Response:
        if "broken" in str(request.url):
            return httpx.Response(404, json={"error": "not found"})
        return httpx.Response(200, json=GREENHOUSE_PAYLOAD)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        jobs = GreenhouseSource(client).fetch(prefs)
    assert [j.source_id for j in jobs] == ["acme:4567"]


def test_board_health_names_the_failing_slug():
    prefs = prefs_from_dict({"ats_boards": {"greenhouse": ["broken", "acme"]}})

    def handler(request: httpx.Request) -> httpx.Response:
        if "broken" in str(request.url):
            return httpx.Response(500, json={"error": "boom"})
        return httpx.Response(200, json=GREENHOUSE_PAYLOAD)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        source = GreenhouseSource(client)
        jobs = source.fetch(prefs)
        health = source.health(len(jobs))

    assert health.boards_ok == ["acme"]
    assert health.boards_failed == ["broken"]
    assert health.healthy is False
    assert "1/2 boards OK" in health.summary()
    assert "broken" in health.summary()


def test_board_health_is_clean_when_everything_works(ats_prefs):
    with client_returning(GREENHOUSE_PAYLOAD, "boards-api.greenhouse.io") as client:
        source = GreenhouseSource(client)
        health = source.health(len(source.fetch(ats_prefs)))

    assert health.healthy is True
    assert health.boards_failed == []
    assert "1/1 boards OK" in health.summary()


def test_board_health_resets_between_runs():
    prefs = prefs_from_dict({"ats_boards": {"greenhouse": ["flaky"]}})
    responses = [httpx.Response(500, json={}), httpx.Response(200, json=GREENHOUSE_PAYLOAD)]

    with httpx.Client(transport=httpx.MockTransport(lambda r: responses.pop(0))) as client:
        source = GreenhouseSource(client)
        source.fetch(prefs)
        assert source.health(0).boards_failed == ["flaky"]

        source.fetch(prefs)
        assert source.health(1).boards_failed == []
        assert source.health(1).boards_ok == ["flaky"]


def test_unexpected_payload_shape_is_ignored(ats_prefs):
    with client_returning({"unexpected": True}, "api.ashbyhq.com") as client:
        assert AshbySource(client).fetch(ats_prefs) == []


def test_registry_includes_ats_sources():
    prefs = prefs_from_dict({"ats_boards": {"greenhouse": ["acme"]}})
    names = [s.name for s in build_sources(prefs)]
    assert {"greenhouse", "lever", "ashby"} <= set(names)


def test_registry_honours_source_toggle():
    prefs = prefs_from_dict({"sources": {"lever": False}})
    names = [s.name for s in build_sources(prefs)]
    assert "lever" not in names
    assert "greenhouse" in names


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, None),
        ("", None),
        ("not a date", None),
        (1788998400000, datetime(2026, 9, 10, tzinfo=timezone.utc)),
        ("2026-09-05T08:30:00Z", datetime(2026, 9, 5, 8, 30, tzinfo=timezone.utc)),
        ("2026-09-05T08:30:00", datetime(2026, 9, 5, 8, 30, tzinfo=timezone.utc)),
    ],
)
def test_parse_datetime(value, expected):
    assert parse_datetime(value) == expected
