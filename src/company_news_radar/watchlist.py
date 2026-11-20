"""Reads the watchlist CSV and, if given, the newsroom JSON.

CSV columns: id, group, name, tax_id, tax_id_source, registered_names, aliases, exclude,
website. The three list columns separate values with ``|``. ``registered_names`` holds
former or extra names in the Registro; BORME Section C is matched on them as on ``name``.
``aliases`` are typed into the CSV by whoever keeps the watchlist and reach the linker
untouched, whereas the keys built from ``group`` and the registered names have to pass
``entities.distinguishes``; aliases are company names, never people's. ``exclude`` lists
phrases showing that a text is about something else with the same name, such as a league.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, replace
from pathlib import Path


@dataclass(frozen=True)
class Company:
    id: str
    group: str
    name: str
    tax_id: str | None = None
    tax_id_source: str | None = None
    registered_names: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()
    exclude: tuple[str, ...] = ()
    website: str | None = None
    newsrooms: tuple[dict[str, str], ...] = ()

    @property
    def search_names(self) -> list[str]:
        return list(dict.fromkeys(self.aliases or (self.group,)))

    @property
    def all_registered_names(self) -> list[str]:
        return list(dict.fromkeys((self.name, *self.registered_names)))


def _cells(row: dict[str, str | None], column: str) -> tuple[str, ...]:
    return tuple(v.strip() for v in (row.get(column) or "").split("|") if v.strip())


def _cell(row: dict[str, str | None], column: str) -> str | None:
    return (row.get(column) or "").strip() or None


def load(path: Path) -> list[Company]:
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    ids = [_cell(r, "id") for r in rows]
    if None in ids or len(set(ids)) != len(ids):
        raise ValueError(f"{path}: ids must be present and unique")
    return [
        Company(
            str(cid),
            str(_cell(r, "group")),
            str(_cell(r, "name")),
            (_cell(r, "tax_id") or "").upper().replace("-", "") or None,
            _cell(r, "tax_id_source"),
            _cells(r, "registered_names"),
            _cells(r, "aliases"),
            _cells(r, "exclude"),
            _cell(r, "website"),
        )
        for cid, r in zip(ids, rows, strict=True)
    ]


def load_newsrooms(path: Path | None) -> dict[str, list[dict[str, str]]]:
    """Newsroom entries per company id; keys starting with '_' are notes and are skipped."""
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def with_newsrooms(
    companies: list[Company], config: dict[str, list[dict[str, str]]]
) -> list[Company]:
    return [replace(c, newsrooms=tuple(config.get(c.id, []))) for c in companies]
