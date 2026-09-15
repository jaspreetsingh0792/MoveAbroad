from __future__ import annotations

import hashlib
import html
import re

_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://([^/?#]+)", re.IGNORECASE)
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


def url_host(url: str | None) -> str:
    """Canonical host for a URL: no scheme, credentials, port, or leading www."""
    if not url:
        return ""
    text = url.strip()
    match = _SCHEME_RE.match(text)
    authority = match.group(1) if match else text.split("/", 1)[0]
    host = authority.split("@")[-1].split(":", 1)[0].lower()
    return host[4:] if host.startswith("www.") else host


def normalize_identity(value: str | None) -> str:
    """Fold a company or title down to comparable words."""
    return _NON_ALNUM_RE.sub(" ", (value or "").lower()).strip()


def fingerprint(
    company: str | None,
    title: str | None,
    url: str | None,
    locale: str | None = "",
) -> str:
    """Identity for the same role reposted under different source ids.

    Scoped by host so two companies sharing a job title never collide, and by
    ``locale`` so one company advertising the same title in two places stays
    two openings. Callers pass a coarse locale (a country bucket rather than
    the raw location) so that "Amsterdam" and "Amsterdam, Netherlands" still
    collapse to one job.

    Empty when company or title is unknown, which callers treat as "no
    fingerprint" rather than a match-all.
    """
    normalized_company = normalize_identity(company)
    normalized_title = normalize_identity(title)
    if not normalized_company or not normalized_title:
        return ""
    seed = "|".join(
        (
            normalized_company,
            normalized_title,
            url_host(url),
            normalize_identity(locale),
        )
    )
    return hashlib.blake2s(seed.encode("utf-8"), digest_size=16).hexdigest()
