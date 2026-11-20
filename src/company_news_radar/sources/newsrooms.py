"""Press pages that the watched companies publish on their own sites.

A site is read through its sitemap. The radar keeps every address it has seen per sitemap
and reports only addresses it has not seen before. The very first read only records what
is there (otherwise the whole archive would arrive as news), and an unusually large batch
of unseen addresses is recorded the same way, because it means the site was rebuilt.
Listing pages, files and other-language copies of a known page are skipped.
"""

from __future__ import annotations

import gzip
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from lxml import etree

from company_news_radar import config
from company_news_radar.models import Item
from company_news_radar.net import Client
from company_news_radar.store import Store
from company_news_radar.textutil import iso_utc, parse_xml, tag

log = logging.getLogger(__name__)

FIRST_READ = "#first-read"  # fake address saved on the first read: known_urls is never empty
LANGUAGES = frozenset("ca de en es eu fr gl it nl pt".split())
SECTION_WORDS = frozenset(
    """
    archive archivo author autor busqueda buscar categoria categorias category etiqueta
    etiquetas fotos galeria galerias gallery hemeroteca imagenes images multimedia page
    pagina paginas photos search tag tags video videos
    """.split()
)
MEDIA_SUFFIXES = (".gif", ".jpeg", ".jpg", ".mp3", ".mp4", ".png", ".svg", ".webp", ".zip")


@dataclass(frozen=True)
class Entry:
    url: str
    lastmod: str | None = None
    title: str | None = None
    published: str | None = None


def _xml(client: Client, url: str) -> etree._Element | None:
    body = client.get(url).content
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return parse_xml(body)


def _first(node: etree._Element, path: str) -> str | None:
    return next((str(v).strip() for v in node.xpath(path) if str(v).strip()), None)


def entry_of(node: etree._Element) -> Entry:
    news = ".//*[local-name() = 'news']/*[local-name() = '{}']"
    return Entry(
        _first(node, "./*[local-name() = 'loc']/text()") or "",
        iso_utc(_first(node, "./*[local-name() = 'lastmod']/text()")),
        _first(node, news.format("title") + "//text()"),
        iso_utc(_first(node, news.format("publication_date") + "/text()")),
    )


def read_sitemap(client: Client, url: str, depth: int = 0) -> list[Entry]:
    """Entries of a sitemap; an index is followed two levels down, news children first."""
    root = _xml(client, url)
    if root is None:
        return []
    if tag(root) != "sitemapindex":
        return [
            entry_of(n) for n in root.xpath("./*[local-name() = 'url'][*[local-name() = 'loc']]")
        ]
    children = [str(c).strip() for c in root.xpath("./*/*[local-name() = 'loc']/text()")]
    children.sort(key=lambda c: "news" not in c.lower())
    allowed = children[: config.CHILD_SITEMAPS_MAX] if depth < 2 else []
    return [e for child in allowed for e in read_sitemap(client, child, depth + 1)]


def path_of(url: str) -> str:
    return urlsplit(url).path or "/"


def without_language(path: str) -> str:
    """Removes a leading language segment such as /en/ or /es-es/."""
    head, _, rest = path.lstrip("/").partition("/")
    pieces = head.lower().split("-")
    if (
        rest
        and pieces
        and all(p in LANGUAGES or len(p) == 2 for p in pieces)
        and (set(pieces) & LANGUAGES)
    ):
        return "/" + rest
    return path


def is_section(path: str, all_paths: set[str]) -> bool:
    if path.endswith("/") or path.lower().endswith(MEDIA_SUFFIXES):
        return True
    segments = [s for s in path.lower().split("/") if s]
    if not segments or segments[-1].isdigit() or SECTION_WORDS & set(segments):
        return True
    prefix = path.rstrip("/") + "/"
    return any(other.startswith(prefix) for other in all_paths)


def title_from_url(url: str) -> str:
    """A readable headline from the last path segment, used when the sitemap has none."""
    last = path_of(url).rstrip("/").rsplit("/", 1)[-1]
    stem = last.rsplit(".", 1)[0] if "." in last else last
    text = " ".join(stem.replace("_", "-").split("-")).strip()
    return text[:1].upper() + text[1:] if text else url


@dataclass
class Newsroom:
    store: Store
    site: str
    company: str
    publisher: str

    def new_pages(
        self, entries: list[Entry], *, whole: bool, path_filter: str | None = None
    ) -> list[Item]:
        """Unseen article pages among ``entries``. Every unseen address is remembered.

        ``whole`` is for news sitemaps; any other sitemap needs ``path_filter``, and a filter
        with no hit at all raises, since that usually means the site moved its pages.
        """
        if not whole and not path_filter:
            raise ValueError(f"{self.site}: path_filter is required for a general sitemap")
        rule = re.compile(path_filter) if path_filter else None
        matching = [e for e in entries if whole or (rule and rule.search(path_of(e.url)))]
        if rule and entries and not matching:
            raise ValueError(f"{self.site}: no address matches {path_filter!r}")
        known = self.store.known_urls(self.site)
        if not known:
            self.store.remember_urls(
                self.site, [(e.url, e.lastmod) for e in matching] + [(FIRST_READ, None)]
            )
            return []
        fresh = [e for e in matching if e.url not in known]
        if len(fresh) > config.REDESIGN_NEW_URLS and len(fresh) > config.REDESIGN_SHARE * (
            len(known) + len(fresh)
        ):
            log.warning("%s: %d unseen addresses in one read; stored, none reported", self.site,
                        len(fresh))  # fmt: skip
            self.store.remember_urls(self.site, [(e.url, e.lastmod) for e in fresh])
            return []
        every_path = {path_of(u) for u in known} | {path_of(e.url) for e in matching}
        seen_pages = {without_language(path_of(u)) for u in known}
        items: list[Item] = []
        for e in fresh:
            path = path_of(e.url)
            page = without_language(path)
            if is_section(path, every_path) or page in seen_pages:
                continue
            seen_pages.add(page)
            items.append(
                Item(
                    ident=e.url,
                    url=e.url,
                    headline=e.title or title_from_url(e.url),
                    origin="newsroom",
                    channel=self.site,
                    published=e.published or e.lastmod,
                    publisher=self.publisher,
                    subject=self.company,
                )
            )
        self.store.remember_urls(self.site, [(e.url, e.lastmod) for e in fresh])
        return items
