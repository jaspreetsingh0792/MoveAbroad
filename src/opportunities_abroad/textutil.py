from __future__ import annotations

import hashlib
import html
import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TAG_RE = re.compile(r"<[^>]+>", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
# Tags become spaces, which strands punctuation that hugged a closing tag.
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?%)\]])")


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text).strip()


def normalize_url(url: str | None) -> str:
    if not url:
        return ""
    return url.strip().rstrip("/").split("?", 1)[0].lower()


def normalize_identity(value: str | None) -> str:
    """Fold a company or title down to comparable words."""
    return _NON_ALNUM_RE.sub(" ", (value or "").lower()).strip()


def fingerprint(company: str | None, title: str | None, locale: str | None = "") -> str:
    """Identity for the same role reposted under different source ids.

    Company, title and place only. The URL host is deliberately *not* part of
    this: an aggregator republishes a role under its own domain, which is the
    very case this exists to catch, so including the host would make the
    fingerprint agree only where the URL already does. Company is already in
    the seed, so it carries the "two firms, one job title" protection the host
    was there for.

    ``locale`` is a place key rather than a raw location, so the many ways
    sources spell one city still agree.

    Empty when company or title is unknown, which callers treat as "no
    fingerprint" rather than a match-all.
    """
    normalized_company = normalize_identity(company)
    normalized_title = normalize_identity(title)
    if not normalized_company or not normalized_title:
        return ""
    seed = "|".join((normalized_company, normalized_title, normalize_identity(locale)))
    return hashlib.blake2s(seed.encode("utf-8"), digest_size=16).hexdigest()
