from __future__ import annotations

import re

from opportunities_abroad.models import Job, Match
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.textutil import strip_html

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
_ONSITE_HINT_RE = re.compile(
    r"\b(on[\s-]?site|in[\s-]?office|office[\s-]?based)\b",
    re.IGNORECASE,
)


def match_jobs(jobs: list[Job], prefs: Prefs) -> list[Match]:
    """Return all matching jobs, highest score first. Does not slice to max_jobs."""
    matches: list[Match] = []
    for job in jobs:
        result = score_job(job, prefs)
        if result is not None:
            matches.append(result)
    matches.sort(key=lambda m: (-m.score, m.job.title.lower()))
    return matches


def score_job(job: Job, prefs: Prefs) -> Match | None:
    haystack = strip_html(job.searchable_text).lower()
    title_l = job.title.lower()
    location_l = (job.location or "").lower()

    for kw in prefs.exclude_keywords:
        if kw and _phrase_in(haystack, kw):
            return None

    include_hits = _keyword_hits(prefs.include_keywords, haystack)
    if prefs.include_keywords and not include_hits:
        return None

    remote = _is_remote(job, haystack)
    hybrid = bool(_HYBRID_HINT_RE.search(haystack))

    if prefs.remote_only and not remote:
        return None

    mode_ok = False
    reasons: list[str] = []
    if remote and prefs.accept_remote:
        if _remote_location_allowed(job, prefs, haystack):
            mode_ok = True
            reasons.append("remote")
        elif not prefs.accept_onsite and not prefs.accept_hybrid:
            return None

    if hybrid and prefs.accept_hybrid and _geo_matches(job, prefs, location_l, haystack):
        mode_ok = True
        reasons.append("hybrid")

    if prefs.accept_onsite and not remote and _geo_matches(job, prefs, location_l, haystack):
        mode_ok = True
        if "hybrid" not in reasons:
            reasons.append("onsite")

    # Hybrid/onsite already handled. A remote job in a target city can also count as onsite-friendly.
    if (
        not mode_ok
        and prefs.accept_onsite
        and _geo_matches(job, prefs, location_l, location_l)
    ):
        mode_ok = True
        reasons.append("onsite")

    if not mode_ok:
        return None

    score = 0
    title_hits = _keyword_hits(prefs.include_keywords, title_l)
    score += 8 * len(title_hits)
    score += 3 * len(include_hits)
    if remote:
        score += 4
    visa_hits = _keyword_hits(prefs.visa_keywords, haystack)
    score += 5 * len(visa_hits)
    if any(token in location_l for token in ("netherlands", "amsterdam", "holland")):
        score += 6
    elif any(token in location_l for token in ("europe", "eu", "germany", "berlin")):
        score += 3

    if include_hits:
        reasons.append("keywords:" + ",".join(include_hits[:5]))
    if visa_hits:
        reasons.append("visa:" + ",".join(visa_hits[:3]))

    return Match(job=job, score=score, reasons=reasons)


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


def _geo_matches(job: Job, prefs: Prefs, location_l: str, haystack: str) -> bool:
    tokens = _geo_tokens(prefs)
    if not tokens:
        return True
    # Prefer the explicit location field; fall back to the full text.
    fields = [location_l, haystack]
    for token in tokens:
        pattern = rf"(?<!\w){re.escape(token)}(?!\w)"
        search_in = fields[0] if len(token) <= 2 else " ".join(fields)
        if re.search(pattern, search_in):
            return True
    return False


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
    if not location_l or location_l in {"remote", "worldwide", "anywhere", "global"}:
        return True
    if any(_phrase_in(location_l, p) or p in location_l for p in accept):
        return True
    # Remote role sitting in a target country/city is still useful (EU remote).
    if _geo_matches(job, prefs, location_l, location_l):
        return True
    return False
