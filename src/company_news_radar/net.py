"""HTTP for the sources (Gemini and Ollama use clients of their own).

Each host gets its own lock, pacing and robots.txt, read before anything else is asked of
it; redirects are followed one hop at a time and each hop's host is checked the same way.
TLS goes through truststore and the system certificates. Failed requests are retried as
``config`` sets out (attempts, waits, Retry-After). Hosts in ``NEVER_ASK`` are refused
outright, and the client stops asking a host for the rest of the run once its answers have
been ``config.BRAKE_STATUSES`` codes ``config.BRAKE_AFTER`` times running.
"""

from __future__ import annotations

import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import partialmethod
from typing import Any

import httpx
import truststore

from company_news_radar import __version__, config, robots

PRODUCT_TOKEN = "company-news-radar"
USER_AGENT = (
    f"{PRODUCT_TOKEN}/{__version__} (+https://github.com/alejandroplazalorenzo/company-news-radar; "
    "alejandroplaza.dev@gmail.com)"
)
# Google News is out of scope for this project; see docs/sources.md
NEVER_ASK = frozenset({"news.google.com"})
RETRYABLE = frozenset({429, 500, 502, 503, 504})


class HttpError(RuntimeError):
    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Disallowed(HttpError):
    """Raised before sending: robots.txt, NEVER_ASK or the per-host brake said no."""


@dataclass
class Tally:
    requests: int = 0
    retries: int = 0
    refused: int = 0
    redirects: int = 0


@dataclass
class _Host:
    lock: threading.Lock = field(default_factory=threading.Lock)
    ready_at: float = 0.0
    rules: robots.Robots | None = None
    blocked_in_a_row: int = 0
    braked: bool = False


def _trust_store() -> ssl.SSLContext:
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def _wait_hint(response: httpx.Response) -> float | None:
    value = (response.headers.get("retry-after") or "").strip()
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


class Client:
    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        pause_s: float = config.PAUSE_S,
        timeout_s: float = config.TIMEOUT_S,
    ) -> None:
        self._http = httpx.Client(
            verify=_trust_store(),
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_s,
            follow_redirects=False,
        )
        self._sleep = sleep
        self._clock = clock
        self.pause_s = pause_s
        self._hosts: dict[str, _Host] = {}
        self._registry = threading.Lock()
        self._count = threading.Lock()
        self.tally = Tally()

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
        pause_s: float | None = None,
        timeout_s: float | None = None,
        attempts: int = config.ATTEMPTS,
    ) -> httpx.Response:
        """Response after following redirects; raises HttpError on a final status of 400+."""
        target = httpx.URL(url, params=params) if params else httpx.URL(url)
        for _hop in range(config.MAX_REDIRECTS + 1):
            response = self._send(method, target, json, headers, pause_s, timeout_s, attempts)
            follow = response.next_request if response.is_redirect else None
            if follow is None:
                if response.status_code >= 400:
                    raise HttpError(
                        f"{target} answered {response.status_code}", response.status_code
                    )
                return response
            self._add(redirects=1)
            if follow.method != method:
                json = None
            method, target = follow.method, follow.url
        raise HttpError(f"{url}: redirect chain longer than {config.MAX_REDIRECTS}")

    get = partialmethod(request, "GET")
    post = partialmethod(request, "POST")

    def robots_report(self) -> dict[str, str]:
        with self._registry:
            return {h: s.rules.verdict for h, s in sorted(self._hosts.items()) if s.rules}

    def summary(self) -> dict[str, Any]:
        return {**asdict(self.tally), "robots": self.robots_report()}

    def close(self) -> None:
        self._http.close()

    def _add(self, **counts: int) -> None:
        with self._count:
            for name, n in counts.items():
                setattr(self.tally, name, getattr(self.tally, name) + n)

    def _host(self, name: str) -> _Host:
        with self._registry:
            return self._hosts.setdefault(name, _Host())

    def _refuse(self, why: str) -> Disallowed:
        self._add(refused=1)
        return Disallowed(why)

    def _pace(self, state: _Host, pause_s: float | None) -> None:
        delay = state.ready_at - self._clock()
        if delay > 0:
            self._sleep(delay)
        state.ready_at = self._clock() + (self.pause_s if pause_s is None else pause_s)

    def _load_robots(self, url: httpx.URL, state: _Host) -> robots.Robots:
        where = url.copy_with(path="/robots.txt", query=None, fragment=None)
        for _hop in range(config.MAX_REDIRECTS + 1):
            self._pace(state, None)
            try:
                answer = self._http.get(where, timeout=config.TIMEOUT_ROBOTS_S)
            except httpx.HTTPError:
                return robots.unreachable()
            self._add(requests=1)
            follow = answer.next_request if answer.is_redirect else None
            if follow is None:
                body = answer.content[: robots.MAX_BYTES].decode(
                    answer.encoding or "utf-8", "replace"
                )
                return robots.from_response(
                    answer.status_code, answer.headers.get("content-type", ""), body, PRODUCT_TOKEN
                )
            where = follow.url
        return robots.unreachable()

    def _send(
        self,
        method: str,
        url: httpx.URL,
        json: Any,
        headers: dict[str, str] | None,
        pause_s: float | None,
        timeout_s: float | None,
        attempts: int,
    ) -> httpx.Response:
        name = url.host.lower()
        if name in NEVER_ASK:
            raise self._refuse(f"{name} is on the never-ask list")
        state = self._host(name)
        with state.lock:
            if state.braked:
                raise self._refuse(f"{name} braked after {config.BRAKE_AFTER} blocking answers")
            if state.rules is None:
                state.rules = self._load_robots(url, state)
            if not state.rules.allows(str(url)):
                raise self._refuse(f"{url} disallowed by robots.txt")
            response = self._attempts(
                state, method, url, json, headers, pause_s, timeout_s, attempts
            )
            if response.status_code in config.BRAKE_STATUSES:
                state.blocked_in_a_row += 1
                state.braked = state.blocked_in_a_row >= config.BRAKE_AFTER
            else:
                state.blocked_in_a_row = 0
            return response

    def _attempts(
        self,
        state: _Host,
        method: str,
        url: httpx.URL,
        json: Any,
        headers: dict[str, str] | None,
        pause_s: float | None,
        timeout_s: float | None,
        attempts: int,
    ) -> httpx.Response:
        timeout = httpx.USE_CLIENT_DEFAULT if timeout_s is None else timeout_s
        for attempt in range(1, attempts + 1):
            self._pace(state, pause_s)
            last_try = attempt == attempts
            try:
                response = self._http.request(
                    method, url, json=json, headers=headers, timeout=timeout
                )
            except httpx.TransportError as exc:
                self._add(requests=1)
                if last_try:
                    raise HttpError(f"{url.host}: {type(exc).__name__}") from exc
                self._add(retries=1)
                self._sleep(config.NETWORK_WAIT_BASE_S**attempt)
                continue
            self._add(requests=1)
            if response.status_code not in RETRYABLE or last_try:
                return response
            self._add(retries=1)
            hint = _wait_hint(response)
            wait = config.RETRY_WAIT_S * attempt if hint is None else hint
            self._sleep(min(wait, config.RETRY_AFTER_CAP_S))
        raise AssertionError("unreachable")  # pragma: no cover
