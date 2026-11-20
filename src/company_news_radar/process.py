"""Turns new captures into stories. No model is called here.

Every waiting capture gets its parties (the watched companies it names) and a triage outcome:
``kept`` or the name of the check that removed it. Kept press captures without a standfirst
get one from the article page when a client is given. Each kept capture then joins an
existing story when it repeats one almost word for word, or opens a story of its own.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from company_news_radar import config, filters
from company_news_radar.entities import Dictionary
from company_news_radar.models import OFFICIAL, Mention
from company_news_radar.net import Client, HttpError
from company_news_radar.sources.press import standfirst
from company_news_radar.store import Row, Store
from company_news_radar.textutil import day_of, normalise

log = logging.getLogger(__name__)

KEPT = "kept"


@dataclass
class Capture:
    id: int
    origin: str
    headline: str
    url: str
    published: str | None
    standfirst: str | None
    publisher_host: str | None
    subject: str | None
    tax_ids: list[str]
    story_id: int | None

    @classmethod
    def of(cls, row: Row) -> Capture:
        wanted = cls.__dataclass_fields__
        values: dict[str, Any] = {k: row[k] for k in row.keys() if k in wanted}  # noqa: SIM118
        values["tax_ids"] = json.loads(values["tax_ids"] or "[]")
        return cls(**values)

    @property
    def text(self) -> str:
        return f"{self.headline} {self.standfirst or ''}"

    @property
    def official(self) -> bool:
        return self.origin in OFFICIAL


def link(d: Dictionary, c: Capture) -> list[Mention]:
    if c.official:
        by_tax_id = [Mention(d.tax_ids[t], "tax_id", t, t) for t in c.tax_ids if t in d.tax_ids]
        if c.subject is None or c.subject in {m.company for m in by_tax_id}:
            return by_tax_id
        return [*by_tax_id, Mention(c.subject, "name", normalise(c.headline)[:80])]
    found = d.find(c.text)
    if c.subject and c.subject not in {m.company for m in found}:
        found.append(Mention(c.subject, "query" if c.origin == "bing_news" else "newsroom"))
    return found


Check = Callable[[Dictionary, Capture, list[Mention]], bool]
# tried top to bottom; the first one that is true names the triage outcome
CHECKS: list[tuple[str, Check]] = [
    ("foreign outlet", lambda d, c, ms: filters.foreign_outlet(c.publisher_host)),
    ("homonym phrase", lambda d, c, ms: bool(c.subject) and d.homonym_in(c.subject, c.text)),
    (
        "names no watched company",
        lambda d, c, ms: not filters.worth_keeping(c.origin, ms, c.subject),
    ),
    (
        "not named in headline or snippet",
        lambda d, c, ms: c.origin == "bing_news" and {m.how for m in ms} == {"query"},
    ),
]


def triage(d: Dictionary, c: Capture, mentions: list[Mention]) -> str:
    if c.official:
        return KEPT
    failed = next((name for name, holds in CHECKS if holds(d, c, mentions)), None)
    return failed or filters.market_noise(c.headline, bool(d.find(c.headline))) or KEPT


@dataclass
class RepeatIndex:
    url_owner: dict[str, int] = field(default_factory=dict)
    by_day: dict[int, list[tuple[str, int]]] = field(default_factory=lambda: defaultdict(list))

    def add(self, story_id: int, headline: str, url: str, published: str | None) -> None:
        self.url_owner.setdefault(url, story_id)
        if (day := day_of(published)) is not None:
            self.by_day[day.toordinal()].append((normalise(headline), story_id))

    def match(self, headline: str, url: str, published: str | None) -> int | None:
        """Story with this address, else the most similar headline close in time."""
        day = day_of(published)
        if url in self.url_owner or day is None:
            return self.url_owner.get(url)
        wanted = normalise(headline)
        reach = config.REPEAT_DAYS
        near = range(day.toordinal() - reach, day.toordinal() + reach + 1)
        scored = []
        for other, story_id in (pair for d in near for pair in self.by_day.get(d, ())):
            sm = SequenceMatcher(None, wanted, other)
            if sm.real_quick_ratio() >= config.HEADLINE_SIMILARITY:
                scored.append((sm.ratio(), -story_id))
        best = max(scored, default=(0.0, 0))
        return -best[1] if best[0] >= config.HEADLINE_SIMILARITY else None


def read_pages(store: Store, client: Client, bare: list[Capture], workers: int = 6) -> int:
    """Fills standfirsts from article pages; a newsroom capture also takes the page title."""

    def fetch(c: Capture) -> tuple[Capture, tuple[str | None, str | None]]:
        try:
            return c, standfirst(client, c.url)
        except HttpError as exc:
            log.debug("no page head for %s (%s)", c.url, exc)
            return c, (None, None)

    filled = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for c, (title, summary) in pool.map(fetch, bare):
            changes: dict[str, Any] = {"page_read": 1}
            if summary:
                changes["standfirst"] = summary
            if title and c.origin == "newsroom":
                changes["headline"] = title
            store.change("capture", c.id, **changes)
            filled += bool(summary)
    store.commit()
    return filled


def process(store: Store, d: Dictionary, client: Client | None) -> dict[str, int]:
    stats: Counter[str] = Counter()
    waiting = [Capture.of(r) for r in store.untriaged()]
    stats["items_seen"] = len(waiting)
    kept: list[int] = []
    for c in waiting:
        outcome = triage(d, c, link(d, c))
        store.change("capture", c.id, triage=outcome)
        if outcome == KEPT:
            kept.append(c.id)
        else:
            stats[outcome] += 1
    stats["passed"] = len(kept)
    store.commit()
    if client is not None:
        chosen = set(kept)
        bare = [c for c in waiting if c.id in chosen and not c.standfirst and not c.official]
        stats["standfirsts"] = read_pages(store, client, bare)
    index = RepeatIndex()
    for s in store.rows("SELECT id, headline, url, published FROM story WHERE record_type IS NULL"):
        index.add(s["id"], s["headline"], s["url"], s["published"])
    for capture_id in kept:
        row = store.capture(capture_id)
        c = Capture.of(row) if row is not None else None
        if c is None or c.story_id is not None:
            continue
        target = None if c.official else index.match(c.headline, c.url, c.published)
        if target is None:
            target = store.open_story(c.id)
            stats["new_stories"] += 1
            if not c.official:
                index.add(target, c.headline, c.url, c.published)
        else:
            store.change("capture", c.id, story_id=target)
            stats["joined_exact"] += 1
        store.add_parties(target, link(d, c))
    store.commit()
    return dict(stats)
