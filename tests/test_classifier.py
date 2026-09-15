from __future__ import annotations

import json

import httpx
import pytest

from opportunities_abroad.classifier import UNCLEAR, VisaClassifier, build_classifier
from opportunities_abroad.models import Match
from opportunities_abroad.prefs import prefs_from_dict
from opportunities_abroad.store.sqlite import SqliteJobStore

from tests.conftest import make_job


@pytest.fixture
def classifier_prefs():
    return prefs_from_dict({"visa": {"classifier": True}})


@pytest.fixture
def store(tmp_path):
    with SqliteJobStore(tmp_path / "seen.db") as opened:
        yield opened


def reply(text: str, status: int = 200) -> httpx.Client:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status != 200:
            return httpx.Response(status, json={"error": "nope"})
        return httpx.Response(200, json={"content": [{"type": "text", "text": text}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    client.calls = calls  # type: ignore[attr-defined]
    return client


def a_match(**overrides) -> Match:
    return Match(job=make_job(**overrides), score=10, reasons=["remote"])


def test_verdict_is_stored_on_the_match(classifier_prefs, store):
    body = json.dumps({"sponsorship": "yes", "reason": "Offers relocation to Amsterdam."})
    with reply(body) as client:
        match = a_match()
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([match])

    assert match.sponsorship == "yes"
    assert match.sponsorship_reason == "Offers relocation to Amsterdam."


def test_request_shape_and_truncation(classifier_prefs, store):
    body = json.dumps({"sponsorship": "no", "reason": "EU work authorisation required."})
    with reply(body) as client:
        match = a_match(description="x" * 5000)
        VisaClassifier(classifier_prefs, store, client=client, key="secret").annotate([match])
        request = client.calls[0]  # type: ignore[attr-defined]

    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "secret"
    assert request.headers["anthropic-version"] == "2023-06-01"

    sent = json.loads(request.content)
    assert sent["model"] == "claude-sonnet-4-6"
    prompt = sent["messages"][0]["content"]
    assert prompt.count("x") == 2500
    assert "Python Software Engineer" in prompt


def test_verdicts_are_cached_between_runs(classifier_prefs, store):
    body = json.dumps({"sponsorship": "yes", "reason": "Sponsors highly skilled migrants."})
    with reply(body) as client:
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([a_match()])
        assert len(client.calls) == 1  # type: ignore[attr-defined]

    with reply(body) as client:
        second = a_match()
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([second])
        assert client.calls == []  # type: ignore[attr-defined]

    assert second.sponsorship == "yes"
    assert second.sponsorship_reason == "Sponsors highly skilled migrants."


def test_api_error_is_unclear_and_not_cached(classifier_prefs, store):
    with reply("", status=500) as client:
        match = a_match()
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([match])

    assert match.sponsorship == UNCLEAR
    assert match.sponsorship_reason == "classifier unavailable"
    assert store.get_visa_verdict(match.job.key) is None


def test_unparseable_answer_is_unclear_and_not_cached(classifier_prefs, store):
    with reply("I am not going to answer that.") as client:
        match = a_match()
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([match])

    assert match.sponsorship == UNCLEAR
    assert store.get_visa_verdict(match.job.key) is None


def test_unknown_verdict_value_is_rejected(classifier_prefs, store):
    with reply(json.dumps({"sponsorship": "maybe", "reason": "who knows"})) as client:
        match = a_match()
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([match])

    assert match.sponsorship == UNCLEAR
    assert store.get_visa_verdict(match.job.key) is None


def test_fenced_json_is_accepted(classifier_prefs, store):
    fenced = '```json\n{"sponsorship": "unclear", "reason": "Posting is silent."}\n```'
    with reply(fenced) as client:
        match = a_match()
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([match])

    assert match.sponsorship == UNCLEAR
    assert match.sponsorship_reason == "Posting is silent."
    assert store.get_visa_verdict(match.job.key) == (UNCLEAR, "Posting is silent.")


def test_build_classifier_requires_prefs_and_key(store, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    assert build_classifier(prefs_from_dict({}), store) is None
    assert build_classifier(prefs_from_dict({"visa": {"classifier": True}}), store) is not None

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert build_classifier(prefs_from_dict({"visa": {"classifier": True}}), store) is None


def test_uses_the_shared_polite_client_when_none_is_injected(classifier_prefs, store, monkeypatch):
    built: list[float] = []

    def fake_make_client(timeout: float) -> httpx.Client:
        built.append(timeout)
        body = json.dumps({"sponsorship": "unclear", "reason": "Silent."})
        payload = {"content": [{"type": "text", "text": body}]}
        return httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        )

    monkeypatch.setattr("opportunities_abroad.classifier.make_client", fake_make_client)
    classifier_prefs.http_timeout_seconds = 12.5
    VisaClassifier(classifier_prefs, store, key="k").annotate([a_match()])

    assert built == [12.5]


def test_annotate_with_no_matches_makes_no_calls(classifier_prefs, store):
    with reply("{}") as client:
        VisaClassifier(classifier_prefs, store, client=client, key="k").annotate([])
        assert client.calls == []  # type: ignore[attr-defined]
