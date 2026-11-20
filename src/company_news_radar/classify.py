"""The classify step.

Register stories get their verdict straight from the record (and are hidden when the amount
is under the floor). Press stories are sent to the model in batches; an answer that breaks
the schema is ignored and the story waits for the next run. The run ends early on a quota
refusal or after a set number of failed batches in a row.

``decide`` turns an answer into the stored verdict: whether the story is shown, its final
level, and whether it reaches the front page or raises an alert.
"""

from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from company_news_radar import config, filters, models, prompts, textutil, watchlist
from company_news_radar import store as storage
from company_news_radar.quota import QuotaExhausted

log = logging.getLogger(__name__)

LLM = Callable[[str, dict[str, Any], str, int], dict[str, Any]]
SPAIN = frozenset({"", "ES", "ESPANA", "SPAIN", "SPANISH"})
NO_PARTY_NEEDED = frozenset({"image", "regulation"})


def in_spain(country: str | None) -> bool:
    return textutil.normalise(country) in SPAIN


@dataclass(frozen=True)
class Decision:
    shown: bool
    why_hidden: str | None
    level: str
    on_front: bool
    alerts: bool


def decide(
    kind: str,
    level: str,
    country: str | None,
    confirmed: bool,
    had_candidates: bool,
    origin: str | None = None,
) -> Decision:
    home = in_spain(country)
    final = "medium" if not home and level == "high" else level
    if kind == "irrelevant":
        why = "irrelevant"
    elif not home and not confirmed:
        why = "abroad, no watched company"
    elif had_candidates and not confirmed and kind not in NO_PARTY_NEEDED:
        why = "homonym"
    else:
        record = origin in models.OFFICIAL
        on_front = models.front_page(kind, final, home)
        return Decision(
            True, None, final, on_front, models.alerts(kind, confirmed or record, final)
        )
    return Decision(False, why, final, False, False)


def candidate_names(
    parties: list[storage.Row], companies: dict[str, watchlist.Company]
) -> list[str]:
    return [
        companies[p["company"]].group if p["company"] in companies else p["company"]
        for p in parties
    ]


def item_payload(
    store: storage.Store, story: storage.Row, companies: dict[str, watchlist.Company]
) -> dict[str, Any]:
    names = candidate_names(store.parties(story["id"]), companies)
    return prompts.payload(
        story["id"],
        story["headline"],
        story["publisher"],
        story["published"],
        story["standfirst"],
        names,
    )


@dataclass
class Answer:
    kind: str
    level: str
    gist: str
    picked: list[int]  # 1-based positions in the candidate list
    country: str | None
    fact_key: str | None


def read_answer(entry: Any) -> Answer | None:
    if not isinstance(entry, dict):
        return None
    kind, level = entry.get("type"), entry.get("relevance")
    if kind not in models.TYPES or level not in models.RELEVANCES:
        return None
    picked = [k for k in entry.get("companies") or [] if isinstance(k, int)]
    return Answer(
        kind,
        level,
        str(entry.get("summary") or "").strip(),
        picked,
        str(entry.get("country") or "").strip() or None,
        textutil.slug(str(entry.get("fact_key") or "")) or None,
    )


def apply(
    store: storage.Store, story: storage.Row, answer: Answer, model: str, version: str
) -> Decision:
    """Stores the verdict for one story and appends the answer to the answer log."""
    parties = store.parties(story["id"])
    if story["origin"] in models.OFFICIAL:
        chosen = {p["id"] for p in parties}
    else:
        chosen = {parties[k - 1]["id"] for k in answer.picked if 0 < k <= len(parties)}
    d = decide(
        answer.kind, answer.level, answer.country, bool(chosen), bool(parties), story["origin"]
    )
    fields = {
        "kind": answer.kind,
        "level": d.level,
        "gist": answer.gist or None,
        "country": answer.country,
        "fact_key": answer.fact_key,
        "shown": int(d.shown),
        "why_hidden": d.why_hidden,
        "on_front": int(d.on_front),
        "alerts": int(d.alerts),
    }
    store.confirm(story["id"], chosen)
    store.put_verdict(story["id"], f"{model}/{version}", **fields)
    store.log_answer(story["id"], model, version, parties=chosen, **fields)
    return d


def close_official(store: storage.Store) -> Counter[str]:
    done: Counter[str] = Counter()
    waiting = store.rows(
        "SELECT * FROM story_now WHERE state = 'new' AND record_type IS NOT NULL ORDER BY id"
    )
    for story in waiting:
        kind, sid = story["record_type"], story["id"]
        answer = Answer(
            kind,
            story["record_level"] or "medium",
            story["headline"][:200],
            [],
            "Spain",
            f"{story['origin']}-{sid}",
        )
        apply(store, story, answer, "source", "source")
        done["official"] += 1
        if filters.below_floor(kind, store.amount(sid)):
            store.change(
                "verdict", sid, shown=0, why_hidden="below the minimum amount", on_front=0, alerts=0
            )
            done["below_minimum"] += 1
    store.commit()
    return done


class StopRun(Exception):
    pass


@dataclass
class Round:
    store: storage.Store
    companies: dict[str, watchlist.Company]
    llm: LLM
    version: str
    model: str
    stats: Counter[str]
    failures_in_a_row: int = 0

    def ask(self, batch: list[storage.Row]) -> dict[str, Any] | None:
        """The model's reply for one batch, or None when that batch failed."""
        text = prompts.classifier(
            self.version, [item_payload(self.store, s, self.companies) for s in batch]
        )
        self.stats["calls"] += 1
        try:
            reply = self.llm(text, prompts.SCHEMA, f"classify-{self.version}", len(batch))
        except QuotaExhausted as exc:
            self.stats["stopped_quota"] = 1
            raise StopRun(str(exc)) from exc
        except Exception as exc:
            log.warning("LLM batch skipped after an error: %s", str(exc)[:300])
            self.stats["failed_batches"] += 1
            self.failures_in_a_row += 1
            if self.failures_in_a_row >= config.FAILED_BATCHES_STOP:
                self.stats["stopped_overload"] = 1
                raise StopRun(f"{self.failures_in_a_row} batches failed in a row") from exc
            return None
        self.failures_in_a_row = 0
        return reply

    def take(self, batch: list[storage.Row], reply: dict[str, Any]) -> None:
        entries = [e for e in reply.get("items") or [] if isinstance(e, dict)]
        by_ref = {e.get("ref"): e for e in entries}
        for story in batch:
            answer = read_answer(by_ref.get(story["id"]))
            outcome = apply(self.store, story, answer, self.model, self.version) if answer else None
            label = (
                "unanswered" if outcome is None else "classified" if outcome.shown else "discarded"
            )
            self.stats[label] += 1
        self.store.commit()


PRESS_WAITING = "FROM story_now WHERE state = 'new' AND record_type IS NULL"


def classify(
    store: storage.Store,
    companies: dict[str, watchlist.Company],
    llm: LLM | None,
    version: str,
    batch_size: int = config.BATCH_SIZE,
    max_calls: int | None = None,
    model: str = config.GEMINI_MODEL,
) -> dict[str, int]:
    stats: Counter[str] = Counter(close_official(store))
    todo = store.rows(f"SELECT * {PRESS_WAITING} ORDER BY published, id")
    if llm is not None:
        run = Round(store, companies, llm, version, model, stats)
        limit = len(todo) if max_calls is None else max_calls * batch_size
        try:
            for start in range(0, min(len(todo), limit), batch_size):
                batch = todo[start : start + batch_size]
                reply = run.ask(batch)
                if reply is not None:
                    run.take(batch, reply)
        except StopRun as why:
            log.warning("classification stopped early: %s", why)
    stats["pending"] = int(store.value(f"SELECT count(*) {PRESS_WAITING}"))
    return dict(stats)


def reopen(
    store: storage.Store, only_visible: bool = False, story_ids: list[int] | None = None
) -> int:
    """Deletes model verdicts so the stories are classified again; returns how many.

    Register stories and stories folded into another by the merge step keep theirs.
    ``only_visible`` limits it to stories that are shown now.
    """
    where = [
        "decided_by IS NOT NULL",
        "record_type IS NULL",
        "(why_hidden IS NULL OR why_hidden NOT LIKE 'repeat of%')",
    ]
    if only_visible:
        where.append("shown = 1")
    ids = [r["id"] for r in store.rows(f"SELECT id FROM story_now WHERE {' AND '.join(where)}")]
    if story_ids is not None:
        wanted = set(story_ids)
        ids = [i for i in ids if i in wanted]
    for story_id in ids:
        store.forget_verdict(story_id)
    store.commit()
    return len(ids)
