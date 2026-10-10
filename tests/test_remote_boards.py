"""Jobicy and Himalayas: keyless remote boards that publish where hires may live."""

from __future__ import annotations

import httpx
import pytest

from opportunities_abroad.pipeline import fetch_all
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.sources import himalayas as himalayas_module
from opportunities_abroad.sources.himalayas import HimalayasSource
from opportunities_abroad.sources.jobicy import JobicySource, format_salary
from opportunities_abroad.sources.registry import build_sources

JOBICY_JOB = {
    "id": 123456,
    "url": "https://jobicy.com/jobs/123456-python-engineer",
    "jobSlug": "123456-python-engineer",
    "jobTitle": "Senior Python Engineer",
    "companyName": "Acme",
    "jobIndustry": ["Engineering"],
    "jobType": ["Full-Time"],
    "jobGeo": "EMEA, APAC",
    "jobLevel": "Senior",
    "jobExcerpt": "Short.",
    "jobDescription": "<p>Build <b>APIs</b>.</p>",
    "pubDate": "2026-09-30T12:00:00+00:00",
    "salaryMin": 90000,
    "salaryMax": 125000,
    "salaryCurrency": "USD",
    "salaryPeriod": "yearly",
}

HIMALAYAS_JOB = {
    "title": "Backend Engineer",
    "excerpt": "Short.",
    "companyName": "Globex",
    "employmentType": "Full Time",
    "minSalary": 60000,
    "maxSalary": 80000,
    "currency": "EUR",
    "seniority": ["Mid-level"],
    "locationRestrictions": ["India", "Singapore"],
    "categories": ["Software Engineering"],
    "description": "<p>Python services.</p>",
    "pubDate": 1790000000,
    "applicationLink": "https://himalayas.app/companies/globex/jobs/backend-engineer",
    "guid": "globex-backend-engineer",
}


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def serve(*pages):
    """Serve pages in order and record the requests."""
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        body = pages[min(len(seen) - 1, len(pages) - 1)]
        return httpx.Response(200, json=body)

    return client_for(handler), seen


# --- Jobicy -----------------------------------------------------------------


def test_jobicy_maps_a_documented_record():
    client, seen = serve({"jobs": [JOBICY_JOB], "nextCursor": None})
    with client:
        jobs = JobicySource(client).fetch(prefs_from_dict({}))
    job = jobs[0]
    assert job.key == "jobicy:123456"
    assert job.title == "Senior Python Engineer"
    assert job.location == "EMEA, APAC"
    assert job.extra["eligible_regions"] == ["EMEA", "APAC"]
    assert job.remote is True
    assert job.description == "Build APIs."
    assert job.salary == "USD 90,000–125,000 / year"
    assert job.posted_at is not None and job.posted_at.year == 2026
    assert seen[0].url.params["count"] == "100"


def test_jobicy_follows_the_cursor_up_to_max_pages():
    page = {"jobs": [JOBICY_JOB], "nextCursor": "abc"}
    client, seen = serve(page)
    with client:
        JobicySource(client).fetch(prefs_from_dict({"jobicy": {"max_pages": 3}}))
    assert len(seen) == 3
    assert seen[1].url.params["cursor"] == "abc"


def test_jobicy_empty_geo_means_anywhere():
    client, _ = serve({"jobs": [{**JOBICY_JOB, "jobGeo": ""}]})
    with client:
        job = JobicySource(client).fetch(prefs_from_dict({}))[0]
    assert job.location == "Anywhere"
    assert job.extra["eligible_regions"] == ["Anywhere"]


def test_unreadable_records_mark_the_source_failed():
    client, _ = serve({"jobs": [{"something": "else"}]})
    with client:
        _, health = fetch_all([JobicySource(client)], prefs_from_dict({}))
    assert health[0].failed is True


def test_http_error_marks_the_source_failed():
    with client_for(lambda r: httpx.Response(500)) as client:
        _, health = fetch_all([JobicySource(client)], prefs_from_dict({}))
    assert health[0].failed is True


# --- Himalayas --------------------------------------------------------------


def test_himalayas_maps_a_record_with_location_restrictions():
    client, _ = serve({"jobs": [HIMALAYAS_JOB]})
    with client:
        job = HimalayasSource(client).fetch(prefs_from_dict({}))[0]
    assert job.key == "himalayas:globex-backend-engineer"
    assert job.location == "India, Singapore"
    assert job.extra["eligible_regions"] == ["India", "Singapore"]
    assert job.salary == "EUR 60,000–80,000"
    assert job.posted_at is not None
    assert job.url.startswith("https://himalayas.app/")


def test_himalayas_no_restrictions_means_worldwide():
    client, _ = serve({"jobs": [{**HIMALAYAS_JOB, "locationRestrictions": []}]})
    with client:
        job = HimalayasSource(client).fetch(prefs_from_dict({}))[0]
    assert job.location == "Worldwide"


def test_himalayas_accepts_alternative_field_spellings():
    record = {
        "title": "Data Engineer",
        "companyName": "Initech",
        "applicationUrl": "https://himalayas.app/companies/initech/jobs/data",
        "publishedAt": "2026-09-30T12:00:00Z",
        "locationRestrictions": [{"name": "Germany"}],
    }
    client, _ = serve({"jobs": [record]})
    with client:
        job = HimalayasSource(client).fetch(prefs_from_dict({}))[0]
    assert job.location == "Germany"
    assert job.posted_at is not None


def test_himalayas_pages_by_offset_until_a_short_page(monkeypatch):
    monkeypatch.setattr(himalayas_module, "PAGE_DELAY_SECONDS", 0)
    full = {"jobs": [{**HIMALAYAS_JOB, "guid": f"g{i}"} for i in range(20)]}
    short = {"jobs": [HIMALAYAS_JOB]}
    client, seen = serve(full, short)
    with client:
        jobs = HimalayasSource(client).fetch(prefs_from_dict({}))
    assert len(jobs) == 21
    assert [r.url.params["offset"] for r in seen] == ["0", "20"]


# --- Shared -----------------------------------------------------------------


@pytest.mark.parametrize(
    "args,expected",
    [
        ((50000, 70000, "eur", "yearly"), "EUR 50,000–70,000 / year"),
        ((None, 70000, None, None), "70,000"),
        ((0, 0, "USD", None), None),
        (("lots", True, "USD", None), None),
    ],
)
def test_format_salary(args, expected):
    assert format_salary(*args) == expected


def test_new_sources_are_on_by_default():
    names = [s.name for s in build_sources(prefs_from_dict({}))]
    assert {"jobicy", "himalayas", "remoteok"} <= set(names)
