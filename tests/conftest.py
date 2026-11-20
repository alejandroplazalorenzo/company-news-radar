"""Shared test setup. The suite is offline, and every fact in the fixtures is invented: the
companies are real listed groups, the events, places and outlets are not."""

from __future__ import annotations

import socket
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from company_news_radar.net import Client
from company_news_radar.store import Store
from company_news_radar.watchlist import Company

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any real connection attempt fails the test."""

    def refuse(*_: object, **__: object) -> None:
        raise RuntimeError("network access attempted during tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


def fake_client(
    handler: Callable[[httpx.Request], httpx.Response],
    robots: str = "User-agent: *\nAllow: /\n",
    waits: list[float] | None = None,
) -> Client:
    """A client on a mock transport; /robots.txt answers ``robots`` unless the handler does."""

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text=robots, headers={"content-type": "text/plain"})
        return handler(request)

    sink = waits if waits is not None else []
    return Client(transport=httpx.MockTransport(route), sleep=sink.append)


COMPANIES = [
    Company("acerinox", "Acerinox", "ACERINOX, S.A.", "A28250777", aliases=("Acerinox",)),
    Company(
        "rovi",
        "Rovi",
        "LABORATORIOS FARMACÉUTICOS ROVI, S.A.",
        "A28041283",
        aliases=("Laboratorios Rovi", "Rovi"),
    ),
    Company(
        "endesa",
        "Endesa",
        "ENDESA, S.A.",
        "A28023430",
        aliases=("Endesa",),
        exclude=("Liga Endesa",),
    ),
    Company("sacyr", "Sacyr", "SACYR, S.A.", "A28013811", aliases=("Sacyr",)),
    Company(
        "colonial",
        "Colonial",
        "INMOBILIARIA COLONIAL, SOCIMI, S.A.",
        "A28027399",
        registered_names=("COLONIAL SFL, SOCIMI, S.A.",),
        aliases=("Inmobiliaria Colonial",),
    ),
]


@pytest.fixture
def companies() -> list[Company]:
    return list(COMPANIES)
