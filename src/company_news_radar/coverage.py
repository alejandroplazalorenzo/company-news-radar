"""E1, coverage against the Companies Register.

The reference is the set of company acts (not officer acts) that BORME Section A published
for the watched companies, taken from a borme-radar database opened read-only
(https://github.com/alejandroplazalorenzo/borme-radar). An act counts as seen when a shown
story of its company is dated from ``BEFORE_DAYS`` before to ``AFTER_DAYS`` after it; the
lead time is the gap to the earliest such story.

Big listed groups make the news nearly every day, so that loose test passes almost always.
Two harder versions are reported next to it: ``strict`` asks for a story kind that fits the
act (see ``COMPATIBLE``), and ``one_to_one`` lets a story be credited to a single act.
Every figure is split into press and register stories.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from company_news_radar.models import OFFICIAL
from company_news_radar.store import Store
from company_news_radar.textutil import normalise
from company_news_radar.watchlist import Company

BEFORE_DAYS = 180
AFTER_DAYS = 30

# act type in borme-radar -> story kinds that can report it
COMPATIBLE: dict[str, frozenset[str]] = {
    **dict.fromkeys(
        (
            "merger",
            "split",
            "global_asset_transfer",
            "merger_project",
            "split_project",
            "global_transfer_project",
            "sole_shareholder_declared",
            "sole_shareholder_lost",
            "sole_shareholder_change",
        ),
        frozenset({"deal", "corporate"}),
    ),
    **dict.fromkeys(
        ("capital_increase", "capital_reduction", "bond_issue"), frozenset({"capital"})
    ),
    **dict.fromkeys(
        ("name_change", "business_purpose_change", "transformation"), frozenset({"corporate"})
    ),
    "address_change": frozenset({"corporate", "footprint"}),
    **dict.fromkeys(("branch_opening", "branch_closure"), frozenset({"footprint"})),
    **dict.fromkeys(("dissolution", "extinction"), frozenset({"risk", "deal", "corporate"})),
    "insolvency": frozenset({"risk"}),
}
# not scored: acts about officers, and acts no story kind describes
OFFICER_ACTS = frozenset({"appointment", "revocation", "reelection", "officer_removal"})
LEFT_OUT_ACTS = frozenset(
    {
        "bylaws_amendment",
        "unexecuted_capital_increase",
        "powers_change",
        "website",
        "erratum",
        "ex_officio_cancellation",
        "other",
        "officer acts (appointments, removals, re-elections)",
    }
)
REQUIRED = {
    "groups": {"group_id", "name"},
    "companies": {"company_id", "group_id", "name"},
    "announcements": {"document_id", "number", "pub_date", "company_id", "kept_as"},
    "acts": {"document_id", "number", "act_type"},
}


@dataclass(frozen=True)
class Act:
    company: str
    pub_date: date
    act_type: str


@dataclass(frozen=True)
class Seen:
    act: Act
    any_first: date | None
    any_source: str | None
    strict_first: date | None
    strict_source: str | None

    @property
    def ahead_any(self) -> int | None:
        return (self.act.pub_date - self.any_first).days if self.any_first else None

    @property
    def ahead_strict(self) -> int | None:
        return (self.act.pub_date - self.strict_first).days if self.strict_first else None


def open_readonly(path: Path) -> sqlite3.Connection:
    if not path.exists():
        raise SystemExit(f"no file at {path}; pass the borme-radar SQLite file")
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    for table, cols in REQUIRED.items():
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if not cols <= have:
            raise SystemExit(f"{path}: table {table} has no column(s) {sorted(cols - have)}")
    return con


def registry_acts(
    con: sqlite3.Connection, companies: list[Company], start: date, end: date
) -> list[Act]:
    """Scored acts in the period; the company is found by group name first, then by name."""
    by_group = {normalise(c.group): c.id for c in companies}
    by_name = {normalise(n): c.id for c in companies for n in c.all_registered_names}
    rows = con.execute(
        """SELECT g.name AS grp, c.name AS company, n.pub_date, a.act_type
        FROM acts a JOIN announcements n ON n.document_id = a.document_id AND n.number = a.number
        JOIN companies c ON c.company_id = n.company_id JOIN groups g ON g.group_id = c.group_id
        WHERE n.kept_as = 'watched' AND n.pub_date BETWEEN ? AND ?""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    acts = set()
    for r in rows:
        if r["act_type"] not in COMPATIBLE:
            continue
        cid = by_group.get(normalise(r["grp"])) or by_name.get(normalise(r["company"]))
        if cid:
            acts.add(Act(cid, date.fromisoformat(r["pub_date"][:10]), r["act_type"]))
    return sorted(acts, key=lambda a: (a.pub_date, a.company, a.act_type))


def left_out_acts(
    con: sqlite3.Connection, companies: list[Company], start: date, end: date
) -> Counter[str]:
    """Counts of the acts left out of the score, per act type."""
    names = {normalise(c.group) for c in companies} | {
        normalise(n) for c in companies for n in c.all_registered_names
    }
    rows = con.execute(
        """SELECT g.name AS grp, c.name AS company, a.act_type FROM acts a
        JOIN announcements n ON n.document_id = a.document_id AND n.number = a.number
        JOIN companies c ON c.company_id = n.company_id JOIN groups g ON g.group_id = c.group_id
        WHERE n.kept_as = 'watched' AND n.pub_date BETWEEN ? AND ?""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    out: Counter[str] = Counter()
    for r in rows:
        if r["act_type"] in COMPATIBLE:
            continue
        if normalise(r["grp"]) in names or normalise(r["company"]) in names:
            out["officer acts" if r["act_type"] in OFFICER_ACTS else r["act_type"]] += 1
    return out


def stories_by_company(store: Store) -> dict[str, list[tuple[date, str, str, int]]]:
    """For each confirmed company: (date, kind, 'official' or 'press', story id) per capture.

    Captures of hidden repeats count for the story they were folded into.
    """
    out: dict[str, list[tuple[date, str, str, int]]] = {}
    rows = store.con.execute(
        """SELECT s.id, s.kind, s.origin, c.published, p.company FROM story_now s
        JOIN party p ON p.story_id = s.id AND p.confirmed = 1
        JOIN capture c ON c.story_id = s.id
        WHERE s.state = 'shown' AND c.published IS NOT NULL"""
    ).fetchall()
    for r in rows:
        where = "official" if r["origin"] in OFFICIAL else "press"
        out.setdefault(r["company"], []).append(
            (date.fromisoformat(r["published"][:10]), r["kind"], where, r["id"])
        )
    return out


def evaluate(
    acts: list[Act], stories: dict[str, list[tuple[date, str, str, int]]], source: str | None
) -> list[Seen]:
    out = []
    for act in acts:
        lo, hi = (
            act.pub_date - timedelta(days=BEFORE_DAYS),
            act.pub_date + timedelta(days=AFTER_DAYS),
        )
        window = [
            s
            for s in stories.get(act.company, [])
            if lo <= s[0] <= hi and (source is None or s[2] == source)
        ]
        strict = [s for s in window if s[1] in COMPATIBLE[act.act_type]]
        first_any = min(window, default=None, key=lambda s: s[0])
        first_strict = min(strict, default=None, key=lambda s: s[0])
        out.append(
            Seen(
                act,
                first_any[0] if first_any else None,
                first_any[2] if first_any else None,
                first_strict[0] if first_strict else None,
                first_strict[2] if first_strict else None,
            )
        )
    return out


def window_ids(
    act: Act, stories: dict[str, list[tuple[date, str, str, int]]], source: str | None
) -> set[int]:
    lo, hi = act.pub_date - timedelta(days=BEFORE_DAYS), act.pub_date + timedelta(days=AFTER_DAYS)
    return {
        sid
        for d, _, src, sid in stories.get(act.company, [])
        if lo <= d <= hi and (source is None or src == source)
    }


def one_to_one(
    acts: list[Act], stories: dict[str, list[tuple[date, str, str, int]]], source: str | None
) -> dict[Act, date | None]:
    """Greedy matching: in date order, each act takes the nearest fitting story not yet used.

    Ties go to the earlier story. The result is a bound, not an optimal assignment.
    """
    used: set[int] = set()
    out: dict[Act, date | None] = {}
    for act in sorted(acts, key=lambda a: (a.pub_date, a.company, a.act_type)):
        lo = act.pub_date - timedelta(days=BEFORE_DAYS)
        hi = act.pub_date + timedelta(days=AFTER_DAYS)
        best: dict[int, date] = {}
        for d, kind, src, sid in stories.get(act.company, []):
            if sid in used or not lo <= d <= hi or kind not in COMPATIBLE[act.act_type]:
                continue
            if source is not None and src != source:
                continue
            gap = abs((d - act.pub_date).days)
            if sid not in best or gap < abs((best[sid] - act.pub_date).days):
                best[sid] = d
        if not best:
            out[act] = None
            continue
        sid, d = min(best.items(), key=lambda kv: (abs((kv[1] - act.pub_date).days), kv[1], kv[0]))
        used.add(sid)
        out[act] = d
    return out


def median(values: list[int]) -> float | None:
    if not values:
        return None
    s = sorted(values)
    mid = len(s) // 2
    return float(s[mid]) if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
