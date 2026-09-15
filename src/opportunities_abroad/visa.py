"""Deterministic sponsorship evidence: hard restrictions and sponsor registers.

Two signals that need no API call and no guessing.

A **hard restriction** is a posting stating outright that sponsorship is not
available. This has to win over everything else, including keyword scoring:
"we do not offer visa sponsorship" contains both "visa" and "sponsorship", so
without this it reads as *evidence in favour* — exactly backwards.

A **sponsor register** is an official list of employers licensed to sponsor,
such as the Dutch IND's public register of recognised sponsors. Membership is
a property of the company rather than of any one posting, which makes it far
stronger evidence than prose, and it is free to check.
"""

from __future__ import annotations

import csv
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from opportunities_abroad.textutil import normalize_identity

logger = logging.getLogger(__name__)

_SPONSOR = r"(?:visa\s+|work\s+)?sponsor(?:ship|ing|s)?"

_HARD_RESTRICTION_PATTERNS = (
    # Explicit refusals.
    rf"\bno\s+{_SPONSOR}\b",
    rf"\b(?:do(?:es)?\s+not|don'?t|will\s+not|won'?t)\s+(?:be\s+able\s+to\s+)?"
    rf"(?:provide|offer|support|consider)?\s*{_SPONSOR}",
    rf"\b(?:un(?:able)?|not\s+able)\s+to\s+(?:provide|offer|support)?\s*{_SPONSOR}",
    rf"\bcan(?:no|'?)t\s+(?:provide|offer|support)?\s*{_SPONSOR}",
    rf"\b{_SPONSOR}\s+is\s+not\s+(?:available|offered|provided|possible)\b",
    rf"\bwithout\s+(?:the\s+need\s+for\s+)?{_SPONSOR}\b",
    rf"\bnot\s+(?:currently\s+)?(?:be\s+)?(?:able\s+to\s+)?{_SPONSOR}",
    # Requirements that presuppose existing authorisation.
    r"\bmust\s+(?:already\s+)?(?:have|hold|possess)\b[^.]{0,60}"
    r"\b(?:right\s+to\s+work|work\s+authori[sz]ation|work\s+permit)\b",
    r"\b(?:existing|current|valid)\s+(?:right\s+to\s+work|work\s+authori[sz]ation)\b",
    r"\b(?:eu|eea)(?:/eea)?\s+(?:citizens?|nationals?|passport\s+holders?)\s+only\b",
    r"\bmust\s+be\s+(?:legally\s+)?(?:authori[sz]ed|eligible|entitled)\s+to\s+work\b"
    r"[^.]{0,60}\bwithout\b",
)
_HARD_RESTRICTION_RE = re.compile("|".join(_HARD_RESTRICTION_PATTERNS), re.IGNORECASE)

# Legal forms carry no identity: "Adyen N.V." and "Adyen" are one employer.
_LEGAL_SUFFIXES = (
    "nv",
    "bv",
    "cv",
    "vof",
    "gmbh",
    "ag",
    "sarl",
    "sas",
    "sa",
    "srl",
    "spa",
    "ab",
    "as",
    "oy",
    "aps",
    "plc",
    "ltd",
    "limited",
    "llc",
    "inc",
    "corp",
    "corporation",
    "holding",
    "holdings",
    "group",
    "international",
    "europe",
    "netherlands",
    "nederland",
    "technologies",
    "technology",
)


def has_hard_restriction(text: str | None) -> bool:
    """Whether a posting states outright that sponsorship is unavailable."""
    return bool(text) and _HARD_RESTRICTION_RE.search(text) is not None


def normalize_company(name: str | None) -> str:
    """Company name reduced to comparable words, without its legal form.

    Punctuated legal forms lose their dots on the way in, so "Adyen N.V."
    arrives as three words; runs of single letters are rejoined before the
    suffix is stripped, or "nv" would never be recognised.
    """
    words: list[str] = []
    initials: list[str] = []
    for word in normalize_identity(name).split():
        if len(word) == 1:
            initials.append(word)
            continue
        if initials:
            words.append("".join(initials))
            initials = []
        words.append(word)
    if initials:
        words.append("".join(initials))

    while words and words[-1] in _LEGAL_SUFFIXES:
        words.pop()
    return " ".join(words)


@dataclass(slots=True)
class SponsorRegister:
    """Employers known to hold a sponsorship licence.

    Sourced from an official register the user downloads; nothing is fetched at
    runtime, so the check is deterministic and works offline.
    """

    names: set[str] = field(default_factory=set)
    source: str = ""

    def __bool__(self) -> bool:
        return bool(self.names)

    def __len__(self) -> int:
        return len(self.names)

    def contains(self, company: str | None) -> bool:
        normalized = normalize_company(company)
        return bool(normalized) and normalized in self.names

    @classmethod
    def from_lines(cls, lines: list[str], source: str = "") -> SponsorRegister:
        names = {normalize_company(line) for line in lines}
        return cls(names={n for n in names if n}, source=source)

    @classmethod
    def load(cls, path: str | Path | None) -> SponsorRegister:
        """Read a register file, or return an empty one.

        Accepts a plain list (one employer per line) or a CSV whose first
        column holds the name. A missing or unreadable file is logged and
        treated as "no register", never as a reason to fail a run.
        """
        if not path:
            return cls()
        target = Path(path)
        if not target.exists():
            logger.warning("Sponsor register not found at %s; skipping the check", target)
            return cls()
        try:
            text = target.read_text(encoding="utf-8")
        except OSError:
            logger.exception("Could not read the sponsor register at %s", target)
            return cls()

        if target.suffix.lower() == ".csv":
            rows = csv.reader(text.splitlines())
            lines = [row[0] for row in rows if row]
        else:
            lines = text.splitlines()
        lines = [
            line for line in lines if line.strip() and not line.lstrip().startswith("#")
        ]
        register = cls.from_lines(lines, source=str(target))
        logger.info("Loaded %s sponsor register entries from %s", len(register), target)
        return register
