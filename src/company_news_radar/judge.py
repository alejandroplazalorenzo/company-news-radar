"""Queues for blind labelling, and Cohen's kappa for scoring against the labels.

A queue line holds what a reader of the news sees (headline, snippet, source, date) and the
watched companies the linker found; no classifier or merge output goes in. The line-to-story
key is written to a separate file. Labelling rules: docs/label_guide.md.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from company_news_radar.store import Store


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    lines = [json.dumps(r, ensure_ascii=False) for r in rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes("".join(f"{line}\n" for line in lines).encode("utf-8"))
    return len(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Objects of a JSON-lines file; a missing file reads as empty."""
    try:
        text = path.read_bytes().decode("utf-8")
    except FileNotFoundError:
        return []
    return [json.loads(chunk) for chunk in filter(str.strip, text.splitlines())]


def _card(store: Store, story_id: int, names: dict[str, str]) -> dict[str, Any]:
    s = store.story(story_id)
    assert s is not None
    companies = [names.get(p["company"], p["company"]) for p in store.parties(story_id)]
    return {
        "headline": s["headline"],
        "snippet": s["standfirst"] or "",
        "source": s["publisher"] or "",
        "date": (s["published"] or "")[:10],
        "watched_companies_named": companies,
    }


def classification_queue(
    store: Store, story_ids: list[int], names: dict[str, str], directory: Path, seed: int = 7
) -> int:
    ids = list(story_ids)
    random.Random(seed).shuffle(ids)
    queue, key = [], []
    for k, sid in enumerate(ids, start=1):
        qid = f"q{k:03d}"
        queue.append({"qid": qid, **_card(store, sid, names)})
        key.append({"qid": qid, "story_id": sid})
    _write_jsonl(directory / "key.jsonl", key)
    return _write_jsonl(directory / "queue.jsonl", queue)


def merge_queue(
    store: Store,
    merged: list[tuple[int, int, str]],
    not_merged: list[tuple[int, int, str]],
    names: dict[str, str],
    directory: Path,
    seed: int = 11,
) -> int:
    """One shuffled queue mixing joined pairs with close pairs left apart."""
    pairs = [(a, b, True, rule) for a, b, rule in merged] + [
        (a, b, False, why) for a, b, why in not_merged
    ]
    random.Random(seed).shuffle(pairs)
    queue, key = [], []
    for k, (a, b, was_merged, rule) in enumerate(pairs, start=1):
        pid = f"p{k:03d}"
        first, second = (a, b) if k % 2 else (b, a)
        queue.append(
            {"pid": pid, "a": _card(store, first, names), "b": _card(store, second, names)}
        )
        key.append({"pid": pid, "a": first, "b": second, "merged": was_merged, "rule": rule})
    _write_jsonl(directory / "merge_key.jsonl", key)
    return _write_jsonl(directory / "merge_queue.jsonl", queue)


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    labels = {x for p in pairs for x in p}
    expected = sum(
        (sum(a == lab for a, _ in pairs) / n) * (sum(b == lab for _, b in pairs) / n)
        for lab in labels
    )
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)
