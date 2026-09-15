from __future__ import annotations

from datetime import datetime, timedelta, timezone

from opportunities_abroad.matcher.engine import (
    MatchStats,
    country_for_location,
    match_jobs,
    match_jobs_with_stats,
    score_job,
)
from opportunities_abroad.prefs import prefs_from_dict

from tests.conftest import make_job


def test_include_keyword_in_title(sample_prefs):
    job = make_job(title="Senior Python Engineer", description="Build APIs.")
    match = score_job(job, sample_prefs)
    assert match is not None
    assert match.score > 0
    assert any("python" in r for r in match.reasons)


def test_intern_does_not_match_international(sample_prefs):
    job = make_job(
        title="International Python Software Engineer",
        description="Role open internationally with relocation.",
        location="Remote",
        remote=True,
    )
    assert score_job(job, sample_prefs) is not None


def test_exclude_intern_role(sample_prefs):
    job = make_job(title="Python Intern", description="Internship for students.")
    assert score_job(job, sample_prefs) is None


def test_missing_include_keyword(sample_prefs):
    job = make_job(
        title="Retail Store Manager",
        description="Manage a shop in Amsterdam.",
        tags=["retail"],
    )
    assert score_job(job, sample_prefs) is None


def test_onsite_amsterdam_matches(sample_prefs):
    job = make_job(location="Amsterdam", remote=False)
    match = score_job(job, sample_prefs)
    assert match is not None
    assert "onsite" in match.reasons or "hybrid" in match.reasons


def test_onsite_new_york_does_not_match(sample_prefs):
    job = make_job(
        title="Python Software Engineer",
        location="New York, USA",
        description="On-site Python role in Manhattan.",
        remote=False,
    )
    assert score_job(job, sample_prefs) is None


def test_remote_worldwide_matches(sample_prefs):
    job = make_job(
        location="Worldwide",
        remote=True,
        description="Fully remote Python backend role.",
    )
    match = score_job(job, sample_prefs)
    assert match is not None
    assert "remote" in match.reasons


def test_remote_usa_only_rejected(sample_prefs):
    job = make_job(
        title="Python Software Engineer",
        location="USA only",
        remote=True,
        description="Candidates must be located in the United States.",
    )
    assert score_job(job, sample_prefs) is None


def test_remote_only_drops_onsite(sample_prefs):
    sample_prefs.remote_only = True
    onsite = make_job(location="Berlin, Germany", remote=False, description="Office Python role.")
    remote = make_job(
        source_id="2",
        url="https://example.com/jobs/2",
        location="Europe",
        remote=True,
        description="Remote Python role.",
    )
    assert score_job(onsite, sample_prefs) is None
    assert score_job(remote, sample_prefs) is not None


def test_visa_keywords_boost_score(sample_prefs):
    plain = make_job(description="Python backend. Hybrid in Amsterdam.", location="Amsterdam")
    visa = make_job(
        source_id="2",
        url="https://example.com/jobs/2",
        description="Python backend with visa sponsorship and relocation. Hybrid in Amsterdam.",
        location="Amsterdam",
    )
    a = score_job(plain, sample_prefs)
    b = score_job(visa, sample_prefs)
    assert a and b
    assert b.score > a.score


def test_match_jobs_sorts_by_score(sample_prefs):
    low = make_job(
        source_id="a",
        url="https://example.com/a",
        title="Backend developer",
        description="django",
        location="Remote",
        remote=True,
    )
    high = make_job(
        source_id="b",
        url="https://example.com/b",
        title="Python Software Engineer",
        description="python backend django visa sponsorship",
        location="Amsterdam, Netherlands",
        remote=True,
    )
    ordered = match_jobs([low, high], sample_prefs)
    assert [m.job.source_id for m in ordered] == ["b", "a"]


def test_old_job_is_dropped_and_counted(sample_prefs):
    sample_prefs.max_age_days = 14
    stale = make_job(posted_at=datetime.now(timezone.utc) - timedelta(days=30))
    stats = MatchStats()
    assert score_job(stale, sample_prefs, stats=stats) is None
    assert stats.too_old == 1


def test_recent_and_undated_jobs_survive_age_filter(sample_prefs):
    sample_prefs.max_age_days = 14
    recent = make_job(posted_at=datetime.now(timezone.utc) - timedelta(days=3))
    undated = make_job(source_id="2", posted_at=None)
    assert score_job(recent, sample_prefs) is not None
    assert score_job(undated, sample_prefs) is not None


def test_age_filter_disabled_with_zero(sample_prefs):
    sample_prefs.max_age_days = 0
    stale = make_job(posted_at=datetime.now(timezone.utc) - timedelta(days=400))
    assert score_job(stale, sample_prefs) is not None


def test_naive_posted_at_is_treated_as_utc(sample_prefs):
    sample_prefs.max_age_days = 14
    stale = make_job(posted_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30))
    assert score_job(stale, sample_prefs) is None


def test_title_exclude_drops_junior_roles(sample_prefs):
    sample_prefs.title_exclude = ["junior", "working student"]
    stats = MatchStats()
    job = make_job(title="Junior Python Software Engineer")
    assert score_job(job, sample_prefs, stats=stats) is None
    assert stats.rejected_title == 1
    assert score_job(make_job(title="Senior Python Engineer"), sample_prefs) is not None


def test_title_exclude_respects_word_boundaries(sample_prefs):
    sample_prefs.title_exclude = ["intern"]
    assert score_job(make_job(title="International Python Engineer"), sample_prefs) is not None


def test_title_include_requires_a_hit(sample_prefs):
    sample_prefs.title_include = ["engineer"]
    assert score_job(make_job(title="Python Developer"), sample_prefs) is None
    assert score_job(make_job(title="Python Engineer"), sample_prefs) is not None


def test_location_weights_come_from_prefs():
    base = {
        "include_keywords": ["python"],
        "locations": {"countries": ["Netherlands", "Germany"]},
    }
    default_prefs = prefs_from_dict(base)
    tuned_prefs = prefs_from_dict({**base, "location_weights": {"Netherlands": 20}})
    job = make_job(location="Amsterdam, Netherlands")
    assert tuned_prefs.location_weights == {"netherlands": 20}
    assert score_job(job, tuned_prefs).score - score_job(job, default_prefs).score == 14


def test_location_weight_uses_best_match_only():
    prefs = prefs_from_dict(
        {
            "include_keywords": ["python"],
            "locations": {"countries": ["Netherlands"]},
            "location_weights": {"Netherlands": 6, "Amsterdam": 2},
        }
    )
    job = make_job(location="Amsterdam, Netherlands")
    plain = prefs_from_dict(
        {
            "include_keywords": ["python"],
            "locations": {"countries": ["Netherlands"]},
            "location_weights": {"Netherlands": 6},
        }
    )
    assert score_job(job, prefs).score == score_job(job, plain).score


def test_score_weights_are_configurable():
    base = {"include_keywords": ["python"], "locations": {"countries": ["Netherlands"]}}
    prefs = prefs_from_dict({**base, "score_weights": {"title_hit": 100}})
    job = make_job(title="Python Engineer", location="Amsterdam")
    assert prefs.weight("title_hit") == 100
    assert prefs.weight("keyword_hit") == 3
    assert score_job(job, prefs).score > score_job(job, prefs_from_dict(base)).score


def test_visa_require_keeps_only_sponsoring_jobs(sample_prefs):
    sample_prefs.visa_require = True
    stats = MatchStats()
    silent = make_job(description="Python backend role in Amsterdam.")
    assert score_job(silent, sample_prefs, stats=stats) is None
    assert stats.rejected_visa == 1

    flagged = make_job(description="Python backend role.", visa_sponsorship=True)
    keyworded = make_job(description="Python backend with visa sponsorship.")
    assert score_job(flagged, sample_prefs) is not None
    assert score_job(keyworded, sample_prefs) is not None


def test_source_flagged_sponsorship_shows_in_reasons(sample_prefs):
    job = make_job(description="Python backend role.", visa_sponsorship=True)
    assert "visa:source-flagged" in score_job(job, sample_prefs).reasons


def test_match_jobs_with_stats_reports_drops(sample_prefs):
    sample_prefs.title_exclude = ["junior"]
    jobs = [
        make_job(source_id="1"),
        make_job(source_id="2", title="Junior Python Engineer"),
        make_job(source_id="3", posted_at=datetime.now(timezone.utc) - timedelta(days=90)),
        make_job(source_id="4", title="Python Engineer", location="Austin, Texas", remote=False),
    ]
    matches, stats = match_jobs_with_stats(jobs, sample_prefs)
    assert [m.job.source_id for m in matches] == ["1"]
    assert stats.rejected_title == 1
    assert stats.too_old == 1
    assert stats.rejected_location == 1


def test_country_for_location_buckets():
    assert country_for_location("Amsterdam, Netherlands") == "Netherlands"
    assert country_for_location("Berlin, DE") == "Germany"
    assert country_for_location("Anywhere in Europe") == "Europe"
    assert country_for_location("", remote=True) == "Remote"
    assert country_for_location("Worldwide", remote=True) == "Remote"
    assert country_for_location("Austin, Texas") == "Other"


def test_empty_include_keywords_allows_geo_match():
    prefs = prefs_from_dict(
        {
            "include_keywords": [],
            "locations": {"countries": ["Netherlands"]},
            "work_mode": {"remote": True, "onsite": True, "hybrid": True},
        }
    )
    job = make_job(title="Whatever", description="Hello", location="Utrecht, Netherlands")
    assert score_job(job, prefs) is not None
