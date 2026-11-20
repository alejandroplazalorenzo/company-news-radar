from __future__ import annotations

import httpx

from company_news_radar import entities, filters
from company_news_radar.models import Item
from company_news_radar.process import RepeatIndex, process
from company_news_radar.store import Store
from company_news_radar.textutil import canonical_url, host, iso_utc, normalise, slug, to_text
from tests.conftest import fake_client


def test_text_helpers() -> None:
    assert iso_utc("Mon, 16 Nov 2026 10:18:00 +0100") == "2026-11-16T09:18:00+00:00"
    assert iso_utc("2026-11-16") == "2026-11-16T00:00:00+00:00"
    assert iso_utc("2026-11-05+01:00") == "2026-11-05T00:00:00+00:00"
    assert iso_utc("30/10/2026") == "2026-10-30T00:00:00+00:00"
    assert iso_utc("not a date") is None
    assert canonical_url("HTTPS://X.TEST/a?utm_source=r&id=2#c") == "https://x.test/a?id=2"
    assert (
        host("https://www.Diario.test/x") == "diario.test" and host("diario.test") == "diario.test"
    )
    assert normalise("Enagás, S.A.") == "ENAGAS S A"
    assert slug("Iberdrola compra en España") == "iberdrola-compra-en-espana"
    assert to_text("<p>Uno <b>dos</b></p>") == "Uno dos"


def test_keys_must_distinguish() -> None:
    assert entities.strip_legal_form("AENA, S.M.E., S.A.") == "AENA"
    assert entities.strip_legal_form("MERLIN PROPERTIES SOCIMI, S.A.") == "MERLIN PROPERTIES"
    assert not entities.distinguishes("SANTANDER")  # a city
    assert not entities.distinguishes("BANCO SANTANDER")  # generic words only
    assert entities.distinguishes("ACERINOX EUROPA")
    assert not entities.distinguishes("ACS")  # one word, too short


def test_whole_phrases_and_homonyms(companies) -> None:
    d = entities.build(companies)
    assert [m.company for m in d.find("Rovi abre una planta ficticia")] == ["rovi"]
    assert d.find("La comarca de Groviana") == []  # never inside another word
    assert d.find("El Unicaja gana en la Liga Endesa") == []  # the homonym phrase drops Endesa
    assert {m.company for m in d.find("Endesa y Sacyr firman un acuerdo")} == {"endesa", "sacyr"}
    assert d.tax_ids["A28013811"] == "sacyr"


def test_calibration_drops_derived_words_written_in_lower_case(companies) -> None:
    d = entities.build(companies)
    assert "COLONIAL" in d.phrases(explicit=False)  # derived from the group name
    texts = ["la época colonial dejó huella", "arquitectura colonial en Cuba", "Endesa sube"]
    noisy = entities.calibrate(d, texts)
    assert "COLONIAL" in noisy and "COLONIAL" not in d.phrases()
    assert "INMOBILIARIA COLONIAL" in d.phrases(explicit=True)  # an alias is never dropped


def test_filters() -> None:
    assert filters.foreign_outlet("https://www.diario.test.mx/x")
    assert not filters.foreign_outlet("https://www.jornal.test.pt")  # Portugal is not filtered
    assert (
        filters.market_noise("Acciones de Acerinox hoy: bajan un 1,92%", True) == "share-price page"
    )
    assert (
        filters.market_noise("El Ibex 35 abre la sesión al alza", False) == "market session report"
    )
    assert filters.market_noise("Acerinox lidera las subidas del Ibex 35", True) is None
    assert filters.market_noise("Rovi gana un 12% más", True) is None
    assert filters.below_floor("grant", 4_800) and not filters.below_floor("grant", 0)
    assert not filters.below_floor("contract", 2_000_000)


def test_repeat_index_same_url_or_similar_headline_within_days() -> None:
    index = RepeatIndex()
    index.add(1, "Endesa vende su negocio ficticio de gas", "u1", "2026-11-12T07:00:00+00:00")
    assert (
        index.match("Endesa vende su negocio ficticio de gas.", "u2", "2026-11-14T09:00:00+00:00")
        == 1
    )
    assert (
        index.match("Endesa vende su negocio ficticio de gas", "u3", "2026-11-20T09:00:00+00:00")
        is None
    )
    assert index.match("Otra cosa", "u1", None) == 1


def _item(ident: str, headline: str, origin: str = "bing_news", **kw: object) -> Item:
    return Item(
        ident=ident,
        url=ident,
        headline=headline,
        origin=origin,
        channel="s",
        published="2026-11-12T08:00:00+00:00",
        **kw,
    )  # type: ignore[arg-type]


def test_process_filters_and_folds(store: Store, companies) -> None:
    store.add_captures(
        [
            _item(
                "https://a.test/1",
                "Sacyr gana un contrato ficticio en Chile",
                standfirst="La constructora Sacyr...",
                subject="sacyr",
                publisher_host="a.test",
            ),
            _item(
                "https://b.test/1",
                "Sacyr gana un contrato ficticio en Chile",
                standfirst="Sacyr...",
                subject="sacyr",
                publisher_host="b.test",
            ),
            _item(
                "https://c.test/1",
                "El Ibex 35 abre al alza",
                standfirst="Con Sacyr entre los mejores",
                subject="sacyr",
                publisher_host="c.test",
            ),
            _item(
                "https://d.test/1",
                "Una empresa cualquiera",
                standfirst="Nada que ver",
                subject="sacyr",
                publisher_host="d.test",
            ),
            _item(
                "https://e.test.ar/1",
                "Sacyr en Argentina",
                standfirst="Sacyr",
                subject="sacyr",
                publisher_host="e.test.ar",
            ),
            _item(
                "https://f.test/1",
                "Endesa vende gas inventado",
                origin="feed",
                standfirst="Endesa",
            ),
            _item(
                "https://g.test/1", "Otra noticia de economía", origin="feed", standfirst="nadie"
            ),
        ]
    )
    stats = process(store, entities.build(companies), None)
    assert stats["passed"] == 3 and stats["new_stories"] == 2 and stats["joined_exact"] == 1
    assert stats["market session report"] == 1
    assert stats["not named in headline or snippet"] == 1
    assert stats["foreign outlet"] == 1 and stats["names no watched company"] == 1


def test_register_records_never_fold_even_with_one_address(store: Store, companies) -> None:
    grants = [
        Item(
            ident=f"bdns:{n}",
            url="https://bdns.test/call/9",
            headline="BDNS grant of 200.000 EUR: same call",
            origin="bdns",
            channel="bdns",
            published="2026-11-02T00:00:00+00:00",
            subject=who,
            record_type="grant",
            record_level="medium",
            amount_eur=200_000.0,
            tax_ids=(tax,),
        )
        for n, (tax, who) in enumerate(
            [("A28013811", "sacyr"), ("A28023430", "endesa"), ("A28013811", "sacyr")]
        )
    ]
    store.add_captures(grants)
    stats = process(store, entities.build(companies), None)
    assert stats["new_stories"] == 3 and "joined_exact" not in stats
    owners = [p["company"] for (s,) in store.rows("SELECT id FROM story") for p in store.parties(s)]
    assert owners == ["sacyr", "endesa", "sacyr"]


def test_standfirst_only_for_what_passed(store: Store, companies) -> None:
    html = (
        '<html><head><meta property="og:description" content="Endesa cierra la venta.">'
        "</head></html>"
    )
    asked: list[str] = []

    def handler(r: httpx.Request) -> httpx.Response:
        asked.append(r.url.path)
        return httpx.Response(200, text=html, headers={"content-type": "text/html"})

    store.add_captures(
        [
            _item("https://f.test/2", "Endesa: comunicado", origin="feed"),
            _item("https://f.test/3", "Nadie conocido", origin="feed"),
        ]
    )
    process(store, entities.build(companies), fake_client(handler))
    row = store.row("SELECT standfirst, page_read FROM capture WHERE ident = 'https://f.test/2'")
    assert row is not None and row["standfirst"] == "Endesa cierra la venta."
    assert row["page_read"] == 1
    assert asked == ["/2"]  # the item that named nobody was dropped before any request


def test_homonym_phrase_drops_a_search_result(store: Store, companies) -> None:
    store.add_captures(
        [
            _item(
                "https://h.test/1",
                "La Liga Endesa abre la jornada",
                standfirst="Baloncesto",
                subject="endesa",
                publisher_host="h.test",
            ),
            _item(
                "https://h.test/2",
                "Endesa abre una planta ficticia",
                standfirst="Endesa",
                subject="endesa",
                publisher_host="h.test",
            ),
        ]
    )
    stats = process(store, entities.build(companies), None)
    assert stats["homonym phrase"] == 1 and stats["passed"] == 1


def test_source_checks_tell_failing_from_silent(store: Store) -> None:
    store.note_source("a", "feed", new=3)
    store.note_source("a", "feed", failure="HTTP 503")
    store.note_source("b", "feed", new=0)
    store.note_source("b", "feed", new=0)
    store.note_source("c", "feed", new=0)
    failing, silent = store.health(idle_runs=2)
    assert [r["source"] for r in failing] == ["a"] and failing[0]["error"] == "HTTP 503"
    assert [r["source"] for r in silent] == ["b"]  # c has one empty check, not two
    store.note_source("a", "feed", new=1)
    assert store.health(idle_runs=2)[0] == []
