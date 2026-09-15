from __future__ import annotations

import pytest

from opportunities_abroad.matcher.engine import MatchStats, score_job
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.seniority import UNKNOWN, classify, is_allowed

from tests.conftest import make_job


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Senior Python Engineer", "senior"),
        ("Sr. Backend Developer", "senior"),
        ("Staff Software Engineer", "staff"),
        ("Senior Staff Engineer", "staff"),
        ("Principal Engineer", "principal"),
        ("Distinguished Engineer", "principal"),
        ("Software Architect", "principal"),
        ("Engineering Team Lead", "lead"),
        ("Tech Lead, Payments", "lead"),
        ("Head of Platform Engineering", "executive"),
        ("VP of Engineering", "executive"),
        ("CTO", "executive"),
        ("Junior Developer", "junior"),
        ("Graduate Software Engineer", "junior"),
        ("Backend Engineer Intern", "intern"),
        ("Working Student Data Engineering", "intern"),
        ("Werkstudent Backend", "intern"),
        ("Medior Developer", "mid"),
        ("Backend Engineer", UNKNOWN),
        ("Software Engineer, Payments", UNKNOWN),
        ("", UNKNOWN),
        (None, UNKNOWN),
    ],
)
def test_classify(title, expected):
    assert classify(title) == expected


@pytest.mark.parametrize(
    "title,expected",
    [("Engineer I", "junior"), ("Engineer II", "mid"), ("Engineer III", "senior")],
)
def test_roman_numeral_levels(title, expected):
    """II must not fall through to the junior branch that also matches I."""
    assert classify(title) == expected


def test_is_allowed_without_configuration_keeps_everything():
    for level in ("intern", "senior", UNKNOWN):
        assert is_allowed(level, []) is True


def test_is_allowed_filters_on_the_configured_set():
    allowed = ["mid", "senior", "staff"]
    assert is_allowed("senior", allowed) is True
    assert is_allowed("junior", allowed) is False
    assert is_allowed("executive", allowed) is False


def test_unknown_levels_are_kept_by_default():
    """An oddly-titled role should be read, not silently dropped."""
    assert is_allowed(UNKNOWN, ["senior"]) is True
    assert is_allowed(UNKNOWN, ["senior"], keep_unknown=False) is False


def test_matcher_filters_on_seniority_and_counts_it():
    prefs = prefs_from_dict(
        {
            "include_keywords": ["python"],
            "locations": {"countries": ["Netherlands"]},
            "seniority": {"allow": ["mid", "senior", "staff"]},
        }
    )
    stats = MatchStats()
    lead = make_job(title="Engineering Lead Python", location="Amsterdam", remote=False)
    assert score_job(lead, prefs, stats=stats) is None
    assert stats.rejected_seniority == 1

    senior = make_job(title="Senior Python Engineer", location="Amsterdam", remote=False)
    match = score_job(senior, prefs)
    assert match is not None
    assert match.seniority == "senior"


def test_matcher_keeps_unknown_levels_unless_told_otherwise():
    base = {
        "include_keywords": ["python"],
        "locations": {"countries": ["Netherlands"]},
    }
    job = make_job(title="Python Engineer", location="Amsterdam", remote=False)

    lenient = prefs_from_dict({**base, "seniority": {"allow": ["senior"]}})
    strict = prefs_from_dict(
        {**base, "seniority": {"allow": ["senior"], "keep_unknown": False}}
    )
    assert score_job(job, lenient) is not None
    assert score_job(job, strict) is None


def test_level_is_recorded_even_without_a_filter():
    prefs = prefs_from_dict(
        {"include_keywords": ["python"], "locations": {"countries": ["Netherlands"]}}
    )
    job = make_job(title="Staff Python Engineer", location="Amsterdam", remote=False)
    assert score_job(job, prefs).seniority == "staff"
