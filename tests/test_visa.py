from __future__ import annotations

import pytest

from opportunities_abroad.matcher.engine import MatchStats, score_job
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.visa import SponsorRegister, has_hard_restriction, normalize_company

from tests.conftest import make_job

BASE = {
    "include_keywords": ["python"],
    "locations": {"countries": ["Netherlands"]},
    "visa_keywords": ["visa", "sponsorship", "relocation"],
}


def prefs(**overrides):
    return prefs_from_dict({**BASE, **overrides})


@pytest.mark.parametrize(
    "text",
    [
        "We do not offer visa sponsorship for this role.",
        "No visa sponsorship is available.",
        "We are unable to sponsor visas at this time.",
        "We cannot provide sponsorship.",
        "Visa sponsorship is not available for this position.",
        "This role does not support visa sponsorship.",
        "We are not able to offer sponsorship.",
        "Applicants must already have the right to work in the Netherlands.",
        "You must hold a valid work permit for Germany.",
        "Candidates must have existing work authorization.",
        "Candidates must be legally authorized to work without sponsorship.",
        "EU citizens only.",
        "EU/EEA nationals only, please.",
    ],
)
def test_hard_restrictions_are_detected(text):
    assert has_hard_restriction(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        None,
        "We offer visa sponsorship and relocation support.",
        "Visa sponsorship is available for the right candidate.",
        "We are happy to sponsor highly skilled migrants.",
        "We sponsor visas for international candidates.",
        "Relocation package and 30% ruling assistance provided.",
        "Sponsorship available for EU and non-EU applicants.",
        "We can provide visa sponsorship where needed.",
        "Backend engineer role in Amsterdam. Python, Django.",
    ],
)
def test_sponsoring_and_silent_postings_are_not_restricted(text):
    assert has_hard_restriction(text) is False


def test_a_refusal_never_outranks_silence():
    """The inversion this exists to fix: "we do not offer visa sponsorship"
    contains two visa keywords and used to score as evidence in favour."""
    refusal = make_job(
        description="Python role. We do not offer visa sponsorship.",
        location="Amsterdam",
        remote=False,
    )
    silent = make_job(
        source_id="2",
        url="https://example.com/2",
        description="Python role in our Amsterdam office.",
        location="Amsterdam",
        remote=False,
    )
    offered = make_job(
        source_id="3",
        url="https://example.com/3",
        description="Python role. We offer visa sponsorship and relocation.",
        location="Amsterdam",
        remote=False,
    )
    a, b, c = (score_job(j, prefs()) for j in (refusal, silent, offered))
    assert a.score < b.score < c.score
    assert "visa:restricted" in a.reasons
    assert not any(r.startswith("visa:visa") for r in a.reasons)


def test_restricted_posting_carries_a_deterministic_verdict():
    job = make_job(
        description="Python role. We cannot provide visa sponsorship.",
        location="Amsterdam",
        remote=False,
    )
    match = score_job(job, prefs())
    assert match.sponsorship == "no"
    assert "not available" in match.sponsorship_reason


def test_visa_require_drops_a_restricted_posting_even_with_keywords():
    job = make_job(
        description="Python role. Visa sponsorship is not available.",
        location="Amsterdam",
        remote=False,
    )
    stats = MatchStats()
    assert score_job(job, prefs(visa={"require": True}), stats=stats) is None
    assert stats.rejected_visa == 1


def test_restriction_overrides_a_source_sponsorship_flag():
    job = make_job(
        description="Python role. We do not offer visa sponsorship.",
        location="Amsterdam",
        remote=False,
        visa_sponsorship=True,
    )
    assert score_job(job, prefs(visa={"require": True})) is None


# --- sponsor register -------------------------------------------------------


def register() -> SponsorRegister:
    return SponsorRegister.from_lines(["Adyen N.V.", "Mollie B.V.", "ASML Netherlands B.V."])


def test_register_matches_across_legal_forms():
    reg = register()
    for name in ("Adyen", "adyen n.v.", "ADYEN NV", "Mollie", "ASML"):
        assert reg.contains(name) is True, name
    assert reg.contains("Globex") is False
    assert reg.contains("") is False
    assert reg.contains(None) is False


def test_register_boosts_and_explains():
    job = make_job(company="Adyen", description="Python role.", location="Amsterdam", remote=False)
    with_reg = score_job(job, prefs(), register=register())
    without = score_job(job, prefs())
    assert with_reg.score - without.score == 7
    assert "visa:sponsor-register" in with_reg.reasons


def test_register_membership_satisfies_visa_require():
    """A silent posting from a licensed sponsor is still worth seeing."""
    job = make_job(company="Mollie", description="Python role.", location="Amsterdam", remote=False)
    strict = prefs(visa={"require": True})
    assert score_job(job, strict) is None
    assert score_job(job, strict, register=register()) is not None


def test_register_does_not_rescue_an_explicit_refusal():
    job = make_job(
        company="Adyen",
        description="Python role. We do not offer visa sponsorship for this position.",
        location="Amsterdam",
        remote=False,
    )
    assert score_job(job, prefs(visa={"require": True}), register=register()) is None


@pytest.mark.parametrize(
    "a,b",
    [
        ("Adyen N.V.", "Adyen"),
        ("Mollie B.V.", "mollie"),
        ("Booking.com BV", "Booking.com"),
        ("Acme GmbH", "ACME"),
        ("Foo Holding Group", "foo"),
    ],
)
def test_company_normalisation(a, b):
    assert normalize_company(a) == normalize_company(b)


def test_distinct_companies_stay_distinct():
    assert normalize_company("Acme BV") != normalize_company("Globex BV")


def test_loading_a_register_file(tmp_path):
    path = tmp_path / "sponsors.txt"
    path.write_text("# Recognised sponsors\nAdyen N.V.\n\nMollie B.V.\n", encoding="utf-8")
    reg = SponsorRegister.load(path)
    assert len(reg) == 2
    assert reg.contains("Adyen") is True
    assert bool(reg) is True


def test_loading_a_csv_register(tmp_path):
    path = tmp_path / "sponsors.csv"
    path.write_text("Adyen N.V.,Amsterdam\nMollie B.V.,Amsterdam\n", encoding="utf-8")
    reg = SponsorRegister.load(path)
    assert reg.contains("Adyen") is True
    assert reg.contains("Amsterdam") is False


def test_missing_register_is_not_fatal(tmp_path):
    reg = SponsorRegister.load(tmp_path / "nope.txt")
    assert bool(reg) is False
    assert reg.contains("Adyen") is False


def test_no_register_configured():
    assert bool(SponsorRegister.load(None)) is False
