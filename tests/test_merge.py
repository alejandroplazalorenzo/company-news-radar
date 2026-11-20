from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from company_news_radar import entities
from company_news_radar.classify import Answer, apply
from company_news_radar.digest import render
from company_news_radar.merge import load_manual, long_key, merge, same_signature, signature
from company_news_radar.models import Item
from company_news_radar.privacy import scrub
from company_news_radar.process import process
from company_news_radar.store import Store


def add(
    store: Store,
    companies,
    title: str,
    day: str,
    company: str | None,
    kind: str = "deal",
    fact: str | None = None,
    relevance: str = "medium",
    country: str = "Spain",
) -> int:
    """Stores a newsroom capture for ``company``, processes it and applies one answer."""
    store.add_captures(
        [
            Item(
                ident=title + day,
                url="https://x.test/" + title.replace(" ", "-") + day,
                headline=title,
                origin="newsroom",
                channel="s",
                published=f"{day}T08:00:00+00:00",
                standfirst=title,
                subject=company,
            )
        ]
    )
    process(store, entities.build(companies), None)
    sid = int(store.value("SELECT max(id) FROM story"))
    story = store.story(sid)
    assert story is not None
    numbers = [n for n, p in enumerate(store.parties(sid), start=1) if p["company"] == company]
    apply(store, story, Answer(kind, relevance, title, numbers, country, fact), "m", "v1")
    store.commit()
    return sid


def test_signature_rules() -> None:
    a = signature("Endesa y Sacyr firman una alianza ficticia de 500 millones en 2026")
    assert {"ENDESA", "SACYR", "500"} <= a and "2026" not in a and "Y" not in a
    assert same_signature(a, signature("Sacyr y Endesa sellan su alianza de 500 millones"))
    four = signature("Sacyr y Rovi firman un acuerdo en Villaejemplo por 40 millones")
    three = signature("Rovi abre en Villaejemplo un centro con Endesa")
    assert four == {"SACYR", "ROVI", "VILLAEJEMPLO", "40"}
    assert not same_signature(four, three)  # 2 shared, but the smaller set has 3
    assert signature("Banco Sabadell abre una oficina ficticia") == {"BANCO SABADELL"}
    assert not same_signature(  # the company's own name is one name, not two
        signature("Banco Sabadell abre una oficina ficticia"),
        signature("Banco Sabadell cierra otra oficina inventada en 2026"),
    )


def test_long_keys() -> None:
    assert long_key("bbva-bid-sabadell-approved", {"bbva", "sabadell"}) == "takeover:bbva+sabadell"
    assert long_key("acerinox-results-2025", {"acerinox"}) == "results:acerinox:2025"
    assert long_key("acerinox-results-q3-2026", {"acerinox"}) is None
    assert long_key("acerinox-buys-plant", {"acerinox"}) is None


def test_merge_by_fact_and_never_two_companies(store: Store, companies) -> None:
    a = add(
        store,
        companies,
        "Acerinox compra una planta ficticia",
        "2026-11-10",
        "acerinox",
        fact="acerinox-buys-plant-villaejemplo",
        relevance="high",
    )
    b = add(
        store,
        companies,
        "La siderúrgica cierra la operación inventada",
        "2026-11-20",
        "acerinox",
        kind="corporate",
        fact="acerinox-buys-plant-villaejemplo",
    )
    c = add(
        store,
        companies,
        "Sacyr se adjudica un puente ficticio",
        "2026-11-10",
        "sacyr",
        fact="acerinox-buys-plant-villaejemplo",
    )
    stats = merge(store, companies)
    assert stats["fact"] == 1
    assert store.story(b)["why_hidden"] == f"repeat of {a}"  # type: ignore[index]
    assert store.story(c)["state"] == "shown"  # type: ignore[index]  # another company
    assert store.value("SELECT count(*) FROM capture WHERE story_id = ?", a) == 2
    log = store.row("SELECT first_id, second_id, kept_id, author FROM decision WHERE act = 'merge'")
    assert log is not None and tuple(log) == (a, b, a, "fact")


def test_no_chain_across_companies(store: Store, companies) -> None:
    x = add(
        store,
        companies,
        "Endesa firma una alianza ficticia",
        "2026-11-10",
        "endesa",
        fact="endesa-alliance-villaejemplo",
    )
    y = add(
        store,
        companies,
        "Sacyr firma una alianza ficticia",
        "2026-11-11",
        "sacyr",
        fact="endesa-alliance-villaejemplo",
    )
    assert merge(store, companies)["fact"] == 0
    assert store.story(x)["state"] == store.story(y)["state"] == "shown"  # type: ignore[index]


def test_manual_no_wins_over_rules_and_judge(store: Store, companies, tmp_path: Path) -> None:
    a = add(
        store,
        companies,
        "Rovi gana 100 millones inventados",
        "2026-11-04",
        "rovi",
        kind="results",
        fact="rovi-results-9m-2026",
    )
    b = add(
        store,
        companies,
        "Rovi gana 100 millones inventados según analistas",
        "2026-11-05",
        "rovi",
        kind="results",
        fact="rovi-results-9m-2026",
    )
    manual = tmp_path / "manual.jsonl"
    manual.write_bytes(
        (json.dumps({"a": a, "b": b, "same": False, "note": "two releases"}) + "\n").encode()
    )
    assert load_manual(store, manual) == 1
    store.save_pair_verdict(a, b, True, "judge-j1")  # the judge cannot overwrite it
    assert merge(store, companies)["fact"] == 0
    assert store.story(b)["state"] == "shown"  # type: ignore[index]


def test_judge_asked_once_per_version(store: Store, companies) -> None:
    a = add(
        store,
        companies,
        "Endesa abre su mayor planta solar ficticia",
        "2026-11-10",
        "endesa",
        kind="footprint",
        fact="endesa-opens-solar-plant-villaejemplo",
    )
    b = add(
        store,
        companies,
        "La eléctrica estrena una planta solar en Villaejemplo",
        "2026-11-11",
        "endesa",
        kind="footprint",
        fact="endesa-new-solar-park",
    )
    asked: list[str] = []

    def judge(prompt: str, schema: dict[str, Any], purpose: str, n: int) -> dict[str, Any]:
        asked.append(prompt)
        pair = json.loads(next(line for line in prompt.splitlines() if line.startswith('{"a"')))
        assert pair["first"]["companies"] == ["Endesa"]
        return {"pairs": [{"a": pair["a"], "b": pair["b"], "same": True}]}

    stats = merge(store, companies, judge=judge)
    assert stats["judge"] == 1 and len(asked) == 1
    assert store.story(b)["why_hidden"] == f"repeat of {a}"  # type: ignore[index]
    assert merge(store, companies, judge=judge)["judge"] == 0 and len(asked) == 1


def test_privacy_and_digest(store: Store, companies) -> None:
    assert scrub("The board appointed Ana María López as CEO of Endesa") == (
        "The board appointed [person] as CEO of Endesa"
    )
    assert (
        scrub("Endesa sells its invented gas business") == "Endesa sells its invented gas business"
    )
    add(
        store,
        companies,
        "Endesa nombra a Luis Pérez consejero delegado",
        "2026-11-10",
        "endesa",
        kind="leadership",
        fact="endesa-new-ceo",
    )
    store.change("verdict", 1, gist="Endesa appoints Luis Pérez as chief executive.")
    by_id = {c.id: c for c in companies}
    full = render(store, by_id, date(2026, 11, 1), date(2026, 11, 18), True)
    assert "[person]" in full and "Pérez" not in full and "nombra" not in full  # no headline
    short = render(store, by_id, date(2026, 11, 1), date(2026, 11, 18), False)
    assert "| Endesa | 1 |" in short and "appoints" not in short
