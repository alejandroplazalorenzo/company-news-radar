from __future__ import annotations

import json
from datetime import UTC, date, datetime

import httpx
import pytest

from company_news_radar.sources import newsrooms, official, press
from company_news_radar.sources.newsrooms import Entry, Newsroom
from company_news_radar.store import Store
from tests.conftest import fake_client

ROVI = press.Channel("bing:rovi", None, "bing_news", "rovi")


def test_bing_query_and_parse(fixtures) -> None:
    assert press.queries(["Laboratorios Rovi", "Rovi", "Rovi"]) == ['"Laboratorios Rovi"', "Rovi"]
    items = press.parse((fixtures / "bing_news.xml").read_bytes(), ROVI)
    first = items[0]
    assert first.url == "https://www.diario-uno.test/empresas/rovi-villaejemplo"  # no utm_
    assert first.publisher == "Diario Uno" and first.publisher_host == "diario-uno.test"
    assert first.standfirst and "Villaejemplo" in first.standfirst
    assert first.published == "2026-11-04T09:00:00+00:00" and first.subject == "rovi"


def test_bing_pages_until_nothing_new_or_too_old(fixtures) -> None:
    pages_asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        pages_asked.append(request.url.params["first"])
        return httpx.Response(200, content=(fixtures / "bing_news.xml").read_bytes())

    client = fake_client(handler)
    since = datetime(2026, 11, 1, tzinfo=UTC)
    items = press.Search("Rovi", ROVI, since).run(client)
    assert len(items) == 2 and pages_asked == ["1", "3"]  # the second page repeated the first
    late = datetime(2026, 11, 4, 12, tzinfo=UTC)
    assert press.Search("Rovi", ROVI, late).run(client) == []


def test_feeds_rss_and_atom(fixtures) -> None:
    rss = press.parse(
        (fixtures / "feed_rss.xml").read_bytes(), press.Channel("feed:x", "Diario Tres")
    )
    assert len(rss) == 1  # the entry without a link is skipped
    assert rss[0].url == "https://www.diario-tres.test/economia/endesa-ficticia?id=7"
    assert rss[0].standfirst == "La eléctrica Endesa cierra una venta que no existe."
    assert rss[0].published == "2026-11-12T06:15:00+00:00"
    atom = press.parse(
        (fixtures / "feed_atom.xml").read_bytes(),
        press.Channel("nr", "Fluidra", "newsroom", "fluidra"),
    )
    assert atom[0].url.endswith("/press-room/centro-ficticio")  # rel=alternate, not self
    assert atom[0].subject == "fluidra" and atom[0].origin == "newsroom"


def _entries(*paths: str) -> list[Entry]:
    return [Entry(f"https://www.example.test{p}") for p in paths]


def test_newsroom_baseline_then_only_new_pages(store: Store) -> None:
    room = Newsroom(store, "newsroom:x:0", "x", "X")
    first = _entries("/es/prensa/uno", "/es/prensa/dos", "/es/prensa/archivo/2025")
    assert room.new_pages(first, whole=False, path_filter="^/es/prensa/") == []
    later = _entries(
        "/es/prensa/uno",
        "/es/prensa/tres",  # new: announced
        "/en/prensa/tres",  # a translation of it
        "/es/prensa/",  # a section page
        "/es/prensa/galeria/fotos-tres",  # a gallery
        "/es/productos/cuatro",  # outside the filter
    )
    items = room.new_pages(later, whole=False, path_filter="^/(es|en)/prensa/")
    assert [i.url for i in items] == ["https://www.example.test/es/prensa/tres"]
    assert items[0].headline == "Tres" and items[0].subject == "x"


def test_newsroom_marker_redesign_and_broken_filter(store: Store) -> None:
    room = Newsroom(store, "s", "x", "X")
    assert room.new_pages([], whole=True) == []
    assert store.known_urls("s") == {newsrooms.FIRST_READ}
    assert len(room.new_pages(_entries("/n/primera-nota"), whole=True)) == 1  # not a baseline
    flood = _entries(*[f"/n/nota-{i}" for i in range(60)])
    assert room.new_pages(flood, whole=True) == []  # a redesign announces nothing
    with pytest.raises(ValueError, match="no address matches"):
        room.new_pages(_entries("/a", "/b"), whole=False, path_filter="^/zz/")
    with pytest.raises(ValueError, match="path_filter is required"):
        room.new_pages(_entries("/a"), whole=False)


def test_sitemap_index_reads_news_children_first(fixtures) -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(request.url.path)
        name = "sitemap_index.xml" if request.url.path == "/sitemap.xml" else "sitemap.xml"
        return httpx.Response(200, content=(fixtures / name).read_bytes())

    read = newsrooms.read_sitemap(fake_client(handler), "https://www.example.test/sitemap.xml")
    assert asked[1] == "/news-sitemap.xml"
    titled = [e for e in read if e.title]
    assert titled[0].title == "Nueva planta" and titled[0].published == "2026-11-12T09:00:00+00:00"
    assert newsrooms.without_language("/gb-en/news/x") == "/news/x"
    assert newsrooms.without_language("/press/x") == "/press/x"


def test_borme_c_by_registered_name(fixtures) -> None:
    data = json.loads((fixtures / "borme_summary.json").read_text(encoding="utf-8"))
    reader = official.BormeC(
        {official.name_key("ACERINOX, S.A."): "acerinox", official.name_key("SACYR, S.A."): "sacyr"}
    )
    items = reader.parse(data, date(2026, 11, 16))
    assert [(i.subject, i.record_type, i.record_level) for i in items] == [
        ("acerinox", "deal", "high"),
        ("sacyr", "corporate", "low"),
    ]
    assert items[0].ident == "borme:BORME-C-2026-9001"
    assert official.names_in("A, S.A. (SOCIEDAD ABSORBENTE)\nB, S.L. (SOCIEDAD ABSORBIDA)") == [
        "A, S.A.",
        "B, S.L.",
    ]
    assert official.heading_type("REDUCCIÓN DE CAPITAL") == ("capital", "medium")


def test_bdns_grants_keep_one_key_each(fixtures) -> None:
    rows = json.loads((fixtures / "bdns.json").read_text("utf-8"))["content"]
    grants = official.bdns_items(rows, "A1", "x")
    assert [g.ident for g in grants] == ["bdns:SB100", "bdns:SB101"]
    assert grants[0].amount_eur == 2_500_000 and grants[0].record_type == "grant"
    assert "2.500.000 EUR" in grants[0].headline


def test_ted_awards_by_winner_with_or_without_prefix(fixtures) -> None:
    notices = json.loads((fixtures / "ted.json").read_text("utf-8"))["notices"]
    awards = official.ted_items(notices, {"A28013811": "sacyr"})
    assert len(awards) == 1
    assert awards[0].tax_ids == ("A28013811",) and awards[0].amount_eur == 1_250_000
    assert "Servicios de limpieza viaria" in awards[0].headline
    assert "España" not in awards[0].headline


def test_page_metadata() -> None:
    html = (
        "<html><head><title>Fallback</title>"
        '<meta property="og:title" content="Rovi abre una planta ficticia">'
        '<meta name="description" content="Una nota inventada.">'
        "</head><body></body></html>"
    )
    assert press.head_fields(html) == ("Rovi abre una planta ficticia", "Una nota inventada.")
    assert press.head_fields("<html><head><title> Solo título </title></head></html>") == (
        "Solo título",
        None,
    )


def test_fetch_plan_one_query_per_alias_and_only(store: Store, companies) -> None:
    from company_news_radar.extract import Window, plan

    client = fake_client(lambda r: httpx.Response(200))
    week = Window(date(2026, 11, 1), date(2026, 11, 2), weekly=True)
    kinds = [t.kind for t in plan(store, client, companies, week)]
    assert kinds.count("bing_news") == 6  # Rovi has two aliases
    assert {"feed", "borme_c", "bdns", "ted"} <= set(kinds)
    assert kinds[:2] == ["bing_news", "feed"]  # source types take turns
    only = Window(date(2026, 11, 1), date(2026, 11, 2), weekly=True, only=frozenset({"ted"}))
    assert [t.kind for t in plan(store, client, companies, only)] == ["ted"]
