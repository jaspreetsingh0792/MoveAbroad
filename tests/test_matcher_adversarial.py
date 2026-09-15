"""Cases where the matcher can plausibly be wrong without erroring.

These are the failures that matter for a job alert: a run that succeeds and
quietly includes the wrong country or drops the right one.
"""

from __future__ import annotations

from opportunities_abroad.matcher.engine import MatchStats, score_job
from opportunities_abroad.prefs import prefs_from_dict

from tests.conftest import make_job

EU_PREFS = {
    "include_keywords": ["python", "backend", "software engineer"],
    "locations": {
        "countries": ["Netherlands", "Germany", "EU", "Europe"],
        "cities": ["Amsterdam", "Berlin"],
    },
    "remote": {
        "accept_locations": ["Worldwide", "Anywhere", "Remote", "Europe", "EU", "India"],
        "reject_locations": ["USA only", "US only", "UK only", "United Kingdom only"],
    },
}


def prefs(**overrides):
    return prefs_from_dict({**EU_PREFS, **overrides})


def test_us_job_naming_a_target_city_in_the_description_is_rejected():
    """The bug this file exists for: geography must come from the location."""
    job = make_job(
        title="Python Engineer",
        location="Austin, Texas",
        description=(
            "Our engineering team collaborates daily with colleagues in Amsterdam "
            "and India. This role is based in our Austin office."
        ),
        remote=False,
    )
    stats = MatchStats()
    assert score_job(job, prefs(), stats=stats) is None
    assert stats.rejected_location == 1


def test_amsterdam_job_naming_the_us_in_the_description_is_kept():
    job = make_job(
        title="Python Engineer",
        location="Amsterdam, Netherlands",
        description="You will partner with our New York and San Francisco teams.",
        remote=False,
    )
    match = score_job(job, prefs())
    assert match is not None
    assert "onsite" in match.reasons


def test_description_only_mention_cannot_rescue_an_empty_location():
    job = make_job(
        title="Python Engineer",
        location="",
        description="A wonderful opportunity in Amsterdam.",
        remote=False,
    )
    assert score_job(job, prefs()) is None


def test_two_letter_country_code_needs_its_own_segment():
    """'Rio de Janeiro' contains 'de' but is not Germany."""
    job = make_job(
        title="Python Engineer",
        location="Rio de Janeiro, Brazil",
        description="Onsite python role.",
        remote=False,
    )
    assert score_job(job, prefs()) is None

    berlin = make_job(
        title="Python Engineer",
        location="Berlin, DE",
        description="Onsite python role.",
        remote=False,
    )
    assert score_job(berlin, prefs()) is not None


def test_remote_role_restricted_to_the_uk_is_rejected():
    job = make_job(
        title="Python Engineer",
        location="UK only",
        remote=True,
        description="Remote python role. Candidates must be based in the United Kingdom.",
    )
    assert score_job(job, prefs()) is None


def test_remote_role_with_a_vague_location_is_kept():
    for location in ("", "Remote", "Worldwide", "Anywhere"):
        job = make_job(
            title="Python Engineer",
            location=location,
            remote=True,
            description="Fully remote python backend role.",
        )
        assert score_job(job, prefs()) is not None, location


def test_remote_role_in_a_non_target_country_is_rejected():
    job = make_job(
        title="Python Engineer",
        location="Remote - Brazil",
        remote=True,
        description="Remote python role for candidates in Brazil.",
    )
    assert score_job(job, prefs()) is None


def test_international_does_not_trip_the_intern_exclusion():
    job = make_job(
        title="International Python Engineer",
        location="Amsterdam",
        description="Python backend role, internationally distributed team.",
        remote=False,
    )
    assert score_job(job, prefs(exclude_keywords=["intern"], title_exclude=["intern"])) is not None


def test_product_manager_mentioning_python_is_rejected_by_title_include():
    role_families = ["engineer", "developer", "sre", "architect"]
    job = make_job(
        title="Product Manager",
        location="Amsterdam",
        description="You will work closely with our Python and backend teams.",
        remote=False,
    )
    stats = MatchStats()
    assert score_job(job, prefs(title_include=role_families), stats=stats) is None
    assert stats.rejected_title == 1

    engineer = make_job(
        title="Backend Engineer",
        location="Amsterdam",
        description="Python backend role.",
        remote=False,
    )
    assert score_job(engineer, prefs(title_include=role_families)) is not None


def test_hybrid_role_outside_the_target_geography_is_rejected():
    job = make_job(
        title="Python Engineer",
        location="Toronto, Canada",
        description="Hybrid python role, three days in our Toronto office.",
        remote=False,
    )
    assert score_job(job, prefs()) is None


def test_keyword_stuffing_cannot_outrank_a_titled_local_role():
    stuffed = make_job(
        source_id="stuffed",
        url="https://example.com/stuffed",
        title="Consultant",
        location="Amsterdam",
        description=(
            "python python backend backend software engineer django flask fastapi "
            "python backend software engineer python backend"
        ),
        remote=False,
    )
    genuine = make_job(
        source_id="genuine",
        url="https://example.com/genuine",
        title="Senior Backend Software Engineer",
        location="Amsterdam, Netherlands",
        description="We are hiring a backend engineer to own our payments platform.",
        remote=False,
    )
    stuffed_match = score_job(stuffed, prefs())
    genuine_match = score_job(genuine, prefs())
    assert stuffed_match and genuine_match
    assert genuine_match.score > stuffed_match.score
