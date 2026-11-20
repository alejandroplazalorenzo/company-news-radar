"""Access to the SQLite file. Table layout: ``sql/schema.sql``; the write statements are
named in ``sql/named.sql`` and called through :meth:`Store.do`."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

from company_news_radar import config, models

Row = sqlite3.Row
_SQL = files("company_news_radar").joinpath("sql")
SCHEMA = _SQL.joinpath("schema.sql").read_text(encoding="utf-8")
NAMED = {
    head.strip(): body.strip()
    for head, _, body in (
        block.partition("\n")
        for block in _SQL.joinpath("named.sql").read_text(encoding="utf-8").split("-- name:")[1:]
    )
}
SCHEMA_VERSION = 1
KEY_COLUMN = {"capture": "id", "verdict": "story_id"}


def stamp() -> str:
    return f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%S}+00:00"


class Store:
    def __init__(self, path: Path | str) -> None:
        where = str(path)
        if where != ":memory:":
            Path(where).parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(where)
        self.con.row_factory = Row
        self.con.execute("PRAGMA foreign_keys = ON")
        if self.value("PRAGMA user_version") == 0:
            self.con.executescript(SCHEMA)
            self.con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def rows(self, sql: str, *args: Any) -> list[Row]:
        return self.con.execute(sql, args).fetchall()

    def row(self, sql: str, *args: Any) -> Row | None:
        first: Row | None = self.con.execute(sql, args).fetchone()
        return first

    def value(self, sql: str, *args: Any) -> Any:
        first = self.row(sql, *args)
        return None if first is None else first[0]

    def do(self, name: str, **params: Any) -> int:
        """Run a named statement; returns the new row id, if any."""
        return self.con.execute(NAMED[name], {"now": stamp(), **params}).lastrowid or 0

    def commit(self) -> None:
        self.con.commit()

    def change(self, table: str, key: int, **values: Any) -> None:
        """Sets columns of one capture (by id) or one verdict (by story id)."""
        if values:
            assignments = ", ".join(f"{column} = :{column}" for column in values)
            sql = f"UPDATE {table} SET {assignments} WHERE {KEY_COLUMN[table]} = :_row"
            self.con.execute(sql, {**values, "_row": key})

    def add_captures(self, items: Iterable[models.Item]) -> list[int]:
        """Inserts the items whose ident is new and returns their row ids."""
        when = stamp()
        added = []
        for it in items:
            params = asdict(it) | {"tax_ids": json.dumps(list(it.tax_ids)), "now": when}
            cursor = self.con.execute(NAMED["capture.add"], params)
            if cursor.rowcount:
                added.append(cursor.lastrowid or 0)
        self.con.commit()
        return added

    def capture(self, capture_id: int) -> Row | None:
        return self.row("SELECT * FROM capture WHERE id = ?", capture_id)

    def untriaged(self) -> list[Row]:
        return self.rows("SELECT * FROM capture WHERE triage IS NULL ORDER BY published, id")

    def open_story(self, capture_id: int) -> int:
        story_id = self.do("story.open", capture=capture_id)
        self.change("capture", capture_id, story_id=story_id)
        return story_id

    def story(self, story_id: int) -> Row | None:
        return self.row("SELECT * FROM story_now WHERE id = ?", story_id)

    def add_parties(self, story_id: int, found: Iterable[models.Mention]) -> None:
        rows = (asdict(m) | {"story": story_id, "now": stamp()} for m in found)
        self.con.executemany(NAMED["party.add"], rows)

    def parties(self, story_id: int) -> list[Row]:
        return self.rows("SELECT * FROM party WHERE story_id = ? ORDER BY id", story_id)

    def confirm(self, story_id: int, party_ids: set[int]) -> None:
        self.do("party.confirm", story=story_id, chosen=json.dumps(sorted(party_ids)))

    def confirmed_companies(self, story_id: int) -> set[str]:
        return {r["company"] for r in self.parties(story_id) if r["confirmed"]}

    def amount(self, story_id: int) -> float | None:
        found = self.con.execute(NAMED["story.amount"], {"story": story_id}).fetchone()
        return None if found is None else float(found[0])

    def put_verdict(self, story_id: int, decided_by: str, **fields: Any) -> None:
        values = dict.fromkeys(("why_hidden", "country", "fact_key", "gist")) | fields
        self.do("verdict.put", story=story_id, decided_by=decided_by, **values)

    def forget_verdict(self, story_id: int) -> None:
        """Deletes the verdict and the confirmations, so the story counts as new again."""
        self.con.execute("DELETE FROM verdict WHERE story_id = ?", (story_id,))
        self.con.execute("UPDATE party SET confirmed = NULL WHERE story_id = ?", (story_id,))

    def log_answer(self, story_id: int, model: str, version: str, **fields: Any) -> None:
        values = dict.fromkeys(("gist", "country", "fact_key", "why_hidden")) | fields
        values["parties"] = json.dumps(sorted(values.get("parties") or []))
        self.do("answer.add", story=story_id, model=model, version=version, **values)

    def pair_verdicts(self) -> dict[tuple[int, int], tuple[bool, str]]:
        found = self.rows(
            "SELECT first_id, second_id, same, author FROM decision WHERE act = 'verdict'"
        )
        return {(r[0], r[1]): (bool(r[2]), r[3]) for r in found}

    def save_pair_verdict(self, a: int, b: int, same: bool, author: str) -> None:
        """Manual verdicts overwrite any verdict; other verdicts never overwrite a manual one."""
        self.do("decision.verdict", a=a, b=b, same=int(same), author=author)

    def note_source(self, source: str, kind: str, *, new: int = 0, failure: str = "") -> None:
        """Appends what one source gave in this fetch: a count of new items, or an error."""
        error = failure[:300] or None
        self.do("source.checked", source=source, kind=kind, new_items=None if error else new,
                error=error)  # fmt: skip

    def health(self, idle_runs: int = config.IDLE_RUNS) -> tuple[list[Row], list[Row]]:
        """Sources whose latest check failed, and sources with nothing new in their last
        ``idle_runs`` checks."""
        failing = self.con.execute(NAMED["source.failing"]).fetchall()
        silent = self.con.execute(NAMED["source.silent"], {"runs": idle_runs}).fetchall()
        return failing, silent

    def known_urls(self, site: str) -> set[str]:
        return {a for (a,) in self.rows("SELECT address FROM sitemap_seen WHERE site = ?", site)}

    def remember_urls(self, site: str, urls: Iterable[tuple[str, str | None]]) -> None:
        when = stamp()
        rows = ({"site": site, "address": u, "lastmod": m, "now": when} for u, m in urls)
        self.con.executemany(NAMED["sitemap.add"], rows)
        self.con.commit()

    @contextmanager
    def logged_run(self, purpose: str, from_day: str | None) -> Iterator[dict[str, Any]]:
        """Writes a run_log row now and stores whatever the caller put in the dict at the end."""
        run_id = self.do("run.start", purpose=purpose, from_day=from_day)
        self.con.commit()
        report: dict[str, Any] = {}
        yield report
        self.do("run.finish", run=run_id, report=json.dumps(report, ensure_ascii=False))
        self.con.commit()

    def last_fetch(self) -> str | None:
        latest = self.con.execute(NAMED["run.last_fetch"]).fetchone()[0]
        return str(latest) if latest else None
