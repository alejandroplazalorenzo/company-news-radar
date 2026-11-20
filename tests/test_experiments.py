from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, date, datetime
from itertools import pairwise
from pathlib import Path

import pytest

from company_news_radar import checks, coverage, experiments, judge
from company_news_radar.store import Store
from tests.test_merge import add

BORME_DDL = """
CREATE TABLE groups (group_id INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE companies (company_id INTEGER PRIMARY KEY, group_id INTEGER, name TEXT);
CREATE TABLE announcements (document_id TEXT, number INTEGER, pub_date TEXT, company_id INTEGER,
                            kept_as TEXT);
CREATE TABLE acts (document_id TEXT, number INTEGER, seq INTEGER, act_type TEXT);
"""


def borme_db(path: Path) -> Path:
    """A tiny database with borme-radar's schema: company acts, an officer act, noise."""
    con = sqlite3.connect(path)
    con.executescript(BORME_DDL)
    con.execute("INSERT INTO groups VALUES (1, 'Acerinox'), (2, 'Otro Grupo')")
    con.execute("INSERT INTO companies VALUES (1, 1, 'ACERINOX SA'), (2, 2, 'OTRA SA')")
    con.executemany(
        "INSERT INTO announcements VALUES (?,?,?,?,?)",
        [
            ("D1", 1, "2026-11-16", 1, "watched"),
            ("D1", 2, "2026-11-17", 1, "watched"),
            ("D1", 3, "2026-11-16", 2, "watched"),
            ("D1", 4, "2026-11-16", 1, "review"),
        ],
    )
    con.executemany(
        "INSERT INTO acts VALUES (?,?,?,?)",
        [
            ("D1", 1, 1, "merger"),
            ("D1", 2, 1, "capital_reduction"),
            ("D1", 2, 2, "appointment"),
            ("D1", 3, 1, "merger"),
            ("D1", 4, 1, "merger"),
        ],
    )
    con.commit()
    con.close()
    return path


def test_e1_reads_borme_radar_read_only(tmp_path: Path, store: Store, companies) -> None:
    db = borme_db(tmp_path / "borme.sqlite")
    con = coverage.open_readonly(db)
    with pytest.raises(sqlite3.OperationalError):
        con.execute("INSERT INTO groups VALUES (3, 'x')")
    acts = coverage.registry_acts(con, companies, date(2026, 11, 1), date(2026, 11, 30))
    assert [(a.company, a.act_type) for a in acts] == [
        ("acerinox", "merger"),
        ("acerinox", "capital_reduction"),
    ]  # officer acts, other groups and the review queue are left out
    assert coverage.left_out_acts(con, companies, date(2026, 11, 1), date(2026, 11, 30)) == {
        "officer acts": 1
    }
    add(
        store,
        companies,
        "Acerinox absorberá su filial ficticia",
        "2026-10-20",
        "acerinox",
        kind="deal",
        fact="acerinox-absorbs-subsidiary",
    )
    add(
        store,
        companies,
        "Acerinox presenta resultados inventados",
        "2026-11-01",
        "acerinox",
        kind="results",
        fact="acerinox-results-9m-2026",
    )
    merger, reduction = coverage.evaluate(acts, coverage.stories_by_company(store), "press")
    assert merger.ahead_any == 27 and merger.ahead_strict == 27
    assert reduction.any_first is not None and reduction.strict_first is None
    text = experiments.e1(argparse.Namespace(borme_db=db, out=tmp_path / "e1.md"), store, companies)
    assert "| press (2026-10-20 to 2026-11-01), all acts | 0 |" in text
    assert "whole window | 0 |" in text


def test_e1_one_to_one_counts_each_story_once() -> None:
    a1 = coverage.Act("bank", date(2026, 3, 1), "bond_issue")
    a2 = coverage.Act("bank", date(2026, 6, 1), "bond_issue")
    a3 = coverage.Act("bank", date(2026, 6, 10), "capital_reduction")
    stories = {"bank": [(date(2026, 2, 20), "capital", "official", 7)]}
    assert [s.ahead_strict for s in coverage.evaluate([a1, a2, a3], stories, None)] == [9, 101, 110]
    assert coverage.one_to_one([a1, a2, a3], stories, None) == {
        a1: date(2026, 2, 20),
        a2: None,
        a3: None,
    }
    stories["bank"].append((date(2026, 5, 25), "capital", "press", 8))
    assert coverage.one_to_one([a1, a2, a3], stories, "press") == {
        a1: None,
        a2: date(2026, 5, 25),
        a3: None,
    }


def test_rule_checks() -> None:
    good = {
        "type": "deal",
        "relevance": "high",
        "summary": "Acerinox buys a plant.",
        "companies": [1],
        "country": "Spain",
        "fact_key": "acerinox-buys-plant",
    }
    assert checks.violations({"headline": "Acerinox compra"}, good, 1) == []
    assert checks.violations({"headline": "x"}, None, 1) == ["missing"]
    bad = {
        **good,
        "summary": "The board named Ana López CEO.",
        "fact_key": "Acerinox Buys",
        "companies": [3],
    }
    assert set(checks.violations({"headline": "x"}, bad, 1)) == {
        "person_in_summary",
        "bad_fact_key",
        "company_out_of_range",
    }
    noise = {**good, "type": "capital"}
    assert "market_noise_kept" in checks.violations(
        {"headline": "Precio objetivo de Acerinox"}, noise, 1
    )


def test_kappa_queues_and_median(tmp_path: Path, store: Store, companies) -> None:
    assert judge.kappa([("a", "a"), ("b", "b")]) == 1.0
    assert judge.kappa([("a", "b"), ("b", "a")]) == -1.0
    assert experiments.median_text([1.0, 2.0, 10.0, 11.0]) == "6.00"  # not the upper median
    a = add(
        store,
        companies,
        "Endesa vende gas inventado",
        "2026-11-10",
        "endesa",
        fact="endesa-sells-gas",
    )
    b = add(
        store,
        companies,
        "Sacyr gana un puente ficticio",
        "2026-11-10",
        "sacyr",
        fact="sacyr-wins-bridge",
    )
    assert judge.classification_queue(store, [a, b], {"endesa": "Endesa"}, tmp_path) == 2
    line = json.loads((tmp_path / "queue.jsonl").read_text("utf-8").splitlines()[0])
    assert set(line) == {"qid", "headline", "snippet", "source", "date", "watched_companies_named"}
    judge.merge_queue(store, [(a, b, "fact")], [], {}, tmp_path)
    pair = json.loads((tmp_path / "merge_queue.jsonl").read_text("utf-8"))
    assert set(pair) == {"pid", "a", "b"} and "merged" not in json.dumps(pair)


def test_e3_effective_verdicts(store: Store, companies) -> None:
    sid = add(
        store,
        companies,
        "Endesa abre una planta ficticia",
        "2026-11-10",
        "endesa",
        kind="footprint",
        fact="endesa-opens-plant",
    )
    store.log_answer(
        sid,
        "m",
        "v2",
        kind="image",
        level="low",
        parties=set(),
        shown=1,
        on_front=0,
        alerts=0,
    )
    eff = experiments.effective(store, ["v1", "v2"])
    assert eff["v1"][sid]["on_front"] == 1 and eff["v2"][sid]["on_front"] == 0


def test_e4_controls_are_a_random_sample(tmp_path: Path, store: Store, companies) -> None:
    topics = "patrocinio premio feria campaña congreso jornada beca concurso gala visita foro ruta"
    ids = [
        add(
            store,
            companies,
            f"{w.capitalize()} inventado de Rovi en {n} ciudades",
            "2026-11-10",
            "rovi",
            kind="image",
            fact=f"rovi-{n}",
        )
        for n, w in enumerate(topics.split())
    ]
    for x, y in pairwise(ids):
        store.save_pair_verdict(x, y, False, "judge-j1")
    store.commit()
    args = argparse.Namespace(
        out=None, queue=True, sample=4, seed=7, labelled_by="x", data_dir=tmp_path
    )
    experiments.e4_report(args, store, companies)
    key = [
        json.loads(line)
        for line in (tmp_path / "judge" / "merge_key.jsonl").read_text("utf-8").splitlines()
    ]
    chosen = sorted((min(k["a"], k["b"]), max(k["a"], k["b"])) for k in key)
    first_four = [(ids[n], ids[n + 1]) for n in range(4)]
    assert len(chosen) == 4 and chosen != first_four  # shuffled with the seed, not the first asked


def test_quota_report_splits_statuses_and_shows_the_counter(tmp_path: Path) -> None:
    from company_news_radar.quota import Quota

    now = datetime(2026, 11, 19, 10, tzinfo=UTC)
    q = Quota(tmp_path / "quota.json", now=lambda: now)
    for status in (200, 503, 200, "timeout"):
        q.reserve()
        q.log(purpose="classify-v1", items=15, model="m", status=status, seconds=2.0)
    args = argparse.Namespace(data_dir=tmp_path, out=None, day=None)
    text = experiments.quota_report(args)
    assert "| 2026-11-19 | classify-v1 | 4 | 2 | 1 | 1 | 30 | 15.0 | 2.00 |" in text
    assert "| 2026-11-19 | 4 | 4 |" in text


def test_e2_report_scores_runs_and_reads_labels(tmp_path: Path, store: Store, companies) -> None:
    a = add(
        store,
        companies,
        "Endesa abre una planta ficticia",
        "2026-11-10",
        "endesa",
        kind="footprint",
        fact="endesa-opens-plant",
    )
    b = add(
        store,
        companies,
        "Sacyr gana un puente ficticio",
        "2026-11-10",
        "sacyr",
        kind="contract",
        fact="sacyr-wins-bridge",
    )
    e2 = tmp_path / "e2"
    (e2 / "runs").mkdir(parents=True)
    (e2 / "sample.json").write_bytes(
        json.dumps({"seed": 7, "batch": 2, "batches": [[a, b]]}).encode()
    )
    entry = {
        "type": "footprint",
        "relevance": "high",
        "summary": "s",
        "companies": [1],
        "country": "Spain",
        "fact_key": "x",
    }
    row = {
        "batch": 0,
        "ids": [a, b],
        "answer": {"items": [{**entry, "ref": a}]},
        "error": None,
        "seconds": 3.0,
        "prompt_tokens": 100,
        "output_tokens": 50,
        "prompt": "v1",
    }
    (e2 / "runs" / "m.jsonl").write_bytes(
        (json.dumps(row) + "\n" + json.dumps({"notes": {"gpu": "g"}}) + "\n").encode()
    )
    (tmp_path / "judge").mkdir()
    (tmp_path / "judge" / "key.jsonl").write_bytes(
        json.dumps({"qid": "q001", "story_id": a}).encode() + b"\n"
    )
    label = {
        "qid": "q001",
        "type": "footprint",
        "relevance": "high",
        "country": "Spain",
        "about_watched": True,
    }
    (tmp_path / "judge" / "labels.jsonl").write_bytes(json.dumps(label).encode() + b"\n")
    args = argparse.Namespace(data_dir=tmp_path, out=None, sample="main", labelled_by="x")
    text = experiments.e2_report(args, store)
    assert "| m | 0 | 1 of 2 | 1 | 1 |" in text and "gpu g" in text
    assert "| m | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |" in text


def test_tuning_replay_matches_the_process_fold(store: Store, companies) -> None:
    from company_news_radar import entities, tuning
    from company_news_radar.models import Item
    from company_news_radar.process import process

    headlines = [
        ("2026-11-10", "Endesa vende su negocio ficticio de gas en Villaejemplo"),
        ("2026-11-11", "Endesa vende su negocio ficticio de gas en Villaejemplo."),
        ("2026-11-12", "Endesa vende el negocio ficticio de gas de Villaejemplo"),
        ("2026-11-16", "Endesa vende su negocio ficticio de gas en Villaejemplo"),
        ("2026-11-12", "Sacyr gana un puente inventado en Villaejemplo"),
    ]
    store.add_captures(
        Item(
            ident=f"https://n.test/{k}",
            url=f"https://n.test/{k}",
            headline=h,
            origin="newsroom",
            channel="s",
            published=f"{day}T08:00:00+00:00",
            standfirst=h,
            subject=h.split()[0].lower(),
        )
        for k, (day, h) in enumerate(headlines)
    )
    d = entities.build(companies)
    process(store, d, None)
    seen = tuning.kept_press(store, d)
    sims = tuning.similarities(seen)
    assert tuning.replay(seen, sims, 0.85, 4) == tuning.replay_as_process(seen)
    assert len(tuning.replay(seen, sims, 0.85, 4)) == len(seen) - store.value(
        "SELECT count(*) FROM story"
    )
    assert len(tuning.replay(seen, sims, 0.85, 7)) > len(tuning.replay(seen, sims, 0.85, 4))
