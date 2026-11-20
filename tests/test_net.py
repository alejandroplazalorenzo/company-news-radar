from __future__ import annotations

import httpx
import pytest

from company_news_radar import robots
from company_news_radar.net import Disallowed, HttpError
from tests.conftest import fake_client

TOKEN = "company-news-radar"


def rules(text: str) -> robots.Robots:
    return robots.from_response(200, "text/plain", text, TOKEN)


def test_wildcards_are_understood() -> None:
    r = rules("User-agent: *\nDisallow: /*format=rss\n")
    assert not r.allows("https://h.test/news/search?q=x&format=rss")
    assert r.allows("https://h.test/news/search?q=x")


def test_longest_match_wins_not_the_first() -> None:
    r = rules("User-agent: *\nAllow: /\nDisallow: /private\n")
    assert not r.allows("https://h.test/private/x")
    r = rules("User-agent: *\nDisallow: /news/\nAllow: /news/search\n")
    assert r.allows("https://h.test/news/search?q=x")
    assert not r.allows("https://h.test/news/archive")


def test_allow_wins_a_tie_and_dollar_anchors() -> None:
    assert rules("User-agent: *\nDisallow: /a\nAllow: /a\n").allows("https://h.test/a")
    r = rules("User-agent: *\nDisallow: /*.pdf$\n")
    assert not r.allows("https://h.test/report.pdf")
    assert r.allows("https://h.test/report.pdf?page=2")


def test_own_group_beats_star_and_groups_combine() -> None:
    text = (
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: Company-News-Radar\nUser-agent: other\nDisallow: /private/\n\n"
        "User-agent: company-news-radar\nDisallow: /drafts/\n"
    )
    r = rules(text)
    assert r.allows("https://h.test/news")
    assert not r.allows("https://h.test/private/1") and not r.allows("https://h.test/drafts/1")


def test_percent_encoding_is_normalised() -> None:
    r = rules("User-agent: *\nDisallow: /caf%C3%A9\nDisallow: /%7Euser\n")
    assert not r.allows("https://h.test/café/menu")
    assert not r.allows("https://h.test/~user/page")


def test_status_of_the_robots_file() -> None:
    assert robots.from_response(404, "text/html", "", TOKEN).allows("https://h.test/x")
    assert robots.from_response(200, "text/html", "<html></html>", TOKEN).verdict == "not_robots"
    assert robots.from_response(200, "", "<html><h1>Rejected</h1>", TOKEN).allows(
        "https://h.test/x"
    )
    assert not robots.from_response(503, "text/plain", "", TOKEN).allows("https://h.test/x")
    assert not robots.from_response(429, "text/plain", "", TOKEN).allows("https://h.test/x")
    assert robots.from_response(503, "", "", TOKEN).allows("https://h.test/robots.txt")


def test_client_refuses_what_robots_disallows() -> None:
    asked: list[str] = []
    client = fake_client(
        lambda r: asked.append(str(r.url)) or httpx.Response(200, text="ok"),
        robots="User-agent: *\nDisallow: /rss/\n",
    )
    with pytest.raises(Disallowed):
        client.get("https://site.test/rss/search?q=x")
    assert client.get("https://site.test/topics/").text == "ok"
    assert asked == ["https://site.test/topics/"] and client.tally.refused == 1


def test_google_news_is_never_asked_whatever_its_robots_says() -> None:
    sent: list[str] = []
    client = fake_client(lambda r: sent.append(str(r.url)) or httpx.Response(200))
    with pytest.raises(Disallowed, match="never-ask list"):
        client.get("https://news.google.com/rss/search?q=Acerinox")
    assert sent == [] and client.robots_report() == {}  # not even its robots.txt


def test_every_redirect_hop_is_checked() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "a.test":
            return httpx.Response(301, headers={"location": "https://b.test/private/page"})
        return httpx.Response(200, text="should not be fetched")

    def route(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /private/\n" if request.url.host == "b.test" else ""
            return httpx.Response(200, text=body, headers={"content-type": "text/plain"})
        return handler(request)

    from company_news_radar.net import Client

    client = Client(transport=httpx.MockTransport(route), sleep=lambda _s: None)
    with pytest.raises(Disallowed):
        client.get("https://a.test/start")
    assert client.tally.redirects == 1


def test_retries_honour_retry_after_and_stop_on_other_4xx() -> None:
    answers = [httpx.Response(503, headers={"retry-after": "7"}), httpx.Response(200, text="ok")]
    waits: list[float] = []
    client = fake_client(lambda r: answers.pop(0), waits=waits)
    assert client.get("https://slow.test/x").text == "ok"
    assert 7.0 in waits and client.tally.retries == 1
    client = fake_client(lambda r: httpx.Response(404))
    with pytest.raises(HttpError) as err:
        client.get("https://gone.test/x")
    assert err.value.status == 404 and client.tally.retries == 0


def test_a_host_that_keeps_blocking_is_left_alone() -> None:
    client = fake_client(lambda r: httpx.Response(403))
    for _ in range(3):
        with pytest.raises(HttpError):
            client.get("https://grumpy.test/x")
    with pytest.raises(Disallowed, match="braked"):
        client.get("https://grumpy.test/y")
