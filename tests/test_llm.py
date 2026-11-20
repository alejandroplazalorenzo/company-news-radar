from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from company_news_radar import entities, prompts
from company_news_radar.classify import classify, decide, reopen
from company_news_radar.gemini import Gemini, rate_limit, to_gemini_schema
from company_news_radar.models import Item
from company_news_radar.process import process
from company_news_radar.quota import Quota, QuotaExhausted, next_reset, quota_day
from company_news_radar.store import Store


def test_quota_day_starts_at_nine_in_madrid() -> None:
    assert quota_day(datetime(2026, 11, 18, 7, 59, tzinfo=UTC)).isoformat() == "2026-11-17"
    assert quota_day(datetime(2026, 11, 18, 8, 0, tzinfo=UTC)).isoformat() == "2026-11-18"
    assert quota_day(datetime(2026, 7, 1, 7, 0, tzinfo=UTC)).isoformat() == "2026-07-01"  # CEST
    assert (
        next_reset(datetime(2026, 11, 18, 8, tzinfo=UTC)).isoformat() == "2026-11-19T09:00:00+01:00"
    )


def test_cap_is_persistent_shared_and_cannot_be_raised(tmp_path: Path) -> None:
    now = [datetime(2026, 11, 18, 10, tzinfo=UTC)]
    q = Quota(tmp_path / "quota.json", cap=2, now=lambda: now[0])
    q.reserve()
    q.reserve()
    with pytest.raises(QuotaExhausted):
        Quota(tmp_path / "quota.json", cap=2, now=lambda: now[0]).reserve()  # another process
    now[0] = datetime(2026, 11, 19, 8, 1, tzinfo=UTC)
    q.reserve()
    assert q.used_today() == 1 and q.used_total() == 3
    with pytest.raises(ValueError):
        Quota(tmp_path / "q2.json", cap=501)


def _gemini(tmp_path: Path, answers: list[httpx.Response], sent: list[httpx.Request]) -> Gemini:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return answers.pop(0)

    quota = Quota(tmp_path / "quota.json", cap=10)
    return Gemini(
        "SECRET-KEY", quota, gap_s=0, sleep=lambda _s: None, transport=httpx.MockTransport(handler)
    )


def _ok(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [{"content": {"parts": [{"text": json.dumps(payload)}]}}],
            "usageMetadata": {"promptTokenCount": 900, "candidatesTokenCount": 120},
            "modelVersion": "gemini-test-001",
        },
    )


def _too_many(quota_id: str, delay: str = "7s") -> httpx.Response:
    return httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "details": [
                    {"@type": "QuotaFailure", "violations": [{"quotaId": quota_id}]},
                    {"@type": "RetryInfo", "retryDelay": delay},
                ],
            }
        },
    )


def test_gemini_key_in_header_and_per_minute_retry(tmp_path: Path) -> None:
    sent: list[httpx.Request] = []
    g = _gemini(
        tmp_path, [_too_many("GenerateRequestsPerMinutePerProject"), _ok({"items": []})], sent
    )
    assert g("p", prompts.SCHEMA, "classify-v1", 3) == {"items": []}
    assert len(sent) == 2 and g.quota.used_today() == 2  # every attempt counts
    assert (
        "SECRET-KEY" not in str(sent[0].url) and sent[0].headers["x-goog-api-key"] == "SECRET-KEY"
    )
    body = json.loads(sent[0].content)
    assert body["generationConfig"]["temperature"] == 0
    assert body["generationConfig"]["responseSchema"]["type"] == "OBJECT"
    log = (tmp_path / "llm_calls.jsonl").read_text("utf-8")
    assert "SECRET-KEY" not in log and "gemini-test-001" in log and '"status": 429' in log


def test_gemini_per_day_429_stops_and_names_the_quota(tmp_path: Path) -> None:
    g = _gemini(tmp_path, [_too_many("GenerateRequestsPerDayPerProjectPerModel-FreeTier")], [])
    with pytest.raises(QuotaExhausted, match="PerDay"):
        g("p", prompts.SCHEMA, "classify-v1", 3)
    assert rate_limit(_too_many("X", "12.5s").text) == ("X", 12.5)
    assert (
        to_gemini_schema({"type": "array", "items": {"type": "string"}})["items"]["type"]
        == "STRING"
    )


def test_post_rules() -> None:
    abroad = decide("deal", "high", "United States", True, True, "bing_news")
    assert abroad.shown and abroad.level == "medium" and not abroad.on_front
    assert (
        decide("deal", "high", "Argentina", False, True).why_hidden == "abroad, no watched company"
    )
    assert decide("corporate", "low", "Spain", False, True).why_hidden == "homonym"
    assert decide("regulation", "high", "Spain", False, True).shown
    assert decide("irrelevant", "low", "Spain", True, True).why_hidden == "irrelevant"
    home = decide("footprint", "medium", "España", True, True)
    assert home.on_front and home.alerts


def _story(store: Store, companies, headline: str, **kw: object) -> int:
    store.add_captures(
        [
            Item(
                ident=headline,
                url="https://x.test/" + headline,
                headline=headline,
                origin=kw.pop("origin", "bing_news"),  # type: ignore[arg-type]
                channel="s",
                published="2026-11-12T08:00:00+00:00",
                standfirst=headline,
                **kw,
            )
        ]
    )  # type: ignore[arg-type]
    process(store, entities.build(companies), None)
    return int(store.value("SELECT max(id) FROM story"))


def _echo(kind: str = "deal") -> Any:
    seen: list[str] = []

    def llm(prompt: str, schema: dict[str, Any], purpose: str, n: int) -> dict[str, Any]:
        seen.append(prompt)
        refs = [
            json.loads(line)["ref"] for line in prompt.splitlines() if line.startswith('{"ref":')
        ]
        return {
            "items": [
                {
                    "ref": r,
                    "type": kind,
                    "relevance": "high",
                    "summary": "s",
                    "companies": [1],
                    "country": "Spain",
                    "fact_key": "Rovi Planta Villa",
                }
                for r in refs
            ]
        }

    llm.seen = seen  # type: ignore[attr-defined]
    return llm


def test_classify_official_from_source_floor_and_items_as_json(store: Store, companies) -> None:
    a = _story(store, companies, "Acerinox compra una planta ficticia", subject="acerinox")
    _story(store, companies, "Rovi presenta un plan inventado", subject="rovi")
    store.add_captures(
        [
            Item(
                ident="bdns:1",
                url="u",
                headline="BDNS grant of 4.800 EUR",
                origin="bdns",
                channel="bdns",
                published="2026-11-01T00:00:00+00:00",
                subject="sacyr",
                record_type="grant",
                record_level="medium",
                amount_eur=4800.0,
                tax_ids=("A28013811",),
            )
        ]
    )
    process(store, entities.build(companies), None)
    llm = _echo()
    stats = classify(store, {c.id: c for c in companies}, llm, "v1", batch_size=1)
    assert stats["official"] == 1 and stats["below_minimum"] == 1 and stats["calls"] == 2
    assert stats["classified"] == 2
    lines = llm.seen[0].splitlines()
    first = json.loads(next(line for line in lines if line.startswith('{"ref":')))
    assert first["candidates"] == [{"n": 1, "company": "Acerinox"}] and first["ref"] == a
    s = store.story(a)
    assert s is not None and s["fact_key"] == "rovi-planta-villa" and s["on_front"] == 1
    assert store.value("SELECT count(*) FROM answer WHERE version = 'v1'") == 2


def test_quota_exhausted_leaves_stories_pending(store: Store, companies) -> None:
    _story(store, companies, "Acerinox compra una planta ficticia", subject="acerinox")

    def no_quota(*_: object) -> dict[str, object]:
        raise QuotaExhausted("cap")

    stats = classify(store, {c.id: c for c in companies}, no_quota, "v1")
    assert stats["pending"] == 1 and stats["stopped_quota"] == 1


def test_two_failed_batches_stop_the_run(store: Store, companies) -> None:
    for title in ("Acerinox compra una planta", "Rovi abre una fábrica", "Sacyr gana un puente"):
        _story(store, companies, title + " ficticia", subject=title.split()[0].lower())
    calls: list[int] = []

    def overloaded(*_: object) -> dict[str, object]:
        calls.append(1)
        raise RuntimeError("Gemini 503: overloaded")

    stats = classify(store, {c.id: c for c in companies}, overloaded, "v1", batch_size=1)
    assert len(calls) == 2 and stats["stopped_overload"] == 1 and stats["pending"] == 3


def test_reopen_everything_by_default_or_only_the_visible(store: Store, companies) -> None:
    _story(store, companies, "Acerinox compra una planta ficticia", subject="acerinox")
    _story(store, companies, "Rovi en la bolsa inventada", subject="rovi")
    classify(store, {c.id: c for c in companies}, _echo(), "v1")
    store.change("verdict", 2, shown=0, why_hidden="irrelevant")
    assert reopen(store, only_visible=True) == 1
    classify(store, {c.id: c for c in companies}, _echo(), "v1")
    store.change("verdict", 2, shown=0, why_hidden="irrelevant")
    assert reopen(store) == 2  # by default every model verdict is reopened


def test_cap_holds_with_two_counters_at_once(tmp_path: Path) -> None:
    """Two Quota objects (as two processes would) share the file lock, not a thread lock."""
    from concurrent.futures import ThreadPoolExecutor

    now = datetime(2026, 11, 18, 10, tzinfo=UTC)
    counters = [Quota(tmp_path / "quota.json", cap=40, now=lambda: now) for _ in range(2)]

    def take(k: int) -> bool:
        try:
            counters[k % 2].reserve()
        except QuotaExhausted:
            return False
        return True

    with ThreadPoolExecutor(max_workers=8) as pool:
        granted = sum(pool.map(take, range(100)))
    assert granted == 40 and counters[0].used_today() == 40
