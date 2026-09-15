from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from opportunities_abroad import seniority
from opportunities_abroad.models import Job, Match
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.textutil import strip_html
from opportunities_abroad.visa import SponsorRegister, has_hard_restriction

# Expand user-facing country names into tokens that commonly appear in job posts.
COUNTRY_ALIASES: dict[str, set[str]] = {
    "netherlands": {
        "netherlands",
        "holland",
        "nl",
        "the netherlands",
        "amsterdam",
        "rotterdam",
        "utrecht",
        "eindhoven",
        "the hague",
        "den haag",
        "haarlem",
        "groningen",
    },
    "germany": {
        "germany",
        "deutschland",
        "de",
        "berlin",
        "munich",
        "münchen",
        "hamburg",
        "frankfurt",
        "cologne",
        "köln",
        "stuttgart",
        "düsseldorf",
    },
    "belgium": {"belgium", "belgië", "belgie", "be", "brussels", "bruxelles", "antwerp", "ghent"},
    "austria": {"austria", "österreich", "at", "vienna", "wien"},
    "ireland": {"ireland", "ie", "dublin", "cork", "galway"},
    "france": {"france", "fr", "paris", "lyon", "lille", "nantes", "toulouse"},
    "spain": {"spain", "es", "madrid", "barcelona", "valencia", "seville"},
    "portugal": {"portugal", "pt", "lisbon", "lisboa", "porto"},
    "sweden": {"sweden", "se", "stockholm", "gothenburg", "göteborg", "malmö"},
    "denmark": {"denmark", "dk", "copenhagen", "københavn", "aarhus"},
    "finland": {"finland", "fi", "helsinki"},
    "norway": {"norway", "no", "oslo", "bergen"},
    "poland": {"poland", "pl", "warsaw", "warszawa", "krakow", "kraków", "wroclaw"},
    "czech republic": {"czech republic", "czechia", "cz", "prague", "praha"},
    "switzerland": {"switzerland", "ch", "zurich", "zürich", "geneva", "basel"},
    "luxembourg": {"luxembourg", "lu"},
    "estonia": {"estonia", "ee", "tallinn"},
    "eu": {"eu", "european union", "eea", "schengen"},
    "europe": {"europe", "european", "emea", "eea", "eu"},
}

# The country-level entries of COUNTRY_ALIASES: names and codes, as opposed to
# the city names living alongside them. Stripping these from a location leaves
# the specific place, which is what tells two openings apart.
COUNTRY_NAME_TOKENS: frozenset[str] = frozenset(
    {
        "netherlands", "the netherlands", "holland", "nl",
        "germany", "deutschland", "de",
        "belgium", "belgië", "belgie", "be",
        "austria", "österreich", "at",
        "ireland", "ie",
        "france", "fr",
        "spain", "es",
        "portugal", "pt",
        "sweden", "se",
        "denmark", "dk",
        "finland", "fi",
        "norway", "no",
        "poland", "pl",
        "czech republic", "czechia", "cz",
        "switzerland", "ch",
        "estonia", "ee",
        "eu", "european union", "europe", "european", "eea", "emea", "schengen",
        # Common non-target countries, so a US or UK posting keys on its city.
        "united states", "usa", "us", "united kingdom", "uk", "britain",
        "canada", "india", "brazil", "australia",
    }
)

_US_ONLY_RE = re.compile(
    r"\b("
    r"usa?\s*only|united states\s*only|u\.s\.?\s*only|"
    r"north america(?:n)?\s*only|canada\s*only|"
    r"(?:must|only)\s+be\s+(?:located\s+)?in\s+the\s+(?:usa|us|united states)|"
    r"authorized to work in the (?:usa|us|united states)"
    r")\b",
    re.IGNORECASE,
)

_REMOTE_HINT_RE = re.compile(
    r"\b(remote|work from home|wfh|distributed team)\b",
    re.IGNORECASE,
)
_HYBRID_HINT_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)

# Location strings often mix a work mode with a place ("Remote - Brazil").
# These carry no eligibility information on their own.
_WORK_MODE_WORDS = {
    "remote",
    "fully remote",
    "remote work",
    "work from home",
    "wfh",
    "hybrid",
    "onsite",
    "on site",
    "in office",
}
_ONSITE_HINT_RE = re.compile(
    r"\b(on[\s-]?site|in[\s-]?office|office[\s-]?based)\b",
    re.IGNORECASE,
)


@dataclass(slots=True)
class MatchStats:
    """Why jobs were dropped, so the digest can report more than a bare count."""

    too_old: int = 0
    rejected_location: int = 0
    rejected_title: int = 0
    rejected_seniority: int = 0
    rejected_visa: int = 0


def match_jobs(
    jobs: list[Job], prefs: Prefs, register: SponsorRegister | None = None
) -> list[Match]:
    """Return all matching jobs, highest score first. Does not slice to max_jobs."""
    matches, _ = match_jobs_with_stats(jobs, prefs, register)
    return matches


def match_jobs_with_stats(
    jobs: list[Job], prefs: Prefs, register: SponsorRegister | None = None
) -> tuple[list[Match], MatchStats]:
    """Match every job and report why the rest were dropped."""
    stats = MatchStats()
    matches: list[Match] = []
    for job in jobs:
        result = score_job(job, prefs, stats=stats, register=register)
        if result is not None:
            matches.append(result)
    matches.sort(key=lambda m: (-m.score, m.job.title.lower()))
    return matches, stats


def score_job(
    job: Job,
    prefs: Prefs,
    *,
    stats: MatchStats | None = None,
    register: SponsorRegister | None = None,
) -> Match | None:
    haystack = strip_html(job.searchable_text).lower()
    title_l = job.title.lower()
    location_l = (job.location or "").lower()

    if _is_too_old(job, prefs.max_age_days):
        _count(stats, "too_old")
        return None

    for kw in prefs.exclude_keywords:
        if kw and _phrase_in(haystack, kw):
            return None

    if _keyword_hits(prefs.title_exclude, title_l):
        _count(stats, "rejected_title")
        return None
    if prefs.title_include and not _keyword_hits(prefs.title_include, title_l):
        _count(stats, "rejected_title")
        return None

    level = seniority.classify(job.title)
    if not seniority.is_allowed(level, prefs.seniority_allow, prefs.seniority_keep_unknown):
        _count(stats, "rejected_seniority")
        return None

    include_hits = _keyword_hits(prefs.include_keywords, haystack)
    if prefs.include_keywords and not include_hits:
        return None

    # Hard restrictions win. "We do not offer visa sponsorship" contains both
    # visa keywords, so without this it would read as evidence in favour.
    restricted = has_hard_restriction(haystack)
    visa_hits = [] if restricted else _keyword_hits(prefs.visa_keywords, haystack)
    on_register = bool(register and register.contains(job.company))
    sponsorship_likely = not restricted and (
        job.visa_sponsorship is True or on_register or bool(visa_hits)
    )
    if prefs.visa_require and not sponsorship_likely:
        _count(stats, "rejected_visa")
        return None

    remote = _is_remote(job, haystack)
    hybrid = bool(_HYBRID_HINT_RE.search(haystack))

    if prefs.remote_only and not remote:
        _count(stats, "rejected_location")
        return None

    mode_ok = False
    reasons: list[str] = []
    if remote and prefs.accept_remote:
        if _remote_location_allowed(job, prefs, haystack):
            mode_ok = True
            reasons.append("remote")
        elif not prefs.accept_onsite and not prefs.accept_hybrid:
            _count(stats, "rejected_location")
            return None

    if hybrid and prefs.accept_hybrid and _geo_matches(prefs, location_l):
        mode_ok = True
        reasons.append("hybrid")

    if prefs.accept_onsite and not remote and _geo_matches(prefs, location_l):
        mode_ok = True
        if "hybrid" not in reasons:
            reasons.append("onsite")

    # A remote job sitting in a target city still counts as onsite-friendly.
    if not mode_ok and prefs.accept_onsite and _geo_matches(prefs, location_l):
        mode_ok = True
        reasons.append("onsite")

    if not mode_ok:
        _count(stats, "rejected_location")
        return None

    title_hits = _keyword_hits(prefs.include_keywords, title_l)
    score = prefs.weight("title_hit") * prefs.scored_hits("title_hit", len(title_hits))
    score += prefs.weight("keyword_hit") * prefs.scored_hits("keyword_hit", len(include_hits))
    if remote:
        score += prefs.weight("remote")
    score += prefs.weight("visa_hit") * prefs.scored_hits("visa_hit", len(visa_hits))
    if on_register:
        score += prefs.weight("sponsor_register")
    if restricted:
        # Not dropped unless visa.require says so, but it must never outrank a
        # posting that simply stays silent.
        score += prefs.weight("visa_restricted")
    score += location_bonus(location_l, prefs.location_weights)

    if include_hits:
        reasons.append("keywords:" + ",".join(include_hits[:5]))
    if on_register:
        reasons.append("visa:sponsor-register")
    if restricted:
        reasons.append("visa:restricted")
    elif visa_hits:
        reasons.append("visa:" + ",".join(visa_hits[:3]))
    elif job.visa_sponsorship is True:
        reasons.append("visa:source-flagged")

    match = Match(job=job, score=score, reasons=reasons, seniority=level)
    if restricted:
        # Deterministic evidence, so the classifier has nothing to add.
        match.sponsorship = "no"
        match.sponsorship_reason = "Posting states sponsorship is not available."
    return match


def location_bonus(location_l: str, weights: dict[str, int]) -> int:
    """Best single weight whose country/city tokens appear in the location.

    Only the strongest match counts, so a city weight does not stack on top of
    its country's.
    """
    best = 0
    for name, weight in weights.items():
        for token in _weight_tokens(name):
            if _phrase_in(location_l, token):
                best = max(best, weight)
                break
    return best


def country_for_location(location: str, remote: bool = False) -> str:
    """Bucket a job for the digest: a country name, then Europe, Remote, or Other."""
    location_l = (location or "").lower()
    segments = _location_segments(location_l)
    generic = {"eu", "europe"}
    for country, aliases in COUNTRY_ALIASES.items():
        if country in generic:
            continue
        for alias in aliases:
            # Two-letter aliases are too noisy inside prose; require a whole segment.
            if len(alias) <= 2:
                if alias in segments:
                    return country.title()
            elif _phrase_in(location_l, alias):
                return country.title()
    for alias in COUNTRY_ALIASES["europe"] | COUNTRY_ALIASES["eu"]:
        if len(alias) > 2 and _phrase_in(location_l, alias):
            return "Europe"
    if remote:
        return "Remote"
    return "Other"


def place_key(location: str, remote: bool = False) -> str:
    """The most specific place a posting names, for dedupe identity.

    Country names are stripped, so "Amsterdam" and "Amsterdam, Netherlands"
    agree while Amsterdam and Rotterdam stay apart. When only a country is
    named there is nothing finer to key on, so the country bucket stands in.

    Erring towards "different" here is deliberate: a duplicate email costs a
    glance, a swallowed opening costs an application.
    """
    location_l = (location or "").lower()
    named = _location_segments(location_l) - COUNTRY_NAME_TOKENS - _WORK_MODE_WORDS
    if named:
        return " ".join(sorted(named))
    return country_for_location(location, remote=remote)


def _weight_tokens(name: str) -> set[str]:
    key = name.lower().strip()
    return COUNTRY_ALIASES.get(key, {key}) if key else set()


def _count(stats: MatchStats | None, field_name: str) -> None:
    if stats is not None:
        setattr(stats, field_name, getattr(stats, field_name) + 1)


def _is_too_old(job: Job, max_age_days: int) -> bool:
    """Only drop jobs whose age is actually known; undated postings pass through."""
    if max_age_days <= 0 or job.posted_at is None:
        return False
    posted = job.posted_at
    if posted.tzinfo is None:
        posted = posted.replace(tzinfo=timezone.utc)
    return posted < datetime.now(timezone.utc) - timedelta(days=max_age_days)


def _phrase_in(text: str, phrase: str) -> bool:
    """Whole-phrase match so 'intern' does not hit 'international'."""
    token = phrase.lower().strip()
    if not token:
        return False
    return re.search(rf"(?<!\w){re.escape(token)}(?!\w)", text) is not None


def _keyword_hits(keywords: list[str], text: str) -> list[str]:
    hits: list[str] = []
    seen: set[str] = set()
    for kw in keywords:
        k = kw.lower().strip()
        if not k or k in seen:
            continue
        if _phrase_in(text, k):
            hits.append(kw)
            seen.add(k)
    return hits


def _is_remote(job: Job, haystack: str) -> bool:
    if job.remote is True:
        return True
    return bool(_REMOTE_HINT_RE.search(job.location or "") or _REMOTE_HINT_RE.search(haystack))


def _geo_tokens(prefs: Prefs) -> set[str]:
    tokens: set[str] = set()
    for country in prefs.countries:
        key = country.lower().strip()
        tokens.add(key)
        tokens.update(COUNTRY_ALIASES.get(key, set()))
    for city in prefs.cities:
        tokens.add(city.lower().strip())
    return {t for t in tokens if t}


def _geo_matches(prefs: Prefs, location_l: str) -> bool:
    """Whether a job is physically in a target place.

    Only ``job.location`` is consulted. Description text is deliberately
    excluded: a posting for Austin that mentions colleagues in Amsterdam is
    not an Amsterdam job, and geography here is a hard filter. Remote-policy
    hints still read the description — that is a different question.
    """
    tokens = _geo_tokens(prefs)
    if not tokens:
        return True
    if not location_l:
        return False
    segments = _location_segments(location_l)
    for token in tokens:
        # Two-letter codes must stand alone as a segment, or "Rio de Janeiro"
        # would read as Germany.
        if len(token) <= 2:
            if token in segments:
                return True
        elif _phrase_in(location_l, token):
            return True
    return False


def _location_segments(location_l: str) -> set[str]:
    return {s.strip() for s in re.split(r"[,/|()\-–—]", location_l) if s.strip()}


def _remote_location_allowed(job: Job, prefs: Prefs, haystack: str) -> bool:
    location_l = (job.location or "").lower()
    blob = f"{location_l} {haystack}"

    geo = _geo_tokens(prefs)
    us_targeted = any(
        t in geo
        for t in ("united states", "usa", "us", "canada", "united kingdom", "uk", "britain")
    )
    if not us_targeted and _US_ONLY_RE.search(location_l):
        return False
    if not us_targeted and _US_ONLY_RE.search(blob[:800]):
        return False

    for phrase in prefs.remote_reject_locations:
        p = phrase.lower().strip()
        if p and p in location_l:
            if p in geo or any(t in p.split() for t in geo):
                continue
            return False

    accept = [p.lower().strip() for p in prefs.remote_accept_locations if p.strip()]
    if not accept:
        return True
    if not location_l:
        return True

    # "Remote" on its own says nothing about eligibility, but "Remote - Brazil"
    # names a requirement. Judge the parts that are not just a work-mode word.
    named_places = _location_segments(location_l) - _WORK_MODE_WORDS
    if not named_places:
        return True
    for place in named_places:
        if any(place == p or _phrase_in(place, p) for p in accept):
            return True
        # Remote role sitting in a target country/city is still useful (EU remote).
        if _geo_matches(prefs, place):
            return True
    return False
