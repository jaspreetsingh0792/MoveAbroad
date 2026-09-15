from __future__ import annotations

import httpx
import pytest

from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.sources.arbeitnow import ArbeitnowSource


def payload(**overrides) -> dict:
    item = {
        "slug": "acme-python-engineer",
        "title": "Python Engineer",
        "company_name": "Acme",
        "url": "https://www.arbeitnow.com/jobs/acme-python-engineer",
        "location": "Berlin",
        "description": "<p>Build services.</p>",
        "remote": True,
        "visa_sponsorship": True,
        "tags": ["python"],
        "job_types": ["full_time"],
    }
    item.update(overrides)
    return {"data": [item], "links": {}}


def source_with(body: dict) -> list:
    client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=body)))
    with client:
        return ArbeitnowSource(client).fetch(prefs_from_dict({}))


def test_visa_sponsorship_flag_is_mapped():
    jobs = source_with(payload())
    assert jobs[0].visa_sponsorship is True
    assert jobs[0].remote is True
    assert jobs[0].description == "Build services."


@pytest.mark.parametrize(
    "raw,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("false", False),
        (None, None),
        ("", None),
    ],
)
def test_visa_sponsorship_accepts_bools_and_strings(raw, expected):
    jobs = source_with(payload(visa_sponsorship=raw))
    assert jobs[0].visa_sponsorship is expected


def test_missing_visa_field_stays_unknown():
    body = payload()
    del body["data"][0]["visa_sponsorship"]
    assert source_with(body)[0].visa_sponsorship is None
