from __future__ import annotations

import os

import httpx

DEFAULT_USER_AGENT = (
    "moveabroad/0.1 (+https://github.com/jaspreetsingh0792/moveabroad)"
)


def user_agent() -> str:
    return os.environ.get("HTTP_USER_AGENT", DEFAULT_USER_AGENT)


def make_client(timeout: float = 30.0) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": user_agent(), "Accept": "application/json"},
    )
