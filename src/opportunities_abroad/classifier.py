from __future__ import annotations

import json
import logging
import os
import re

import httpx

from opportunities_abroad.http import make_client
from opportunities_abroad.models import Match
from opportunities_abroad.prefs import Prefs
from opportunities_abroad.store.sqlite import SqliteJobStore

logger = logging.getLogger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

MAX_DESCRIPTION_CHARS = 2500
MAX_TOKENS = 200
UNCLEAR = "unclear"
VERDICTS = frozenset({"yes", "no", UNCLEAR})

# Sponsorship language is as likely to sit in a closing "Immigration" or
# "Equal Opportunity" section as in the opening paragraphs, so the excerpt
# sent to the model is built around these rather than taken from the top.
VISA_TERMS = (
    "visa",
    "sponsor",
    "sponsorship",
    "work permit",
    "work authorisation",
    "work authorization",
    "right to work",
    "eligible to work",
    "authorised to work",
    "authorized to work",
    "relocation",
    "relocate",
    "blue card",
    "highly skilled migrant",
    "kennismigrant",
    "immigration",
    "30% ruling",
    "residence permit",
)
_VISA_TERMS_RE = re.compile("|".join(re.escape(t) for t in VISA_TERMS), re.IGNORECASE)
# Characters of context kept either side of a match.
VISA_WINDOW_CHARS = 400
# Opening text is always included: it usually carries the location and contract.
VISA_HEAD_CHARS = 700

SYSTEM_PROMPT = (
    "You read job postings and judge whether the employer will sponsor a work visa "
    "or offer relocation support for a candidate who needs a permit to work there. "
    'Answer with JSON only, no prose: {"sponsorship": "yes"|"no"|"unclear", '
    '"reason": "<one short line>"}. '
    'Use "yes" only when the posting says sponsorship or relocation is offered, '
    '"no" when it requires existing work authorisation, and "unclear" when it is silent.'
)


def api_key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def build_classifier(
    prefs: Prefs,
    store: SqliteJobStore,
    client: httpx.Client | None = None,
) -> VisaClassifier | None:
    """Return a classifier only when prefs ask for it and a key is present."""
    if not prefs.visa_classifier:
        return None
    if not api_key():
        logger.info("Visa classifier enabled in prefs but ANTHROPIC_API_KEY is not set; skipping")
        return None
    return VisaClassifier(prefs, store, client=client)


class VisaClassifier:
    """Asks the Anthropic Messages API whether a posting offers sponsorship.

    Every verdict is cached in SQLite by job key so repeat runs cost nothing.
    Any failure degrades to "unclear" and is never cached, so a transient
    outage does not poison the cache.
    """

    def __init__(
        self,
        prefs: Prefs,
        store: SqliteJobStore,
        client: httpx.Client | None = None,
        key: str | None = None,
    ) -> None:
        self.model = prefs.visa_classifier_model
        self.timeout = prefs.http_timeout_seconds
        self._store = store
        self._client = client
        self._key = key if key is not None else api_key()

    def annotate(self, matches: list[Match]) -> None:
        """Attach a sponsorship verdict and reason to each match, in place."""
        if not matches:
            return
        client = self._client or make_client(self.timeout)
        owns_client = self._client is None
        checked = 0
        try:
            for match in matches:
                cached = self._store.get_visa_verdict(match.job.key)
                if cached is not None:
                    match.sponsorship, match.sponsorship_reason = cached
                    continue
                verdict, reason, answered = self._ask(client, match)
                match.sponsorship = verdict
                match.sponsorship_reason = reason
                if answered:
                    checked += 1
                    self._store.save_visa_verdict(match.job.key, verdict, reason, self.model)
        finally:
            if owns_client:
                client.close()
        logger.info("Visa classifier: %s new verdict(s) over %s match(es)", checked, len(matches))

    def _ask(self, client: httpx.Client, match: Match) -> tuple[str, str, bool]:
        """Return (verdict, reason, answered). ``answered`` gates caching."""
        try:
            response = client.post(
                ANTHROPIC_MESSAGES_URL,
                headers={
                    "x-api-key": self._key,
                    "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": MAX_TOKENS,
                    "system": SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": _prompt(match)}],
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning("Visa classifier call failed for %s: %s", match.job.key, exc)
            return UNCLEAR, "classifier unavailable", False

        verdict, reason = _parse_verdict(_response_text(payload))
        if verdict is None:
            logger.warning("Visa classifier returned an unusable answer for %s", match.job.key)
            return UNCLEAR, "classifier returned no verdict", False
        return verdict, reason, True


def visa_excerpt(description: str | None, budget: int = MAX_DESCRIPTION_CHARS) -> str:
    """Excerpt the parts of a posting that bear on sponsorship.

    Truncating the first N characters loses the closing "Immigration" or
    "Equal Opportunity" paragraph where sponsorship is most often stated. This
    keeps the opening for context and adds a window around each visa-related
    mention, in document order, until the budget is spent.
    """
    text = (description or "").strip()
    if len(text) <= budget:
        return text

    head = min(VISA_HEAD_CHARS, budget)
    spans: list[tuple[int, int]] = [(0, head)]
    for hit in _VISA_TERMS_RE.finditer(text, head):
        start = max(head, hit.start() - VISA_WINDOW_CHARS)
        end = min(len(text), hit.end() + VISA_WINDOW_CHARS)
        spans.append((start, end))

    merged: list[list[int]] = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])

    pieces: list[str] = []
    used = 0
    for start, end in merged:
        if used >= budget:
            break
        chunk = text[start : min(end, start + (budget - used))]
        if not chunk:
            continue
        pieces.append(chunk)
        used += len(chunk)
    if len(pieces) == 1:
        return pieces[0]
    return " […] ".join(pieces)


def _prompt(match: Match) -> str:
    job = match.job
    description = visa_excerpt(job.description)
    return (
        f"Job title: {job.title}\n"
        f"Company: {job.company or 'unknown'}\n"
        f"Location: {job.location or 'unknown'}\n\n"
        f"Description:\n{description or '(no description provided)'}"
    )


def _response_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return ""
    return " ".join(
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict) and block.get("type") == "text"
    ).strip()


def _parse_verdict(text: str) -> tuple[str | None, str]:
    data = _extract_json(text)
    if not isinstance(data, dict):
        return None, ""
    verdict = str(data.get("sponsorship") or "").strip().lower()
    if verdict not in VERDICTS:
        return None, ""
    reason = " ".join(str(data.get("reason") or "").split())
    return verdict, reason


def _extract_json(text: str) -> object:
    """Pull the JSON object out of a reply that may be fenced or padded with prose."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        return json.loads(candidate[start : end + 1])
    except ValueError:
        return None
