"""``fetch``: one task per source, downloads in a thread pool, writes in the main thread.

Every fetch reads the press search, the feeds, the newsrooms and BORME Section C; BDNS and
TED are added with ``--weekly``. Each task's outcome, new items or the exception text, goes
to ``source_check``; an exception is caught per task, so the loop carries on with the next.
Google News is never requested (``net.NEVER_ASK``).
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from itertools import zip_longest
from typing import Any

from company_news_radar import models, net, watchlist
from company_news_radar import store as storage
from company_news_radar.sources import catalogue, newsrooms, official, press

log = logging.getLogger(__name__)


@dataclass
class Task:
    name: str
    kind: str
    fetch: Callable[[], Any]  # called on a pool thread
    finish: Callable[[Any], list[models.Item]] = list  # runs in the main thread


@dataclass(frozen=True)
class Window:
    since: date
    until: date
    weekly: bool = False
    feeds: bool = True
    official_only: bool = False
    only: frozenset[str] | None = None

    @property
    def days(self) -> list[date]:
        return [self.since + timedelta(n) for n in range((self.until - self.since).days + 1)]


def borme_days(client: net.Client, reader: official.BormeC, days: list[date]) -> list[models.Item]:
    found: list[models.Item] = []
    for day in (d for d in days if d.weekday() < 5):
        try:
            found += reader.fetch(client, day)
        except net.HttpError as exc:
            if exc.status != 404:  # 404: no issue that day
                raise
            log.debug("BORME %s: no issue", day)
    return found


def search_tasks(client: net.Client, c: watchlist.Company, w: Window) -> Iterator[Task]:
    start = datetime.combine(w.since, time(), tzinfo=UTC)
    for k, q in enumerate(press.queries(c.search_names)):
        channel = press.Channel(f"bing:{c.id}:{k}", None, "bing_news", c.id)
        yield Task(
            channel.name,
            "bing_news",
            lambda q=q, ch=channel: press.Search(q, ch, start).run(client),
        )


def newsroom_tasks(
    store: storage.Store, client: net.Client, c: watchlist.Company
) -> Iterator[Task]:
    for k, entry in enumerate(c.newsrooms):
        site, shape = f"newsroom:{c.id}:{k}", entry.get("type", "sitemap")
        if shape == "feed":
            channel = press.Channel(site, c.group, "newsroom", c.id)
            yield Task(
                site, "newsroom", lambda u=entry["url"], ch=channel: press.read_feed(client, u, ch)
            )
            continue
        room = newsrooms.Newsroom(store, site, c.id, c.group)
        yield Task(
            site,
            "newsroom",
            lambda u=entry["url"]: newsrooms.read_sitemap(client, u),
            lambda read, r=room, e=entry: r.new_pages(
                read, whole=e.get("type") == "news_sitemap", path_filter=e.get("filter")
            ),
        )


def plan(
    store: storage.Store, client: net.Client, companies: list[watchlist.Company], w: Window
) -> list[Task]:
    """All tasks, interleaved by kind so that no single host holds up the pool."""
    lanes: dict[str, list[Task]] = {}
    if not w.official_only:
        lanes["bing_news"] = [t for c in companies for t in search_tasks(client, c, w)]
        lanes["newsroom"] = [t for c in companies for t in newsroom_tasks(store, client, c)]
        lanes["feed"] = [
            Task(
                f"feed:{f.slug}",
                "feed",
                lambda f=f: press.read_feed(
                    client, f.url, press.Channel(f"feed:{f.slug}", f.outlet)
                ),
            )
            for f in (catalogue.FEEDS if w.feeds else ())
        ]
    reader = official.BormeC(
        {official.name_key(n): c.id for c in companies for n in c.all_registered_names}
    )
    lanes["borme_c"] = [Task("borme_c", "borme_c", lambda: borme_days(client, reader, w.days))]
    if w.weekly:
        payer = {c.tax_id: c.id for c in companies if c.tax_id}
        lanes["bdns"] = [
            Task(f"bdns:{who}", "bdns", lambda t=t, who=who: official.bdns(client, t, who, w.since))
            for t, who in sorted(payer.items())
        ]
        lanes["ted"] = [Task("ted", "ted", lambda: official.ted(client, payer, w.since))]
    kept = [lane for kind, lane in lanes.items() if w.only is None or kind in w.only]
    return [t for row in zip_longest(*kept) for t in row if t is not None]


def extract(
    store: storage.Store,
    client: net.Client,
    companies: list[watchlist.Company],
    w: Window,
    workers: int = 4,
) -> dict[str, Any]:
    tasks = plan(store, client, companies, w)
    added: Counter[str] = Counter()
    failed: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        running = [(t, pool.submit(t.fetch)) for t in tasks]
        for task, future in running:
            try:
                new = store.add_captures(task.finish(future.result()))
            except Exception as exc:  # any error stays inside its own source
                failed[task.name] = f"{type(exc).__name__}: {str(exc)[:200]}"
                log.warning("source %s skipped: %s", task.name, failed[task.name])
                store.note_source(task.name, task.kind, failure=failed[task.name])
            else:
                added[task.kind] += len(new)
                store.note_source(task.name, task.kind, new=len(new))
            store.commit()
    return {
        "since": w.since.isoformat(),
        "until": w.until.isoformat(),
        "tasks": len(tasks),
        "new_items": sum(added.values()),
        "new_by_source": dict(sorted(added.items())),
        "failed_sources": failed,
        "never_asked": sorted(net.NEVER_ASK),
        "left_out_feeds": [name for name, _ in catalogue.left_out()],
        **client.summary(),
    }
