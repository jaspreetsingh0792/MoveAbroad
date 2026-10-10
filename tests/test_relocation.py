"""Jobs that someone living in India cannot actually take must not be sent."""

from __future__ import annotations

import pytest

from opportunities_abroad.matcher.engine import MatchStats, score_job
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.relocation import offers_move, posting_language, required_language

from tests.conftest import make_job

BASE = {
    "include_keywords": ["python"],
    "locations": {"countries": ["Netherlands", "Germany"]},
    "remote": {"accept_locations": ["Worldwide", "Anywhere", "Europe", "EU", "India", "APAC"]},
    "visa_keywords": ["visa", "sponsorship", "relocation"],
    "candidate": {"based_in": "India", "needs_visa": True, "languages": ["English"]},
}


def prefs(**candidate):
    data = {**BASE, "candidate": {**BASE["candidate"], **candidate}}
    return prefs_from_dict(data)


def judge(job, p=None):
    stats = MatchStats()
    match = score_job(job, p or prefs(), stats=stats)
    return match, stats


def remote_job(location, description="Python backend role."):
    return make_job(location=location, remote=True, description=description)


def onsite_job(description, location="Amsterdam, Netherlands"):
    return make_job(location=location, remote=False, description=description)


@pytest.mark.parametrize("location", ["Worldwide", "Anywhere", "India", "APAC", "Remote"])
def test_remote_jobs_open_to_india_are_kept(location):
    match, _ = judge(remote_job(location))
    assert match is not None
    assert match.highlight.startswith("Open ")


@pytest.mark.parametrize("location", ["Europe", "EU", "Germany", "Remote - Netherlands"])
def test_remote_jobs_for_residents_elsewhere_are_dropped(location):
    match, stats = judge(remote_job(location))
    assert match is None
    assert stats.rejected_relocation == 1


def test_remote_job_whose_text_limits_residence_is_dropped():
    job = remote_job("Worldwide", "Python role. You must be based in the United Kingdom.")
    assert judge(job)[0] is None


def test_timezone_wording_is_not_a_residence_limit():
    job = remote_job("Worldwide", "Python role. You must be located in a timezone near CET.")
    assert judge(job)[0] is not None


def test_eligible_regions_from_the_source_win_over_the_location_text():
    job = remote_job("Remote")
    job.extra["eligible_regions"] = ["United States", "Canada"]
    assert judge(job)[0] is None
    job.extra["eligible_regions"] = ["India", "Singapore"]
    match, _ = judge(job)
    assert match is not None and match.highlight == "Open to India"


def test_onsite_job_with_sponsorship_is_kept_and_says_why():
    match, _ = judge(onsite_job("Python engineer. We offer visa sponsorship and relocation."))
    assert match is not None
    assert match.highlight.startswith("Mentions visa")


def test_source_flag_is_the_highlight():
    job = onsite_job("Python engineer.")
    job.visa_sponsorship = True
    match, _ = judge(job)
    assert match.highlight == "Visa sponsorship offered"


@pytest.mark.parametrize(
    "description",
    [
        "Python engineer. We do not offer visa sponsorship.",
        "Python engineer. No relocation support.",
        "Python engineer. Local candidates only.",
        "Python engineer. You must already be living in the Netherlands.",
        "Python engineer. Security clearance required.",
        "Python engineer. Fluent German is required.",
        "Python engineer. Dutch (C1) is a must.",
    ],
)
def test_onsite_jobs_closed_to_movers_are_dropped(description):
    match, stats = judge(onsite_job(description))
    assert match is None
    assert stats.rejected_relocation == 1


def test_based_in_with_relocation_offer_is_not_local_only():
    job = onsite_job("Python engineer. You must be based in Amsterdam; we support relocation.")
    assert judge(job)[0] is not None


def test_language_as_a_plus_is_fine():
    job = onsite_job("Python engineer with visa sponsorship. German is a plus, not required.")
    assert judge(job)[0] is not None


def test_a_spoken_language_is_not_a_blocker():
    job = onsite_job("Python engineer with visa sponsorship. Fluent German required.")
    assert judge(job, prefs(languages=["English", "German"]))[0] is not None


def test_posting_written_in_german_is_dropped():
    text = (
        "Wir suchen einen Python Entwickler. Du hast Erfahrung mit Django und "
        "Kenntnisse in der Cloud. Bei uns arbeitest du mit einem tollen Team und "
        "wir bieten dir die Möglichkeit, für unsere Kunden zu entwickeln. Visa."
    )
    match, _ = judge(onsite_job(text, location="Berlin, Germany"))
    assert match is None
    assert posting_language(text.lower()) == "german"


def test_english_posting_with_a_few_foreign_words_stays_english():
    text = "We are hiring in Den Haag. Die-hard Python fans welcome. You will join the team."
    assert posting_language(text.lower()) == "english"


def test_require_visa_evidence_drops_silent_onsite_postings():
    silent = onsite_job("Python engineer building APIs.")
    assert judge(silent, prefs(require_visa_evidence=False))[0] is not None
    assert judge(silent, prefs(require_visa_evidence=True))[0] is None


def test_not_needing_a_visa_skips_the_visa_checks():
    job = onsite_job("Python engineer. We do not offer visa sponsorship.")
    assert judge(job, prefs(needs_visa=False))[0] is not None


def test_no_candidate_section_changes_nothing():
    data = {k: v for k, v in BASE.items() if k != "candidate"}
    job = remote_job("Europe")
    assert score_job(job, prefs_from_dict(data)) is not None


def test_polish_the_verb_is_not_the_language():
    assert required_language("you must polish the ui to excellent quality", {"english"}) is None


@pytest.mark.parametrize(
    "description",
    [
        "Python engineer. We sponsor visas.",
        "Python engineer. Relocation package included.",
        "Python engineer. We help you relocate.",
        "Python engineer. EU Blue Card eligible.",
    ],
)
def test_move_offers_count_as_evidence_without_a_matching_keyword(description):
    p = prefs_from_dict({**BASE, "visa_keywords": [], "candidate": {
        "based_in": "India", "require_visa_evidence": True}})
    match, _ = judge(onsite_job(description), p)
    assert match is not None
    assert match.highlight == "Offers visa or relocation help"


@pytest.mark.parametrize(
    "text",
    [
        "we cannot support visas for this role",
        "we don't offer visa support",
        "there is no relocation package",
    ],
)
def test_negated_offers_are_not_evidence(text):
    assert offers_move(text) is False
