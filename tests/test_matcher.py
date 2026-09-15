from __future__ import annotations

from opportunities_abroad.matcher.engine import match_jobs, score_job
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
