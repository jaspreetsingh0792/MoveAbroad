"""Read a seniority level out of a job title.

Excluding "junior" as a string is blunt: it cannot tell you what a posting
*is*, only what it is not, so "Engineer II" and "Head of Platform" both look
the same as a role you actually want. Classifying the level lets the level be
filtered on, reported, and shown in the digest.

Titles are inconsistent across companies, so an unrecognised title is
``UNKNOWN`` rather than a guess, and unknown levels are kept by default: it is
better to read one extra posting than to silently drop an oddly-titled role.
"""

from __future__ import annotations

import re

UNKNOWN = "unknown"

# Ordered least to most senior. Order matters for range filters.
LEVELS: tuple[str, ...] = (
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
    "executive",
)

# Checked most senior first, so "Senior Staff Engineer" reads as staff and
# "Head of Engineering" does not stop at the word "engineer".
_PATTERNS: tuple[tuple[str, str], ...] = (
    ("executive", r"\b(chief|cto|cio|vp|vice president|head of|director)\b"),
    ("lead", r"\b(lead|leader|team lead|tech lead|technical lead|manager)\b"),
    ("principal", r"\b(principal|distinguished|fellow|architect)\b"),
    ("staff", r"\b(staff|senior staff)\b"),
    ("senior", r"\b(senior|snr|sr|iii|iv|expert|experienced)\b"),
    ("intern", r"\b(intern|internship|working student|werkstudent|stagiair|stage)\b"),
    # Roman numerals: "Engineer I" is junior, "Engineer II" mid. Keep these
    # single-alternative so II never falls through to the junior branch.
    ("junior", r"\b(junior|jr|graduate|grad|trainee|apprentice|entry[\s-]?level|i)\b"),
    ("mid", r"\b(mid|medior|intermediate|ii)\b"),
)
_COMPILED = tuple((level, re.compile(pattern, re.IGNORECASE)) for level, pattern in _PATTERNS)


def classify(title: str | None) -> str:
    """Return a level from LEVELS, or UNKNOWN when the title does not say."""
    text = (title or "").strip()
    if not text:
        return UNKNOWN
    for level, pattern in _COMPILED:
        if pattern.search(text):
            return level
    return UNKNOWN


def is_allowed(level: str, allowed: list[str], keep_unknown: bool = True) -> bool:
    """Whether a classified level passes the configured filter."""
    if not allowed:
        return True
    if level == UNKNOWN:
        return keep_unknown
    return level in {a.lower().strip() for a in allowed}
