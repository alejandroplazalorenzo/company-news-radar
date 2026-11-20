"""The merge step: folds shown press stories that report one event.

Candidate pairs share a company (or both have none) and lie within a year of each other.
Five tests run over them one after another; the windows live in ``config``:

    signature  headlines of one kind with the same names and figures
    fact       identical fact keys
    long_key   one bid between the same companies, or one company's results for one year
    topic      regulation, risk or results stories whose fact keys share two words
    judge      a stored "same event" verdict for the pair

Stories are joined with union-find. A join is refused when it would put different
company sets together (one set has to contain the other) or when any pair across the two
groups carries a manual "different" verdict. The gap between two groups is measured from
their date spans, which grow as members join. The heaviest story of a group keeps its
captures and parties; the rest are hidden as repeats of it.
"""

from __future__ import annotations

import json
import logging
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from itertools import combinations
from pathlib import Path
from typing import Any

from company_news_radar import config, prompts
from company_news_radar.models import TOPIC_TYPES
from company_news_radar.quota import QuotaExhausted
from company_news_radar.store import Store
from company_news_radar.textutil import normalise, without_accents, words
from company_news_radar.watchlist import Company

log = logging.getLogger(__name__)

RANK = {"high": 3, "medium": 2, "low": 1}

# words that start with a capital in a headline without being a name, by kind
_NOT_NAMES_BY_KIND = {
    "weekday": "lunes martes miercoles jueves viernes sabado domingo",
    "month": "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre"
    " diciembre",
    "relative day": "ayer hoy manana",
    "english": "and for in its of on the to with",
    "article": "el la las lo los un una unas unos",
    "preposition": "a al ante con de del desde en entre hasta para por sin sobre tras",
    "conjunction": "e o que u y",
    "pronoun or determiner": "esa ese eso esta estas este estos otra otro quien se su sus"
    " todo todos",
    "adverb": "asi como cuando donde mas muy no ya",
}
NOT_A_NAME = frozenset(w.upper() for listed in _NOT_NAMES_BY_KIND.values() for w in listed.split())
QUARTER_WORDS = frozenset("3m 6m 9m h1 h2 half q1 q2 q3 q4 quarter quarterly semester".split())
BID_WORDS = frozenset("bid opa takeover".split())
DULL_FACT_WORDS = frozenset(
    "and company for from group its into new over plan results spain spanish the with".split()
)


def signature(title: str) -> set[str]:
    """Names and numbers in a headline, normalised.

    Neighbouring capitalised words form one name, so 'Banco Sabadell' is a single entry.
    Four-digit numbers that look like years are left out.
    """
    found: set[str] = set()
    run: list[str] = []
    for raw in [*title.split(), "."]:
        token = raw.strip(".,;:!?¡¿\"'«»()[]")
        folded = normalise(token)
        if token and token[0].isupper() and folded and folded not in NOT_A_NAME:
            run.append(folded)
            if raw[-1:] not in ',;:.!?)»"':
                continue
        if run:
            found.add(" ".join(run))
            run = []
        figure = "".join(ch for ch in token if ch.isdigit())
        if figure and not (len(figure) == 4 and figure[:2] in ("19", "20")):
            found.add(figure)
    return found


def same_signature(a: set[str], b: set[str]) -> bool:
    shared = len(a & b)
    return shared >= config.SIGNATURE_MIN_SHARED and shared >= config.SIGNATURE_MIN_SHARE * min(
        len(a), len(b)
    )


def fact_words(fact: str | None) -> set[str]:
    return {w for w in (fact or "").split("-") if len(w) > 2 and not w.isdigit()} - DULL_FACT_WORDS


def long_key(fact: str | None, companies: set[str]) -> str | None:
    """A key that holds for a year: ``takeover:<companies>`` or ``results:<companies>:<year>``.

    Quarterly and half-year results get none.
    """
    parts = (fact or "").split("-")
    who = "+".join(sorted(companies))
    if not who:
        return None
    if BID_WORDS & set(parts):
        return f"takeover:{who}"
    years = [p for p in parts if len(p) == 4 and p.isdigit() and p.startswith("20")]
    if "results" in parts and years and not QUARTER_WORDS & set(parts):
        return f"results:{who}:{years[-1]}"
    return None


@dataclass
class Card:
    id: int
    kind: str
    level: str
    on_front: bool
    fact_key: str | None
    headline: str
    companies: frozenset[str]
    first: date
    last: date
    row: dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def weight(self) -> tuple[int, int, int, int]:
        """Sort key for the story that stays: front page, level, not image, oldest."""
        return (
            int(self.on_front),
            RANK.get(self.level, 0),
            int(self.kind != "image"),
            -self.first.toordinal(),
        )


CARDS_SQL = """
SELECT s.*, min(substr(c.published, 1, 10)) AS first_day,
       max(substr(c.published, 1, 10)) AS last_day
FROM story_now s JOIN capture c ON c.story_id = s.id
WHERE s.state = 'shown' AND s.origin IN ('bing_news', 'feed', 'newsroom')
GROUP BY s.id ORDER BY s.id
"""


def cards(store: Store) -> list[Card]:
    out = []
    for r in store.rows(CARDS_SQL):
        if not r["first_day"]:
            continue
        out.append(
            Card(
                id=r["id"],
                kind=r["kind"],
                level=r["level"] or "low",
                on_front=bool(r["on_front"]),
                fact_key=r["fact_key"],
                headline=r["headline"],
                companies=frozenset(store.confirmed_companies(r["id"])),
                first=date.fromisoformat(r["first_day"]),
                last=date.fromisoformat(r["last_day"]),
                row=dict(r),
            )
        )
    return sorted(out, key=lambda c: (c.first, c.id))


class Groups:
    def __init__(self, items: Iterable[Card], vetoed: set[tuple[int, int]]) -> None:
        self.parent: dict[int, int] = {}
        self.members: dict[int, set[int]] = {}
        self.companies: dict[int, frozenset[str]] = {}
        self.span: dict[int, tuple[date, date]] = {}
        for c in items:
            self.parent[c.id] = c.id
            self.members[c.id] = {c.id}
            self.companies[c.id] = c.companies
            self.span[c.id] = (c.first, c.last)
        self.vetoed = vetoed

    def root(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def gap(self, a: int, b: int) -> int:
        (s1, e1), (s2, e2) = self.span[self.root(a)], self.span[self.root(b)]
        return max(0, (s2 - e1).days, (s1 - e2).days)

    def compatible(self, a: int, b: int) -> bool:
        x, y = self.companies[self.root(a)], self.companies[self.root(b)]
        if not x or not y:
            return not x and not y
        return x <= y or y <= x

    def vetoes(self, a: int, b: int) -> bool:
        left, right = self.members[self.root(a)], self.members[self.root(b)]
        return any((min(p, q), max(p, q)) in self.vetoed for p in left for q in right)

    def join(self, a: int, b: int) -> bool:
        """Unites the two groups if allowed; True when it did."""
        ra, rb = self.root(a), self.root(b)
        if ra == rb or not self.compatible(a, b) or self.vetoes(a, b):
            return False
        self.parent[rb] = ra
        self.members[ra] |= self.members.pop(rb)
        self.companies[ra] = self.companies[ra] | self.companies.pop(rb)
        (s1, e1), (s2, e2) = self.span[ra], self.span.pop(rb)
        self.span[ra] = (min(s1, s2), max(e1, e2))
        return True


def _candidate_pairs(items: list[Card]) -> list[tuple[Card, Card]]:
    by_company: dict[str, list[Card]] = defaultdict(list)
    for c in items:
        for company in c.companies or {"-"}:
            by_company[company].append(c)
    seen: set[tuple[int, int]] = set()
    pairs = []
    for group in by_company.values():
        for x, y in combinations(group, 2):
            key = (min(x.id, y.id), max(x.id, y.id))
            if key in seen or abs((y.first - x.last).days) > config.LONG_KEY_WINDOW_DAYS:
                continue
            seen.add(key)
            pairs.append((x, y) if x.first <= y.first else (y, x))
    return sorted(pairs, key=lambda p: (p[1].first, p[0].first, p[0].id, p[1].id))


def _rules(verdicts: dict[tuple[int, int], tuple[bool, str]]) -> list[tuple[str, Any]]:
    sigs: dict[int, set[str]] = {}

    def sig(c: Card) -> set[str]:
        if c.id not in sigs:
            sigs[c.id] = signature(c.headline)
        return sigs[c.id]

    def by_signature(x: Card, y: Card, gap: int) -> bool:
        return (
            gap <= config.SIGNATURE_WINDOW_DAYS
            and x.kind == y.kind
            and same_signature(sig(x), sig(y))
        )

    def by_fact(x: Card, y: Card, gap: int) -> bool:
        return gap <= config.FACT_WINDOW_DAYS and bool(x.fact_key) and x.fact_key == y.fact_key

    def by_long_key(x: Card, y: Card, gap: int) -> bool:
        k = long_key(x.fact_key, set(x.companies))
        return (
            gap <= config.LONG_KEY_WINDOW_DAYS
            and k is not None
            and k == long_key(y.fact_key, set(y.companies))
        )

    def by_topic(x: Card, y: Card, gap: int) -> bool:
        return (
            gap <= config.TOPIC_WINDOW_DAYS
            and x.kind == y.kind
            and x.kind in TOPIC_TYPES
            and len(fact_words(x.fact_key) & fact_words(y.fact_key)) >= 2
        )

    def by_judge(x: Card, y: Card, gap: int) -> bool:
        said = verdicts.get((min(x.id, y.id), max(x.id, y.id)))
        return bool(said and said[0])

    return [
        ("signature", by_signature),
        ("fact", by_fact),
        ("long_key", by_long_key),
        ("topic", by_topic),
        ("judge", by_judge),
    ]


COPY_PARTIES = """
INSERT OR IGNORE INTO party (story_id, company, how, evidence, tax_id, confirmed)
SELECT ?, company, 'merged', evidence, tax_id, confirmed FROM party
WHERE story_id = ? AND confirmed = 1
"""
CONFIRM_COPIED = """
UPDATE party SET confirmed = 1 WHERE story_id = ? AND company IN
    (SELECT company FROM party WHERE story_id = ? AND confirmed = 1)
"""


def _apply(
    store: Store, items: list[Card], groups: Groups, joins: list[tuple[int, int, str]]
) -> None:
    by_id = {c.id: c for c in items}
    keeper_of: dict[int, int] = {}
    for members in groups.members.values():
        if len(members) > 1:
            keeper = max(members, key=lambda i: by_id[i].weight)
            keeper_of.update(dict.fromkeys(members, keeper))
    for a, b, rule in joins:
        store.do("decision.merge", a=a, b=b, kept=keeper_of[a], rule=rule)
    for story_id, keeper in keeper_of.items():
        if story_id == keeper:
            continue
        store.con.execute("UPDATE capture SET story_id = ? WHERE story_id = ?", (keeper, story_id))
        store.con.execute(COPY_PARTIES, (keeper, story_id))
        store.con.execute(CONFIRM_COPIED, (keeper, story_id))
        store.change(
            "verdict", story_id, shown=0, why_hidden=f"repeat of {keeper}", on_front=0, alerts=0
        )
    store.commit()


def merge_by_rules(store: Store) -> Counter[str]:
    verdicts = store.pair_verdicts()
    vetoed = {k for k, (same, who) in verdicts.items() if not same and who.startswith("manual")}
    items = cards(store)
    groups = Groups(items, vetoed)
    joins: list[tuple[int, int, str]] = []
    pairs = _candidate_pairs(items)
    for rule, test in _rules(verdicts):
        for x, y in pairs:
            if groups.root(x.id) == groups.root(y.id):
                continue
            if test(x, y, groups.gap(x.id, y.id)) and groups.join(x.id, y.id):
                joins.append((x.id, y.id, rule))
    _apply(store, items, groups, joins)
    return Counter(rule for _, _, rule in joins)


def name_words(companies: Iterable[Company]) -> set[str]:
    """All words in the watchlist names and aliases, so a shared company name is no clue."""
    out: set[str] = set()
    for c in companies:
        for name in (c.group, c.name, *c.registered_names, *c.aliases):
            out.update(words(name))
    return out


def headline_words(title: str, ignore: set[str]) -> set[str]:
    return {w for w in words(without_accents(title)) if len(w) >= 4 and not w.isdigit()} - ignore


def doubtful_pairs(
    items: list[Card],
    ignore: set[str],
    asked: dict[tuple[int, int], tuple[bool, str]],
    judge_version: str | None,
    *,
    need_word: bool = True,
) -> list[tuple[Card, Card]]:
    """Unmerged pairs to put to the judge.

    Both stories have the same companies (or one set inside the other), at most a day apart,
    and, with ``need_word``, at least one headline word in common outside ``ignore``. A pair
    is skipped once it has a "same" verdict, a manual verdict, or a "different" from
    ``judge_version``.
    """
    out = []
    for x, y in _candidate_pairs(items):
        if not x.companies or not (x.companies <= y.companies or y.companies <= x.companies):
            continue
        if abs((y.first - x.last).days) > config.DOUBTFUL_WINDOW_DAYS:
            continue
        said = asked.get((min(x.id, y.id), max(x.id, y.id)))
        if said and (said[0] or said[1].startswith("manual") or said[1] == judge_version):
            continue
        if need_word and not headline_words(x.headline, ignore) & headline_words(
            y.headline, ignore
        ):
            continue
        out.append((x, y))
    return out


def ask_judge(
    store: Store, companies: list[Company], judge: Any, version: str = prompts.CURRENT_JUDGE
) -> int:
    names = {c.id: c.group for c in companies}
    items = cards(store)
    pairs = doubtful_pairs(items, name_words(companies), store.pair_verdicts(), version)
    asked = 0
    for start in range(0, len(pairs), config.JUDGE_BATCH):
        batch = pairs[start : start + config.JUDGE_BATCH]
        shown = []
        for x, y in batch:
            shown.append(
                tuple(
                    {**c.row, "companies": sorted(names.get(k, k) for k in c.companies)}
                    for c in (x, y)
                )
            )
        text = prompts.judge(version, shown)  # type: ignore[arg-type]
        try:
            reply = judge(text, prompts.JUDGE_SCHEMA, f"judge-{version}", len(batch))
        except QuotaExhausted as exc:
            log.warning("judge halted by the quota: %s", exc)
            break
        except Exception as exc:
            log.warning("judge request failed, batch skipped: %s", str(exc)[:300])
            continue
        wanted = {(min(x.id, y.id), max(x.id, y.id)) for x, y in batch}
        for entry in reply.get("pairs") or []:
            if not isinstance(entry, dict) or not isinstance(entry.get("same"), bool):
                continue
            key = (
                min(entry.get("a", 0), entry.get("b", 0)),
                max(entry.get("a", 0), entry.get("b", 0)),
            )
            if key in wanted:
                store.save_pair_verdict(*key, entry["same"], f"judge-{version}")
                asked += 1
        store.commit()
    return asked


def load_manual(store: Store, path: Path | None) -> int:
    """Reads verdicts from a JSON-lines file with a, b, same and an optional note."""
    if path is None or not path.exists():
        return 0
    n = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            v = json.loads(line)
            author = f"manual: {v.get('note', '')}".strip()
            store.save_pair_verdict(int(v["a"]), int(v["b"]), bool(v["same"]), author)
            n += 1
    store.commit()
    return n


def merge(store: Store, companies: list[Company], judge: Any = None) -> dict[str, int]:
    done = merge_by_rules(store)
    if judge is not None:
        done["judged_pairs"] = ask_judge(store, companies, judge)
        done.update(merge_by_rules(store))
    return {
        k: done.get(k, 0)
        for k in ("signature", "fact", "long_key", "topic", "judge", "judged_pairs")
    }
