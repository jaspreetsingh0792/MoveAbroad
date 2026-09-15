from __future__ import annotations

import html
import re

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
