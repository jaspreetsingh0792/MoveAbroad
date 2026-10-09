"""Can someone living in ``candidate.based_in`` actually take this job?

Matching on skills and target country is not enough for a move abroad. A
Python role in Amsterdam is no use to an engineer in India if the posting
wants Dutch speakers, only considers people already in the EU, or is a remote
role open to EU residents only. This module answers that question with
deterministic text rules, no API call.

A job is workable from home when either:

* it is **remote and open to the candidate's country** (worldwide, APAC, Asia,
  or the country itself), and the description does not quietly restrict
  residence elsewhere; or
* it is a **move**: the role is abroad and, when the candidate needs a visa,
  the posting gives evidence of sponsorship or relocation support and nothing
  ruling it out (local candidates only, citizenship or clearance, a language
  the candidate does not speak).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from opportunities_abroad.models import Job
from opportunities_abroad.prefs import Prefs

# Places that, named as a remote job's eligible region, include the candidate.
_OPEN_EVERYWHERE = {
    "worldwide",
    "anywhere",
    "global",
    "globally",
    "international",
    "anywhere in the world",
    "remote",
    "fully remote",
    "100% remote",
    "work from anywhere",
}

_HOME_REGIONS: dict[str, set[str]] = {
    "india": {
        "india",
        "asia",
        "south asia",
        "apac",
        "asia pacific",
        "asia-pacific",
        "emea & apac",
        "bangalore",
        "bengaluru",
        "hyderabad",
        "pune",
        "mumbai",
        "delhi",
        "new delhi",
        "chennai",
        "gurgaon",
        "gurugram",
        "noida",
        "kolkata",
        "ahmedabad",
        "kochi",
        "jaipur",
        "chandigarh",
    },
}

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

# Languages a posting may require, with the words that name them in English
# and in the language itself.
_LANGUAGES: dict[str, tuple[str, ...]] = {
    "german": ("german", "deutsch", "deutschkenntnisse"),
    "dutch": ("dutch", "nederlands", "flemish"),
    "french": ("french", "français", "francais"),
    "spanish": ("spanish", "español", "espanol", "castellano"),
    "portuguese": ("portuguese", "português", "portugues"),
    "italian": ("italian", "italiano"),
    "swedish": ("swedish", "svenska"),
    "danish": ("danish", "dansk"),
    "norwegian": ("norwegian", "norsk"),
    "finnish": ("finnish", "suomi"),
    # Bare "polish" is also an English verb, so only unambiguous phrasings.
    "polish": ("polski", "polish language", "polish-speaking", "fluent polish"),
    "czech": ("czech", "čeština", "cestina"),
    "japanese": ("japanese",),
    "mandarin": ("mandarin",),
}
_REQUIRED_WORDS = re.compile(
    r"\b(fluent|fluency|fluently|native|mother tongue|required|requirement|must|mandatory|"
    r"essential|c1|c2|business[- ]level|business fluent|professional working|proficien\w*|"
    r"excellent|verhandlungssicher|fließend|fliessend|vloeiend)\b"
)
_SOFT_WORDS = re.compile(
    r"\b(plus|nice to have|nice-to-have|advantage|advantageous|bonus|beneficial|preferred|"
    r"preferably|ideally|not required|not necessary|no need|not needed|optional|"
    r"learn|learning|lessons|courses?|help you|support you|asset|helpful|welcome)\b"
)

# Function words that only occur in running text of that language. Postings
# written in German or Dutch almost always want a speaker of it.
_STOPWORDS: dict[str, frozenset[str]] = {
    "english": frozenset(
        "the and you we with for our your are will this that have from team".split()
    ),
    "german": frozenset(
        "und der die das wir sie mit für ist nicht eine einen bei oder unser unsere "
        "du dich dein deine ihre erfahrung kenntnisse auf zu".split()
    ),
    "dutch": frozenset(
        "het een wij jij je jouw voor met van naar zijn ervaring bij ons onze niet "
        "wat ook deze".split()
    ),
    "french": frozenset(
        "et le la les des nous vous pour avec une dans sur est votre notre expérience".split()
    ),
    "spanish": frozenset(
        "y el los las del nosotros para con una en es tu tus nuestro nuestra experiencia".split()
    ),
}
_WORD_RE = re.compile(r"[a-zà-ÿäöüß]+")

_CLEARANCE_RE = re.compile(
    r"\b(?:security|sc|dv|nato|government|top secret|secret)\s+clearance\b"
    r"|\bclearance\s+(?:is\s+)?required\b"
    r"|\bcitizenship\s+(?:is\s+)?required\b"
    r"|\bmust\s+(?:be|hold)\s+(?:an?\s+)?(?:[a-z]+\s+){0,2}(?:citizen|citizenship|national)\b"
    r"|\b(?:citizens?|nationals?)\s+only\b"
)

# Sentences that keep the role for people already there. A sentence that also
# offers relocation ("based in Berlin or willing to relocate") is not one.
_LOCAL_ONLY_RE = re.compile(
    r"\bno\s+relocation\b"
    r"|\brelocation\s+(?:is\s+)?(?:not|cannot\s+be)\s+(?:offered|provided|available|"
    r"supported|possible|covered)\b"
    r"|\b(?:unable|not\s+able)\s+to\s+(?:offer|provide|support)\s+relocation\b"
    r"|\blocal\s+(?:candidates|applicants|residents)\s+only\b"
    r"|\bonly\s+(?:consider|accept|considering|accepting)\s+(?:local|eu[- ]based|"
    r"in[- ]country)\s+(?:candidates|applicants)\b"
    r"|\bmust\s+(?:already\s+|currently\s+)?(?:be\s+)?(?:based|located|living|residing|reside|"
    r"live|resident)\s+in\b"
    r"|\b(?:must|need\s+to|should)\s+(?:already\s+)?(?:live|reside)\s+(?:in|within)\b"
)
_RELOCATION_OFFER_RE = re.compile(r"\brelocat\w*|\bvisa\b|\bsponsor\w*")

# "You must be based in Germany" style limits inside a remote posting.
_RESIDENCY_RE = re.compile(
    r"\b(?:must|need\s+to|needs\s+to|should|required\s+to)\s+(?:already\s+|currently\s+)?"
    r"(?:be\s+)?(?:based|located|living|residing|reside|live|resident)\s+(?:in|within)\s+"
    r"(?:the\s+)?([a-z][a-z .&/-]{1,40})"
    r"|\bopen\s+(?:only\s+)?to\s+(?:candidates|applicants|residents|people)\s+"
    r"(?:based\s+|located\s+|living\s+)?(?:in|from)\s+(?:the\s+)?([a-z][a-z .&/-]{1,40})"
    r"|\b([a-z][a-z ]{1,25})\s+(?:residents|based\s+candidates)\s+only\b"
)
# Phrasings that offer a move outright, whatever the user's visa_keywords say.
# "We sponsor visas" would otherwise slip past a keyword list holding "visa".
_MOVE_OFFER_RE = re.compile(
    r"\b(?:sponsor|sponsors|sponsoring|support|supports)\s+(?:your\s+|work\s+)?visas?\b"
    r"|\bvisa\s+(?:sponsorship|support|assistance|help)\b"
    r"|\brelocation\s+(?:package|support|assistance|bonus|allowance|budget|help)\b"
    r"|\b(?:help|support|assist)\s+(?:you\s+)?(?:with\s+)?(?:your\s+)?relocat\w*"
    r"|\b(?:eu\s+)?blue\s+card\b|\bkennismigrant\b|\bhighly\s+skilled\s+migrant\b"
)
_NEGATION_RE = re.compile(r"\b(?:no|not|never|cannot|unable|without)\b|n't\b|n’t\b")
_SENTENCE_SPLIT_RE = re.compile(r"[.;!?\n•·]+")


@dataclass(slots=True)
class Eligibility:
    ok: bool
    # Why a job was dropped, for logs and tests.
    reason: str = ""
    # Why a kept job is workable from home, for the digest: "Open to India"
    # for a remote role, or the visa evidence for a move.
    highlight: str = ""


def assess(
    job: Job,
    haystack: str,
    prefs: Prefs,
    *,
    remote: bool,
    sponsorship_likely: bool,
    restricted: bool,
    on_register: bool,
    visa_hits: list[str],
) -> Eligibility:
    """Decide whether a job is workable from ``prefs.candidate_based_in``.

    ``haystack`` is the job's lowercased searchable text. Everything is a no-op
    when the candidate's country is not configured.
    """
    home = prefs.candidate_based_in.strip()
    if not home:
        return Eligibility(True)

    spoken = {lang.lower().strip() for lang in prefs.candidate_languages} or {"english"}
    written_in = posting_language(haystack)
    if written_in not in spoken:
        return Eligibility(False, reason=f"posting written in {written_in.title()}")
    needed = required_language(haystack, spoken)
    if needed:
        return Eligibility(False, reason=f"requires {needed.title()}")
    if _CLEARANCE_RE.search(haystack):
        return Eligibility(False, reason="citizenship or security clearance required")

    home_tokens = _home_tokens(home)
    places = eligible_places(job)
    if remote:
        open_to_home = not places or any(_place_includes(p, home_tokens) for p in places)
        elsewhere = residency_elsewhere(haystack, home_tokens)
        if open_to_home and not elsewhere:
            if not places or all(p in _OPEN_EVERYWHERE for p in places):
                return Eligibility(True, highlight="Open worldwide")
            return Eligibility(True, highlight=f"Open to {home.title()}")

    if not prefs.candidate_needs_visa:
        return Eligibility(True, highlight=_evidence_highlight(job, on_register, visa_hits))

    if restricted:
        return Eligibility(False, reason="posting rules out visa sponsorship")
    if _local_only(haystack):
        return Eligibility(False, reason="local candidates only / no relocation")
    if remote and not sponsorship_likely:
        limit = ", ".join(places) if places else "another country"
        return Eligibility(False, reason=f"remote, but only for people in {limit}")
    if prefs.candidate_require_evidence and not sponsorship_likely:
        return Eligibility(False, reason="no visa sponsorship or relocation support mentioned")
    return Eligibility(True, highlight=_evidence_highlight(job, on_register, visa_hits))


def offers_move(haystack: str) -> bool:
    """Whether a posting offers visa or relocation help in so many words.

    "We cannot support visas" is not an offer, so a negation just before the
    phrase disqualifies that occurrence.
    """
    for match in _MOVE_OFFER_RE.finditer(haystack):
        before = haystack[max(0, match.start() - 30) : match.start()]
        if not _NEGATION_RE.search(before):
            return True
    return False


def eligible_places(job: Job) -> list[str]:
    """Where a remote job says its hires may live, lowercased.

    Sources that publish an explicit list (Himalayas, Jobicy) put it in
    ``extra["eligible_regions"]``; otherwise the location field is read, minus
    words that only describe a work mode.
    """
    regions = job.extra.get("eligible_regions") if isinstance(job.extra, dict) else None
    if isinstance(regions, list) and regions:
        return [str(r).lower().strip() for r in regions if str(r).strip()]
    location_l = (job.location or "").lower()
    segments = {s.strip() for s in re.split(r"[,/|()\-–—;]", location_l) if s.strip()}
    named = segments - _WORK_MODE_WORDS
    return sorted(named)


def posting_language(haystack: str) -> str:
    """The language most of the posting is written in, by function-word counts."""
    counts = dict.fromkeys(_STOPWORDS, 0)
    for word in _WORD_RE.findall(haystack[:6000]):
        for lang, words in _STOPWORDS.items():
            if word in words:
                counts[lang] += 1
    best = max(counts, key=lambda lang: counts[lang])
    # A few stray words ("die", "en") in an English posting must not flip it.
    if best != "english" and counts[best] >= 8 and counts[best] > 1.5 * counts["english"]:
        return best
    return "english"


def required_language(haystack: str, spoken: set[str]) -> str | None:
    """A language the posting requires that the candidate does not speak."""
    for sentence in _SENTENCE_SPLIT_RE.split(haystack):
        if not _REQUIRED_WORDS.search(sentence) or _SOFT_WORDS.search(sentence):
            continue
        for lang, names in _LANGUAGES.items():
            if lang in spoken:
                continue
            if any(re.search(rf"(?<!\w){re.escape(n)}(?!\w)", sentence) for n in names):
                return lang
    return None


def residency_elsewhere(haystack: str, home_tokens: set[str]) -> bool:
    """Whether a posting limits where hires live to somewhere other than home."""
    for match in _RESIDENCY_RE.finditer(haystack):
        place = next((g for g in match.groups() if g), "").strip()
        if not place:
            continue
        if _place_includes(place, home_tokens):
            continue
        # "must be based in a timezone overlapping CET" says nothing about country.
        if re.match(r"(?:a|an|one|your|their|our)\b", place) or "time" in place:
            continue
        return True
    return False


def _local_only(haystack: str) -> bool:
    """A "be based here" requirement, unless the posting also offers relocation.

    "You must be based in Amsterdam; we support relocation" is open to movers,
    so a relocation or visa offer anywhere in the posting outweighs it.
    """
    sentences = _SENTENCE_SPLIT_RE.split(haystack)
    if any(_offers_relocation(sentence) for sentence in sentences):
        return False
    return any(_LOCAL_ONLY_RE.search(sentence) for sentence in sentences)


def _offers_relocation(sentence: str) -> bool:
    if not _RELOCATION_OFFER_RE.search(sentence):
        return False
    return not re.search(r"\bno\s+relocation\b|\brelocation\s+(?:is\s+)?not\b", sentence)


def _home_tokens(home: str) -> set[str]:
    key = home.lower().strip()
    return {key, *_HOME_REGIONS.get(key, set())}


def _place_includes(place: str, home_tokens: set[str]) -> bool:
    place = place.lower().strip()
    if place in _OPEN_EVERYWHERE:
        return True
    return any(
        re.search(rf"(?<!\w){re.escape(token)}(?!\w)", place) for token in home_tokens
    )


def _evidence_highlight(job: Job, on_register: bool, visa_hits: list[str]) -> str:
    if on_register:
        return "Employer is a licensed visa sponsor"
    if job.visa_sponsorship is True:
        return "Visa sponsorship offered"
    if visa_hits:
        return "Mentions " + ", ".join(visa_hits[:2])
    return "Offers visa or relocation help"
