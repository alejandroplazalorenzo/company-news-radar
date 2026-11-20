"""News outlets: RSS and Atom sections, Bing News search pages and the metadata of an article
page. The same parser reads all the XML; ``Channel.origin`` tells a search page from a feed.

On Bing each link points to a click-through address whose ``url`` parameter holds the article,
and the engine takes no date range, so :class:`Search` keeps asking for the next page while
pages still bring unseen results from the requested days. Its RSS ignored ``OR`` and negative
terms when tried on 19 Nov 2026, which is why every alias gets a query of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit

from lxml import etree
from lxml import html as lxml_html

from company_news_radar import config, models, net
from company_news_radar import textutil as tx

SEARCH = "https://www.bing.com/news/search"
SEARCH_PARAMS = {"format": "rss", "setlang": "es", "cc": "es"}
WHEN = "pubDate published updated date issued modified".split()
BODY = "description summary encoded content".split()
PAGE_TITLE = (
    "//meta[@property='og:title']/@content",
    "//meta[@name='twitter:title']/@content",
    "//title/text()",
)
PAGE_SUMMARY = (
    "//meta[@property='og:description']/@content",
    "//meta[@name='description' or @name='Description']/@content",
    "//meta[@name='twitter:description']/@content",
)
PAGE_REQUEST = {"timeout_s": config.TIMEOUT_PAGE_S, "pause_s": config.PAUSE_PAGE_S, "attempts": 2}


@dataclass(frozen=True)
class Channel:
    name: str
    publisher: str | None = None
    origin: str = "feed"
    subject: str | None = None


def entries(root: etree._Element) -> list[etree._Element]:
    found: list[etree._Element] = root.xpath("//*[local-name() = 'item' or local-name() = 'entry']")
    return found


def entry_link(entry: etree._Element) -> str | None:
    """Atom href (alternate or no rel), else RSS link text, else a guid that is a URL."""
    atom = entry.xpath("./*[local-name() = 'link'][@href][not(@rel) or @rel = 'alternate']/@href")
    rss = tx.text_of(entry, "link")
    guid = entry.xpath("./*[local-name() = 'guid'][not(@isPermaLink = 'false')]/text()")
    for candidate in (*atom, rss, *guid):
        if candidate and str(candidate).strip().startswith("http"):
            return str(candidate).strip()
    return None


def item_of(entry: etree._Element, channel: Channel) -> models.Item | None:
    searched = channel.origin == "bing_news"
    title = tx.text_of(entry, "title")
    link = tx.text_of(entry, "link") if searched else entry_link(entry)
    if not (title and link):
        return None
    url = publisher(link) if searched else tx.canonical_url(link)
    return models.Item(
        ident=url,
        url=url,
        headline=" ".join(title.split()),
        origin=channel.origin,
        channel=channel.name,
        published=tx.iso_utc(tx.text_of(entry, *WHEN)),
        publisher=tx.text_of(entry, "Source") if searched else channel.publisher,
        publisher_host=tx.host(url) if searched else None,
        standfirst=tx.to_text(tx.text_of(entry, *BODY)),
        subject=channel.subject,
    )


def parse(content: bytes, channel: Channel) -> list[models.Item]:
    root = tx.parse_xml(content)
    made = (item_of(e, channel) for e in (entries(root) if root is not None else []))
    return [it for it in made if it is not None]


def read_feed(client: net.Client, url: str, channel: Channel) -> list[models.Item]:
    return parse(client.get(url).content, channel)


def queries(names: list[str]) -> list[str]:
    """['Laboratorios Rovi', 'Rovi'] -> ['"Laboratorios Rovi"', 'Rovi']."""
    out: list[str] = []
    for name in map(str.strip, dict.fromkeys(n.replace('"', "") for n in names)):
        if name:
            out.append(name if name.isalnum() else f'"{name}"')
    return out


def publisher(link: str) -> str:
    inner = parse_qs(urlsplit(link).query).get("url", [link])
    return tx.canonical_url(inner[0])


@dataclass(frozen=True)
class Search:
    q: str
    channel: Channel
    since: datetime
    max_pages: int = config.SEARCH_MAX_PAGES

    def page(self, client: net.Client, offset: int) -> list[models.Item]:
        params = SEARCH_PARAMS | {"q": self.q, "first": offset}
        answer = client.get(SEARCH, params=params, pause_s=config.PAUSE_SEARCH_S)
        return parse(answer.content, self.channel)

    def run(self, client: net.Client) -> list[models.Item]:
        floor = self.since.isoformat()
        found: dict[str, models.Item] = {}
        offset = 1
        for _ in range(self.max_pages):
            batch = self.page(client, offset)
            fresh = {
                i.ident: i
                for i in batch
                if i.ident not in found and (i.published or floor) >= floor
            }
            if not fresh:
                break
            found |= fresh
            offset += len(batch)
        return list(found.values())


def first_value(tree: Any, paths: tuple[str, ...]) -> str | None:
    values = (" ".join(str(v).split()) for path in paths for v in tree.xpath(path))
    return next((v for v in values if v), None)


def head_fields(document: str) -> tuple[str | None, str | None]:
    """(title, description) of an HTML page; (None, None) if it does not parse."""
    try:
        tree = lxml_html.document_fromstring(document)
    except (etree.ParserError, ValueError):
        return None, None
    return first_value(tree, PAGE_TITLE), tx.to_text(first_value(tree, PAGE_SUMMARY))


def standfirst(client: net.Client, url: str) -> tuple[str | None, str | None]:
    page = client.get(url, **PAGE_REQUEST)
    if "html" in page.headers.get("content-type", "html"):
        return head_fields(page.text)
    return None, None
