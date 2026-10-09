from __future__ import annotations

import httpx
import pytest

from opportunities_abroad.digest import render_compact_text
from opportunities_abroad.models import Match, RunResult
from opportunities_abroad.notifiers import (
    EmailConfigError,
    EmailNotifier,
    NtfyEmailNotifier,
    build_email_notifier,
)
from opportunities_abroad.notifiers.ntfy import MAX_BODY_BYTES

from tests.conftest import make_job


def a_result(count: int = 1) -> RunResult:
    return RunResult(
        matches=[
            Match(
                job=make_job(source_id=str(i), title=f"Python Engineer {i}", url=f"https://x/{i}"),
                score=50 - i,
            )
            for i in range(count)
        ]
    )


def recording_client(status: int = 200):
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(status, json={"id": "abc"})

    return httpx.Client(transport=httpx.MockTransport(handler)), sent


def test_sends_one_uncached_email_per_recipient_to_a_random_topic():
    client, sent = recording_client()
    with client:
        NtfyEmailNotifier(mail_to="a@example.com, b@example.com", client=client).send(a_result())
    assert [r.headers["Email"] for r in sent] == ["a@example.com", "b@example.com"]
    assert all(r.headers["Cache"] == "no" for r in sent)
    assert all(r.url.host == "ntfy.sh" for r in sent)
    topics = {r.url.path for r in sent}
    assert len(topics) == 2 and all(t.startswith("/moveabroad-") for t in topics)
    assert "1 matching role " in sent[0].headers["Title"]
    body = sent[0].content.decode("utf-8")
    assert "Python Engineer 0 @ Acme" in body
    assert "https://x/0" in body


def test_needs_no_key_only_a_recipient():
    with pytest.raises(EmailConfigError, match="EMAIL_TO"):
        NtfyEmailNotifier(mail_to="").require_configured()
    NtfyEmailNotifier(mail_to="a@example.com").require_configured()


def test_custom_server_is_used(monkeypatch):
    monkeypatch.setenv("NTFY_URL", "https://ntfy.example.org/")
    client, sent = recording_client()
    with client:
        NtfyEmailNotifier(mail_to="a@example.com", client=client).send(a_result())
    assert sent[0].url.host == "ntfy.example.org"


def test_rate_limit_is_explained():
    client, _ = recording_client(status=429)
    with client, pytest.raises(RuntimeError, match="rate-limited"):
        NtfyEmailNotifier(mail_to="a@example.com", client=client).send(a_result())


def test_compact_digest_stays_under_the_limit_and_counts_the_rest():
    body = render_compact_text(a_result(200), max_bytes=MAX_BODY_BYTES)
    assert len(body.encode("utf-8")) <= MAX_BODY_BYTES
    assert "Python Engineer 0 @" in body
    assert "more not shown." in body


def test_compact_digest_lists_everything_that_fits():
    body = render_compact_text(a_result(3), max_bytes=MAX_BODY_BYTES)
    assert "more not shown" not in body
    assert all(f"https://x/{i}" in body for i in range(3))


@pytest.mark.parametrize(
    "env,expected",
    [
        ({}, NtfyEmailNotifier),
        ({"SMTP_HOST": "smtp.example.com"}, EmailNotifier),
        ({"SMTP_HOST": "smtp.example.com", "EMAIL_PROVIDER": "ntfy"}, NtfyEmailNotifier),
        ({"EMAIL_PROVIDER": "SMTP"}, EmailNotifier),
    ],
)
def test_provider_selection(monkeypatch, env, expected):
    for key in ("SMTP_HOST", "EMAIL_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert isinstance(build_email_notifier(), expected)


def test_unknown_provider_is_rejected(monkeypatch):
    monkeypatch.setenv("EMAIL_PROVIDER", "carrier-pigeon")
    with pytest.raises(EmailConfigError, match="not supported"):
        build_email_notifier()
