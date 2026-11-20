"""Client for the Gemini REST API with a response schema and temperature 0.

Every attempt first takes one request from the on-disk counter (``quota.Quota``), so the
daily cap holds whatever Gemini reports. Requests are spaced by ``config.GEMINI_GAP_S``.
A 429 tied to a per-day quota raises ``QuotaExhausted``; any other 429 sleeps for the
``retryDelay`` Gemini sends (capped at two minutes). Server errors and timeouts back off
by ``config.OVERLOAD_WAITS_S``. The API key goes in a request header only.
"""

from __future__ import annotations

import json
import ssl
import time
from collections.abc import Callable
from typing import Any

import httpx
import truststore

from company_news_radar import config
from company_news_radar.quota import Quota, QuotaExhausted

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiError(RuntimeError):
    pass


def rate_limit(body: str) -> tuple[str, float | None]:
    """Quota id and suggested delay found in the body of a 429."""
    try:
        details = json.loads(body).get("error", {}).get("details", [])
    except (ValueError, AttributeError):
        return "", None
    quota_id, delay = "", None
    for detail in details if isinstance(details, list) else []:
        for violation in detail.get("violations") or []:
            quota_id = quota_id or str(violation.get("quotaId") or "")
        wait = str(detail.get("retryDelay") or "").removesuffix("s")
        if wait.replace(".", "", 1).isdigit():
            delay = float(wait)
    return quota_id, delay


def to_gemini_schema(node: Any) -> Any:
    """Same schema with the type names in upper case, as Gemini expects."""
    if isinstance(node, dict):
        out = {k: to_gemini_schema(v) for k, v in node.items()}
        if isinstance(out.get("type"), str):
            out["type"] = out["type"].upper()
        return out
    if isinstance(node, list):
        return [to_gemini_schema(v) for v in node]
    return node


class Gemini:
    def __init__(
        self,
        key: str,
        quota: Quota,
        model: str = config.GEMINI_MODEL,
        *,
        gap_s: float = config.GEMINI_GAP_S,
        attempts: int = config.GEMINI_ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = config.GEMINI_TIMEOUT_S,
    ) -> None:
        self.quota = quota
        self.model = model
        self.gap_s = gap_s
        self.attempts = attempts
        self._sleep = sleep
        self._clock = clock
        self._next_at = 0.0
        self._http = httpx.Client(
            verify=truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT),
            transport=transport,
            timeout=timeout_s,
            headers={"x-goog-api-key": key},
        )
        self.last: dict[str, Any] = {}

    def _wait_turn(self) -> None:
        delay = self._next_at - self._clock()
        if delay > 0:
            self._sleep(delay)
        self._next_at = self._clock() + self.gap_s

    def __call__(
        self, prompt: str, schema: dict[str, Any], purpose: str, n_items: int
    ) -> dict[str, Any]:
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": to_gemini_schema(schema),
            },
        }
        overload = iter(config.OVERLOAD_WAITS_S)
        for attempt in range(1, self.attempts + 1):
            self._wait_turn()
            self.quota.reserve()
            started = self._clock()
            record = {
                "purpose": purpose,
                "items": n_items,
                "model": self.model,
                "attempt": attempt,
                "cap": self.quota.cap,
            }
            try:
                answer = self._http.post(API.format(model=self.model), json=body)
            except httpx.TimeoutException:
                self.quota.log(
                    **record, status="timeout", seconds=round(self._clock() - started, 2)
                )
                self._sleep(next(overload, config.OVERLOAD_WAITS_S[-1]))
                continue
            seconds = round(self._clock() - started, 2)
            if answer.status_code == 200:
                return self._read(answer, record, seconds)
            self.quota.log(**record, status=answer.status_code, seconds=seconds)
            if answer.status_code == 429:
                quota_id, delay = rate_limit(answer.text)
                if "PerDay" in quota_id:
                    raise QuotaExhausted(f"per-day quota used up ({quota_id})")
                wait = config.RATE_WAIT_DEFAULT_S if delay is None else delay
                self._sleep(min(wait, config.RATE_WAIT_CAP_S) + config.RATE_WAIT_EXTRA_S)
                continue
            if answer.status_code in (500, 502, 503, 504):
                self._sleep(next(overload, config.OVERLOAD_WAITS_S[-1]))
                continue
            raise GeminiError(
                f"Gemini refused the request ({answer.status_code}): {answer.text[:300]}"
            )
        raise GeminiError(f"{self.attempts} attempts to Gemini, none usable")

    def _read(
        self, answer: httpx.Response, record: dict[str, Any], seconds: float
    ) -> dict[str, Any]:
        data = answer.json()
        usage = data.get("usageMetadata") or {}
        self.last = {
            "seconds": seconds,
            "prompt_tokens": usage.get("promptTokenCount"),
            "output_tokens": usage.get("candidatesTokenCount"),
            "model_version": data.get("modelVersion"),
        }
        self.quota.log(**record, status=200, **self.last)
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            parsed: dict[str, Any] = json.loads(text)
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            reason = (data.get("candidates") or [{}])[0].get("finishReason")
            raise GeminiError(f"reply without a JSON body (finishReason {reason})") from exc
        return parsed
