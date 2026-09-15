from __future__ import annotations

from opportunities_abroad.http import DEFAULT_USER_AGENT, make_client, user_agent


def test_client_identifies_the_project_and_honours_the_timeout():
    with make_client(7.5) as client:
        assert client.headers["User-Agent"] == DEFAULT_USER_AGENT
        assert "moveabroad" in client.headers["User-Agent"]
        assert client.timeout.read == 7.5


def test_user_agent_is_overridable(monkeypatch):
    monkeypatch.setenv("HTTP_USER_AGENT", "custom-agent/2.0")
    assert user_agent() == "custom-agent/2.0"
