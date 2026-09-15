from __future__ import annotations

import pytest

from opportunities_abroad.textutil import normalize_url, strip_html


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),
        ("", ""),
        ("plain text", "plain text"),
        ("<p>Hello <b>world</b></p>", "Hello world"),
        ("<p>Ship <b>things</b>.</p>", "Ship things."),
        ("<li>One</li><li>Two</li>", "One Two"),
        ("Tabs\tand\nnewlines", "Tabs and newlines"),
        ("R&amp;D team", "R&D team"),
        ("<span>Salary</span>: <b>90k</b>!", "Salary: 90k!"),
    ],
)
def test_strip_html(raw, expected):
    assert strip_html(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, ""),
        ("https://Example.com/Jobs/1/", "https://example.com/jobs/1"),
        ("https://example.com/jobs/1?utm_source=x", "https://example.com/jobs/1"),
        ("  https://example.com/jobs/1  ", "https://example.com/jobs/1"),
    ],
)
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected
