"""Offline checks of thresholds against the local store (no network, no LLM).

``repeats`` replays the exact-repeat fold of process.py over the kept press captures for a
grid of headline-similarity cuts and day windows. Two signals from stored data judge a fold:
the two captures name disjoint company sets (the fold is wrong), or the merge step later put
their stories together anyway (the fold only saved work).

``calibration`` counts, in the feed corpus, how often each one-word company name of the
watchlist appears and how often it is written in lower case: what the calibration of
derived keys looks at.

``filters_section`` gives the figures behind the other re-derived values: register amounts,
the domains of the press-search publishers, and what the dropped body-only matches look like.
"""

from __future__ import annotations

import argparse
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from company_news_radar import config, entities, filters
from company_news_radar.entities import Dictionary
from company_news_radar.process import Capture, RepeatIndex, link
from company_news_radar.store import Store
from company_news_radar.textutil import day_of, host, normalise, without_accents
from company_news_radar.watchlist import Company

CUTS = (0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
WINDOWS = (1, 2, 4, 7)
BANDS = (0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)
REACH = 7
OUTCOMES = (
    "disjoint companies",
    "same story in the end",
    "kept apart by the merge step",
    "one of them hidden",
)


@dataclass
class Seen:
    order: int
    capture: Capture
    text: str
    day: int | None
    companies: frozenset[str]
    final_story: int
    shown: bool


def kept_press(store: Store, d: Dictionary) -> list[Seen]:
    """Kept press captures in the order process.py read them."""
    shown = {r[0] for r in store.rows("SELECT id FROM story_now WHERE state = 'shown'")}
    rows = store.rows(
        "SELECT * FROM capture WHERE triage = 'kept' AND record_type IS NULL ORDER BY published, id"
    )
    out = []
    for n, r in enumerate(rows):
        c = Capture.of(r)
        day = day_of(c.published)
        out.append(
            Seen(
                n,
                c,
                normalise(c.headline),
                day.toordinal() if day else None,
                frozenset(m.company for m in link(d, c)),
                r["story_id"],
                r["story_id"] in shown,
            )
        )
    return out


def similarities(seen: list[Seen], floor: float = BANDS[0]) -> dict[tuple[int, int], float]:
    """Similarity of every pair at most REACH days apart and at least ``floor`` similar.

    Keys are (later, earlier) positions in reading order; the later headline is compared
    against the earlier one, the same way round as process.RepeatIndex does it.
    """
    by_day: dict[int, list[Seen]] = defaultdict(list)
    for s in seen:
        if s.day is not None:
            by_day[s.day].append(s)
    found: dict[tuple[int, int], float] = {}
    sm = SequenceMatcher(None)
    for earlier in seen:
        if earlier.day is None:
            continue
        sm.set_seq2(earlier.text)  # indexed once, compared with every later headline
        days = range(earlier.day - REACH, earlier.day + REACH + 1)
        for later in (o for day in days for o in by_day.get(day, ())):
            if later.order <= earlier.order:
                continue
            sm.set_seq1(later.text)
            if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
                continue
            ratio = sm.ratio()
            if ratio >= floor:
                found[(later.order, earlier.order)] = ratio
    return found


def replay(
    seen: list[Seen], sims: dict[tuple[int, int], float], cut: float, window: int
) -> dict[int, int]:
    """Position of each folded capture -> position of the capture that opened its story."""
    url_owner: dict[str, int] = {}
    openers: dict[int, list[int]] = defaultdict(list)
    folded: dict[int, int] = {}
    for s in seen:
        c = s.capture
        if c.url in url_owner or s.day is None:
            target = url_owner.get(c.url)
        else:
            near = (o for g in range(-window, window + 1) for o in openers.get(s.day + g, ()))
            scored = [(sims.get((s.order, o), 0.0), -o) for o in near]
            best = max(scored, default=(0.0, 0))
            target = -best[1] if best[0] >= cut else None
        if target is None:
            url_owner.setdefault(c.url, s.order)
            if s.day is not None:
                openers[s.day].append(s.order)
        else:
            folded[s.order] = target
    return folded


def replay_as_process(seen: list[Seen]) -> dict[int, int]:
    """The same fold through process.RepeatIndex, at the configured setting."""
    index = RepeatIndex()
    folded: dict[int, int] = {}
    for s in seen:
        c = s.capture
        target = index.match(c.headline, c.url, c.published)
        if target is None:
            index.add(s.order, c.headline, c.url, c.published)
        else:
            folded[s.order] = target
    return folded


def outcome(a: Seen, b: Seen) -> str:
    if a.companies and b.companies and not a.companies & b.companies:
        return OUTCOMES[0]
    if a.final_story == b.final_story:
        return OUTCOMES[1]
    if a.shown and b.shown:
        return OUTCOMES[2]
    return OUTCOMES[3]


def _cells(counts: Counter[str]) -> str:
    return " | ".join(str(counts[k]) for k in OUTCOMES)


def repeats(store: Store, d: Dictionary) -> list[str]:
    seen = kept_press(store, d)
    sims = similarities(seen)
    stories = store.value("SELECT count(*) FROM story WHERE record_type IS NULL")
    base = replay(seen, sims, config.HEADLINE_SIMILARITY, config.REPEAT_DAYS)
    same_as_process = base == replay_as_process(seen)
    head = " | ".join(OUTCOMES)
    lines = [
        "## Exact repeats: headline similarity and day window",
        "",
        f"Kept press captures: {len(seen)} in {stories} press stories, so "
        f"{len(seen) - stories} were folded. Replaying the current setting "
        f"({config.HEADLINE_SIMILARITY} within {config.REPEAT_DAYS} days) folds {len(base)} "
        f"(through process.RepeatIndex: {'the same' if same_as_process else 'DIFFERENT'}).",
        "",
        "Folds per setting. The outcome columns describe the folds that setting makes and the "
        "current one does not (Extra); Lost counts the current folds it does not make, and how "
        "many of those joined disjoint companies. Companies are those the linker finds in "
        "each capture.",
        "",
        f"| Cut | Days | Folds | Extra | {head} | Lost | Lost, disjoint companies |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for cut in CUTS:
        for window in WINDOWS:
            folds = replay(seen, sims, cut, window)
            extra = Counter(outcome(seen[k], seen[t]) for k, t in folds.items() if k not in base)
            lost = [k for k in base if k not in folds]
            wrong = sum(outcome(seen[k], seen[base[k]]) == OUTCOMES[0] for k in lost)
            lines.append(
                f"| {cut:.2f} | {window} | {len(folds)} | {sum(extra.values())} | "
                f"{_cells(extra)} | {len(lost)} | {wrong} |"
            )
    now = Counter(outcome(seen[k], seen[t]) for k, t in base.items())
    lines += [
        "",
        f"The {len(base)} folds of the current setting: "
        + ", ".join(f"{k} {now[k]}" for k in OUTCOMES)
        + ".",
        "",
        f"Every pair of kept press captures up to {REACH} days apart, by headline similarity, "
        "whatever the fold did:",
        "",
        f"| Similarity | Pairs | {head} |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    by_band: dict[int, Counter[str]] = defaultdict(Counter)
    by_gap: dict[int, Counter[str]] = defaultdict(Counter)
    for (a, b), ratio in sims.items():
        band = max(k for k, lo in enumerate(BANDS) if ratio >= lo)
        verdict = outcome(seen[a], seen[b])
        by_band[band][verdict] += 1
        if ratio >= config.HEADLINE_SIMILARITY:
            gap = abs((seen[a].day or 0) - (seen[b].day or 0))
            by_gap[gap][verdict] += 1
    for k, lo in enumerate(BANDS):
        hi = BANDS[k + 1] if k + 1 < len(BANDS) else 1.0
        lines.append(f"| {lo:.2f}-{hi:.2f} | {sum(by_band[k].values())} | {_cells(by_band[k])} |")
    lines += [
        "",
        f"Pairs at {config.HEADLINE_SIMILARITY} or more, by days apart:",
        "",
        f"| Days apart | Pairs | {head} |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for gap in range(REACH + 1):
        lines.append(f"| {gap} | {sum(by_gap[gap].values())} | {_cells(by_gap[gap])} |")
    return [*lines, ""]


def calibration(store: Store, companies: list[Company], texts_sql: str) -> list[str]:
    texts = [r[0] for r in store.rows(texts_sql)]
    names: set[str] = set()
    for c in companies:
        for n in (c.group, *c.aliases, *map(entities.strip_legal_form, c.all_registered_names)):
            key = normalise(n)
            if " " not in key and len(key) >= 3 and key not in entities.GENERIC:
                names.add(key)
    d = Dictionary()
    for key in names:
        d.add(key, key, explicit=False)
    lower, matched = entities.word_counts(d, texts)
    derived = {p for p in entities.build(companies).phrases(explicit=False) if " " not in p}
    limit = max(config.CALIBRATION_FLOOR, config.CALIBRATION_MAX_SHARE * len(texts))
    lines = [
        "## Calibration of derived one-word keys",
        "",
        f"Corpus: {len(texts)} feed captures. One-word company names in the watchlist (three "
        f"letters or more, not generic): {len(names)}. Derived one-word keys in use: "
        f"{', '.join(sorted(derived)) or 'none'}; the other names are aliases, or shorter than "
        f"{config.MIN_ONE_WORD_LETTERS} letters, and the calibration never touches them.",
        f"Current setting: a derived key goes when {config.CALIBRATION_MIN_LOWERCASE} or more "
        f"texts write it in lower case, or when it matches more than {limit:g} texts "
        f"(the larger of {config.CALIBRATION_FLOOR} and {config.CALIBRATION_MAX_SHARE} x "
        f"{len(texts)}). The last column applies that test to every name, as if all were "
        "derived.",
        "",
        "| Name | Letters | Texts in lower case | Texts matched | Share | Would go |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for key in sorted(names, key=lambda k: (-matched[k], k)):
        goes = lower[key] >= config.CALIBRATION_MIN_LOWERCASE or matched[key] > limit
        share = matched[key] / len(texts) if texts else 0.0
        lines.append(
            f"| {key} | {len(key)} | {lower[key]} | {matched[key]} | {share:.2%} | "
            f"{'yes' if goes else 'no'} |"
        )
    lines += [
        "",
        "Derived one-word keys for each minimum length of a one-word key (the current one is "
        f"{config.MIN_ONE_WORD_LETTERS}); a key the calibration keeps stays in the linker:",
        "",
        "| Minimum letters | Derived one-word keys | Kept by the calibration |",
        "|---:|---|---|",
    ]
    for letters in range(3, 7):
        found = entities.build(companies, min_letters=letters).phrases(explicit=False)
        keys = sorted(p for p in found if " " not in p)
        kept = [
            k for k in keys if lower[k] < config.CALIBRATION_MIN_LOWERCASE and matched[k] <= limit
        ]
        lines.append(f"| {letters} | {', '.join(keys) or '-'} | {', '.join(kept) or '-'} |")
    return [*lines, ""]


def _percentiles(amounts: list[float]) -> str:
    if len(amounts) < 2:
        return "-"
    q = statistics.quantiles(amounts, n=100, method="inclusive")
    picks = {"p10": q[9], "p25": q[24], "median": statistics.median(amounts), "p75": q[74]}
    picks["p90"] = q[89]
    return ", ".join(f"{k} {v:,.0f}" for k, v in picks.items())


MARKET_WORDS = re.compile(
    r"\b(?:ibex|bolsas?|selectivo|mercados?|cotiza\w*|acciones|valores|wall street"
    r"|dividendo\w*|analistas?|precio objetivo)\b"
)


def filters_section(store: Store) -> list[str]:
    lines = ["## Figures behind the other re-derived values", ""]
    for kind, floor in (("grant", config.GRANT_FLOOR_EUR), ("contract", config.CONTRACT_FLOOR_EUR)):
        rows = store.rows("SELECT amount_eur, subject FROM capture WHERE record_type = ?", kind)
        amounts = [float(r[0]) for r in rows if r[0]]
        lines.append(
            f"- {kind} records: {len(rows)} for {len({r[1] for r in rows})} companies, "
            f"{len(amounts)} with an amount; {_percentiles(amounts)} EUR "
            "(statistics.quantiles, inclusive; statistics.median); below the floor of "
            f"{floor:,} EUR: {sum(a < floor for a in amounts)}."
        )
    tlds = Counter(
        host(r[0]).rsplit(".", 1)[-1]
        for r in store.rows("SELECT publisher_host FROM capture WHERE origin = 'bing_news'")
        if host(r[0])
    )
    lines.append(
        "- press-search captures by publisher top-level domain: "
        + ", ".join(f".{t} {n}" for t, n in tlds.most_common())
        + f"; dropped as foreign: {', '.join(sorted(config.FOREIGN_CCTLDS))}."
    )
    body_only = [
        r[0]
        for r in store.rows(
            "SELECT headline FROM capture WHERE triage = 'not named in headline or snippet'"
        )
    ]
    market = [h for h in body_only if MARKET_WORDS.search(without_accents(h).lower())]
    lines.append(
        "- search results dropped because headline and snippet name no watched company: "
        f"{len(body_only)}; with a stock-market word in the headline: {len(market)} "
        f"(words: `{MARKET_WORDS.pattern}`)."
    )
    noise = sum(1 for h in body_only if filters.market_noise(h, False))
    lines.append(
        f"- of those, also matched by the share-price or session patterns: {noise} (the "
        "triage checks names first, so none of them reached those patterns)."
    )
    return [*lines, ""]


def report(args: argparse.Namespace, store: Store, companies: list[Company]) -> list[str]:
    from company_news_radar import cli

    d = cli.dictionary(store, companies)
    return [
        *repeats(store, d),
        *calibration(store, companies, cli.CALIBRATION_TEXTS),
        *filters_section(store),
    ]


def add_command(sub: Any) -> None:
    t = sub.add_parser("tuning-report", help="check thresholds on the stored data (offline)")
    t.add_argument("--out", type=Path, default=Path("results/tuning.md"))
