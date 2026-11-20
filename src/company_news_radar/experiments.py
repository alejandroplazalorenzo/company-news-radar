"""Report commands: the probe, the development subset, E1 to E4 and the quota log.

Each report starts with the command that produced it, the run time and the library versions.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import random
import shlex
import shutil
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from importlib import metadata
from pathlib import Path
from typing import Any

from company_news_radar import checks, coverage, judge, prompts, tuning
from company_news_radar.classify import decide, item_payload, read_answer
from company_news_radar.models import TYPES
from company_news_radar.quota import QuotaExhausted
from company_news_radar.sources import newsrooms
from company_news_radar.store import Store
from company_news_radar.watchlist import Company


def versions() -> str:
    libs = ", ".join(f"{p} {metadata.version(p)}" for p in ("httpx", "lxml", "truststore"))
    return f"Python {platform.python_version()} on {platform.system()} {platform.release()}; {libs}"


def header(title: str, command: str, extra: list[str] | None = None) -> list[str]:
    lines = [
        f"# {title}",
        "",
        f"Command: `{command}`",
        "",
        f"- Run: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        f"- {versions()}",
    ]
    lines += [f"- {e}" for e in extra or []]
    return [*lines, ""]


def write(path: Path | None, lines: list[str]) -> str:
    text = "\n".join(lines).rstrip() + "\n"
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))
    return text


def pct(a: int, b: int) -> str:
    return f"{100 * a / b:.1f}%" if b else "n/a"


def command_line() -> str:
    return "company-news-radar " + shlex.join(sys.argv[1:])


def median_text(values: list[float], digits: int = 2) -> str:
    return f"{statistics.median(values):,.{digits}f}" if values else "-"


def _fetch_runs(store: Store) -> list[dict[str, Any]]:
    rows = store.rows("SELECT * FROM run_log WHERE report IS NOT NULL ORDER BY id")
    return [{"mode": r["purpose"], "started": r["began"], **json.loads(r["report"])} for r in rows]


def probe_report(store: Store, batches: list[int]) -> str:
    """Volumes per source and stage, and how many requests one LLM pass would take."""
    lines = [
        "## Items",
        "",
        "| Source | Items | Pass the filters | Oldest | Newest |",
        "|---|---:|---:|---|---|",
    ]
    for r in store.rows(
        """SELECT origin, count(*) AS n, sum(triage = 'kept') AS ok, min(published) AS lo,
        max(published) AS hi FROM capture GROUP BY 1 ORDER BY 2 DESC"""
    ):
        lines.append(
            f"| {r['origin']} | {r['n']} | {r['ok'] or 0} | {(r['lo'] or '')[:10]} "
            f"| {(r['hi'] or '')[:10]} |"
        )
    nr = store.rows(
        "SELECT channel, count(*) AS n FROM capture WHERE origin = 'newsroom' GROUP BY 1"
    )
    sitemaps = store.value("SELECT count(DISTINCT site) FROM sitemap_seen")
    addresses = store.value(
        "SELECT count(*) FROM sitemap_seen WHERE address <> ?", newsrooms.FIRST_READ
    )
    lines += [
        "",
        f"Newsrooms: {sitemaps} sitemaps read (their first read is the baseline: "
        f"{addresses} addresses stored, none announced); "
        "newsroom items by source: "
        + (", ".join(f"{r['channel']} {r['n']}" for r in nr) or "none"),
        "",
        "Press-search items per month of publication (how far back the engine serves): "
        + ", ".join(
            f"{r[0]} {r[1]}"
            for r in store.rows(
                "SELECT substr(published, 1, 7), count(*) FROM capture WHERE origin = 'bing_news'"
                " GROUP BY 1 ORDER BY 1"
            )
        ),
        "",
        "## Dropped before the LLM",
        "",
        "| Reason | Items |",
        "|---|---:|",
    ]
    for r in store.rows(
        "SELECT triage, count(*) AS n FROM capture WHERE triage <> 'kept'"
        " GROUP BY 1 ORDER BY 2 DESC"
    ):
        lines.append(f"| {r['triage']} | {r['n']} |")
    waiting = store.value("SELECT count(*) FROM story WHERE record_type IS NULL")
    official = store.value("SELECT count(*) FROM story WHERE record_type IS NOT NULL")
    joined = store.value("SELECT count(*) FROM capture WHERE story_id IS NOT NULL") - store.value(
        "SELECT count(*) FROM story"
    )
    lines += [
        "",
        f"Stories for the LLM: **{waiting}**; official records (no LLM, one story each): "
        f"{official}; items folded into an existing story as exact repeats: {joined}.",
        "",
        "| Batch size | Requests for one pass |",
        "|---:|---:|",
    ]
    lines += [f"| {b} | {math.ceil(waiting / b) if b else 0} |" for b in batches]
    per_company = store.rows(
        """SELECT p.company, count(DISTINCT s.id) AS n FROM story s
        JOIN party p ON p.story_id = s.id AND p.how <> 'merged'
        WHERE s.record_type IS NULL GROUP BY 1 ORDER BY 2 DESC"""
    )
    if per_company:
        lines += ["", "Stories per company: " + ", ".join(f"{r[0]} {r[1]}" for r in per_company)]
    runs = _fetch_runs(store)
    if runs:
        lines += [
            "",
            "## Requests made",
            "",
            "| Run | Started (UTC) | Since | New items by source | Requests | Retries "
            "| Refused (robots.txt, never-ask, brake) | Redirects "
            "| Hosts: rules / no file / not a robots file / unreachable |",
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
        for run in runs:
            verdicts = Counter((run.get("robots") or {}).values())
            new = ", ".join(f"{k} {v}" for k, v in (run.get("new_by_source") or {}).items())
            lines.append(
                f"| {run['mode']} | {run['started'][:16]} | {run.get('since') or '-'} | "
                f"{new or '-'} | {run.get('requests', 0)} | {run.get('retries', 0)} | "
                f"{run.get('refused', 0)} | {run.get('redirects', 0)} | "
                f"{verdicts.get('rules', 0)} / {verdicts.get('no_file', 0)} / "
                f"{verdicts.get('not_robots', 0)} / {verdicts.get('unreachable', 0)} |"
            )
        lines.append("")
        for run in runs:
            for source, error in sorted((run.get("failed_sources") or {}).items()):
                lines.append(f"- failed in the run of {run['started'][:16]}: {source}: {error}")
        never = sorted({h for run in runs for h in run.get("never_asked") or []})
        if never:
            lines.append(f"- never asked, by design: {', '.join(never)}")
    return "\n".join(lines) + "\n"


def answers_of(store: Store, version: str) -> dict[int, Any]:
    """The last answer of ``version`` for each story it read."""
    rows = store.rows("SELECT * FROM answer WHERE version = ? ORDER BY id", version)
    return {r["story_id"]: r for r in rows}


def dev_split(args: argparse.Namespace, store: Store, companies: list[Company]) -> str:
    """Draws the development subset and writes its ids and a reading sheet under data/dev.

    The sheet shows each story with the answer ``args.prompt`` gave, not its current verdict.
    """
    version = args.prompt
    answers = answers_of(store, version)
    ids = sorted(answers)
    random.Random(args.seed).shuffle(ids)
    dev = sorted(ids[: round(len(ids) * args.share)])
    out = args.data_dir / "dev"
    out.mkdir(parents=True, exist_ok=True)
    (out / "ids.json").write_bytes(
        json.dumps({"prompt": version, "seed": args.seed, "ids": dev}).encode("utf-8")
    )
    names = {c.id: c.group for c in companies}
    sheet = [f"# Development subset: {len(dev)} of {len(ids)} stories classified by {version}", ""]
    for sid in dev:
        s, a = store.story(sid), answers[sid]
        if s is None:
            continue
        chosen = set(json.loads(a["parties"]))
        parties = store.parties(sid)
        who = sorted(names.get(p["company"], p["company"]) for p in parties if p["id"] in chosen)
        cand = sorted(names.get(p["company"], p["company"]) for p in parties)
        sheet += [
            f"## {sid} · {a['kind']} / {a['level']} · {'shown' if a['shown'] else 'hidden'}"
            f"{' (' + a['why_hidden'] + ')' if a['why_hidden'] else ''}"
            f"{' · FRONT' if a['on_front'] else ''}",
            f"- {s['headline']} ({s['publisher'] or ''}, {(s['published'] or '')[:10]})",
            f"- snippet: {(s['standfirst'] or '')[:300]}",
            f"- candidates: {', '.join(cand) or '-'}; confirmed: {', '.join(who) or '-'}",
            f"- summary: {a['gist'] or ''} · country: {a['country']} · fact: {a['fact_key']}",
            "",
        ]
    (out / f"{version}_sheet.md").write_bytes("\n".join(sheet).encode("utf-8"))
    return f"development subset: {len(dev)} of {len(ids)} -> {out}\n"


def dev_report(args: argparse.Namespace, store: Store) -> str:
    """Counts behind docs/prompt_versions.md, from the answer log and the recorded reading."""
    plan = json.loads((args.data_dir / "dev" / "ids.json").read_text("utf-8"))
    version, dev = plan["prompt"], plan["ids"]
    answers = answers_of(store, version)
    subset = [answers[i] for i in dev if i in answers]
    front = [a for a in subset if a["on_front"]]
    by_kind = Counter(a["kind"] for a in front)
    lines = header(
        "Development subset",
        command_line(),
        [
            f"Drawn by `dev-split --prompt {version} --seed {plan['seed']}` from the "
            f"{len(answers)} stories {version} read; the rest ({len(answers) - len(dev)}) is "
            "where E2 draws its sample",
        ],
    )
    lines += [
        f"| {version} on the subset | Stories |",
        "|---|---:|",
        f"| read | {len(subset)} |",
        f"| shown | {sum(a['shown'] for a in subset)} |",
        f"| on the front page | {len(front)} |",
    ]
    lines += [f"| front page, {k} | {n} |" for k, n in sorted(by_kind.items())]
    reading_path = args.data_dir / "dev" / f"{version}_front_reading.jsonl"
    reading = {r["story_id"]: r for r in judge.read_jsonl(reading_path)}
    if reading:
        wrong = [a for a in front if not reading.get(a["story_id"], {}).get("front", True)]
        missing = sum(a["story_id"] not in reading for a in front)
        per = Counter(a["kind"] for a in wrong)
        lines += [
            "",
            f"Reading of the {len(front)} front-page stories (`{reading_path.name}`, written by "
            f"{args.read_by}; not blind: the reader saw {version}'s answers): "
            f"{len(wrong)} should not be on the front page ("
            + ", ".join(f"{per.get(k, 0)} of {n} {k}" for k, n in sorted(by_kind.items()))
            + f"); not read: {missing}.",
        ]
    later = sorted(
        v for (v,) in store.rows("SELECT DISTINCT version FROM answer WHERE version LIKE 'v%'")
    )
    for other in (v for v in later if v > version):
        theirs = answers_of(store, other)
        kept = [a for a in front if theirs.get(a["story_id"]) and theirs[a["story_id"]]["on_front"]]
        agree = (
            sum(
                reading[a["story_id"]]["front"] == (a in kept)
                for a in front
                if a["story_id"] in reading
            )
            if reading
            else None
        )
        lines += [
            "",
            f"{other} on the same {len(front)} stories: {len(kept)} kept on the front page, "
            f"{len(front) - len(kept)} taken off"
            + (f"; it agrees with the reading on {agree} of them." if agree is not None else "."),
        ]
    return write(args.out, lines)


def e1(args: argparse.Namespace, store: Store, companies: list[Company]) -> str:
    con = coverage.open_readonly(args.borme_db)
    stories = coverage.stories_by_company(store)
    # press period: the dates the search returned (older feed or newsroom pages would stretch it)
    lo, hi = store.row(
        """SELECT min(published), max(published) FROM capture WHERE origin = 'bing_news'
        AND triage = 'kept'"""
    ) or (None, None)
    press = [date.fromisoformat(d[:10]) for d in (lo, hi) if d] or [
        d for v in stories.values() for d, _, k, _ in v if k == "press"
    ]
    official = [d for v in stories.values() for d, _, k, _ in v if k == "official"]
    lines = header(
        "E1: coverage against the Companies Register",
        command_line(),
        [
            f"borme-radar database (opened read-only): `{args.borme_db.name}`",
            f"A story counts if published {coverage.BEFORE_DAYS} days before to "
            f"{coverage.AFTER_DAYS} days after the act",
            "Rows 'all acts': every act of the source's period; rows 'whole window': only acts "
            f"whose {coverage.BEFORE_DAYS}+{coverage.AFTER_DAYS}-day window lies inside the period",
            "One-to-one: acts in date order each take the unused compatible story closest in "
            "date (greedy, so a bound, not an optimal matching)",
            "Act types left out (not company facts this radar types): "
            + ", ".join(sorted(coverage.LEFT_OUT_ACTS)),
        ],
    )
    lines += [
        "| Stories from | Acts | Seen (any story) | Median days ahead "
        "| Seen (compatible type) | Median days ahead "
        "| Seen (one-to-one) | Median days ahead |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    detail: list[str] = []
    excluded: Counter[str] = Counter()
    for label, src, dates in (
        ("press", "press", press),
        ("official records", "official", official),
    ):
        if not dates:
            lines.append(f"| {label} | 0 | - | - | - | - | - | - |")
            continue
        start, end = min(dates), max(dates)
        every = coverage.registry_acts(con, companies, start, end)
        inner = [
            a
            for a in every
            if a.pub_date - timedelta(days=coverage.BEFORE_DAYS) >= start
            and a.pub_date + timedelta(days=coverage.AFTER_DAYS) <= end
        ]
        for scope, acts in (("all acts", every), ("whole window", inner)):
            row = f"| {label} ({start} to {end}), {scope} | {len(acts)} |"
            if not acts:
                lines.append(row + " - | - | - | - | - | - |")
                continue
            seen = coverage.evaluate(acts, stories, src)
            any_seen = [s for s in seen if s.any_first]
            strict = [s for s in seen if s.strict_first]
            ahead_any = [s.ahead_any for s in any_seen if s.ahead_any is not None]
            ahead_strict = [s.ahead_strict for s in strict if s.ahead_strict is not None]
            matched = coverage.one_to_one(acts, stories, src)
            ahead_one = [(a.pub_date - d).days for a, d in matched.items() if d is not None]
            lines.append(
                f"{row} {len(any_seen)} ({pct(len(any_seen), len(acts))}) | "
                f"{coverage.median(ahead_any)} | {len(strict)} ({pct(len(strict), len(acts))}) | "
                f"{coverage.median(ahead_strict)} | "
                f"{len(ahead_one)} ({pct(len(ahead_one), len(acts))}) | "
                f"{coverage.median(ahead_one)} |"
            )
            if scope == "all acts":
                # loose metric only: which origins sat in the window of each act it counted
                kinds = dict(store.rows("SELECT id, origin FROM story"))
                seen_by = Counter(
                    "+".join(
                        sorted(
                            {kinds.get(sid, "?") for sid in coverage.window_ids(a, stories, src)}
                        )
                    )
                    for a in (s.act for s in any_seen)
                )
                detail += [
                    f"### {label}",
                    "",
                    "Acts seen under the loose metric, by the sources in their window: "
                    + ", ".join(f"{k} {v}" for k, v in sorted(seen_by.items())),
                    "",
                    "| Company | Act | BORME date | Whole window | First compatible story "
                    "| Days ahead | One-to-one story | Days ahead |",
                    "|---|---|---|---|---|---:|---|---:|",
                ]
                for s in seen:
                    one = matched[s.act]
                    detail.append(
                        f"| {s.act.company} | {s.act.act_type} | {s.act.pub_date} | "
                        f"{'yes' if s.act in inner else 'no'} | {s.strict_first or '-'} | "
                        f"{s.ahead_strict if s.ahead_strict is not None else '-'} | "
                        f"{one or '-'} | {(s.act.pub_date - one).days if one else '-'} |"
                    )
                detail.append("")
    span = (
        (min([*press, *official]), max([*press, *official])) if press or official else (None, None)
    )
    if span[0] is not None:
        excluded.update(coverage.left_out_acts(con, companies, span[0], span[1]))
    lines += [
        "",
        "Positive days ahead: the radar had it before the Registro published it.",
        "",
        f"Acts of left-out types from {span[0]} to {span[1]}: "
        + (", ".join(f"{k} {v}" for k, v in sorted(excluded.items())) or "none"),
        "",
    ]
    return write(args.out, [*lines, *detail])


def e2_dir(args: argparse.Namespace) -> Path:
    name = getattr(args, "sample", "main")
    return args.data_dir / "e2" if name == "main" else args.data_dir / "e2" / name


def e2_sample(args: argparse.Namespace, store: Store, companies: list[Company]) -> str:
    """Writes the E2 sample (and, for the main sample, the blind queue).

    The main sample leaves out the development subset; another sample regroups the same
    stories with a different batch size.
    """
    main = args.data_dir / "e2" / "sample.json"
    if args.sample != "main":
        sample = sorted(s for b in json.loads(main.read_text("utf-8"))["batches"] for s in b)
        excluded = 0
    else:
        dev: set[int] = set()
        if args.exclude and args.exclude.exists():
            dev = set(json.loads(args.exclude.read_text("utf-8"))["ids"])
        ids = [
            r[0]
            for r in store.rows(
                "SELECT DISTINCT story_id FROM answer WHERE version = ? ORDER BY story_id",
                args.drawn_from,
            )
        ]
        excluded = sum(i in dev for i in ids)
        pool = [i for i in ids if i not in dev]
        random.Random(args.seed).shuffle(pool)
        sample = sorted(pool[: args.n])
    batches = [sample[i : i + args.batch] for i in range(0, len(sample), args.batch)]
    out = e2_dir(args) / "sample.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    plan = {
        "seed": args.seed,
        "batch": args.batch,
        "batches": batches,
        "excluded_development": excluded,
    }
    out.write_bytes(json.dumps(plan).encode("utf-8"))
    n = 0
    if args.sample == "main":
        names = {c.id: c.group for c in companies}
        n = judge.classification_queue(store, sample, names, args.data_dir / "judge")
    return (
        f"sample of {len(sample)} stories in {len(batches)} batches -> {out}; "
        f"development stories left out: {excluded}; judge queue: {n}\n"
    )


def e2_run(
    args: argparse.Namespace, store: Store, companies: list[Company], llm: Any, name: str
) -> str:
    """Runs one model over the sample batches; batches already done are skipped."""
    plan = json.loads((e2_dir(args) / "sample.json").read_text("utf-8"))
    by_id = {c.id: c for c in companies}
    out = e2_dir(args) / "runs" / f"{name}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    done = {r["batch"] for r in judge.read_jsonl(out) if "batch" in r and not r["error"]}
    with out.open("ab") as fh:
        for k, batch in enumerate(plan["batches"]):
            if k in done:
                continue
            stories = [store.story(sid) for sid in batch]
            text = prompts.classifier(
                args.prompt, [item_payload(store, s, by_id) for s in stories if s is not None]
            )
            started = datetime.now(UTC)
            try:
                answer, error = llm(text, prompts.SCHEMA, f"e2-{name}", len(batch)), None
            except QuotaExhausted as exc:
                fh.write((json.dumps({"stopped": str(exc)}) + "\n").encode("utf-8"))
                break
            except Exception as exc:  # kept as a failed batch
                answer, error = {}, f"{type(exc).__name__}: {str(exc)[:200]}"
            meta = getattr(llm, "last", {}) or {}
            row = {
                "batch": k,
                "ids": batch,
                "answer": answer,
                "error": error,
                "seconds": meta.get("seconds") or (datetime.now(UTC) - started).total_seconds(),
                "prompt_tokens": meta.get("prompt_tokens"),
                "output_tokens": meta.get("output_tokens"),
                "num_ctx": meta.get("num_ctx"),
                "prompt_chars": len(text),
                "prompt": args.prompt,
            }
            fh.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
            fh.flush()
        notes = getattr(llm, "notes", None)
        if callable(notes):
            fh.write((json.dumps({"notes": notes()}, ensure_ascii=False) + "\n").encode("utf-8"))
    return f"{name}: {out}\n"


def last_per_batch(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    last = {r["batch"]: r for r in rows if "batch" in r}
    return [last[k] for k in sorted(last)]


def verdicts_of(store: Store, run: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for row in run:
        entries = (row["answer"] or {}).get("items", [])
        by_ref = {e.get("ref"): e for e in entries if isinstance(e, dict)}
        for sid in row["ids"]:
            s = store.story(sid)
            parties = store.parties(sid)
            entry = by_ref.get(sid)
            fails = checks.violations({"headline": s["headline"] if s else ""}, entry, len(parties))
            v: dict[str, Any] = {
                "violations": fails,
                "type": None,
                "visible": False,
                "front": False,
            }
            answer = read_answer(entry)
            if "missing" not in fails and answer and s:
                confirmed = any(1 <= k <= len(parties) for k in answer.picked)
                d = decide(
                    answer.kind, answer.level, answer.country, confirmed, bool(parties), s["origin"]
                )
                v.update(type=answer.kind, visible=d.shown, front=d.on_front)
            out[sid] = v
    return out


def reference(
    store: Store, labels: list[dict[str, Any]], key: dict[str, int]
) -> dict[int, dict[str, Any]]:
    """Passes each blind label through ``decide`` so it can be compared with a run."""
    out = {}
    for lab in labels:
        sid = key.get(lab.get("qid", ""))
        s = store.story(sid) if sid else None
        if not s or lab.get("type") not in TYPES:
            continue
        d = decide(
            lab["type"],
            lab.get("relevance", "low"),
            lab.get("country"),
            bool(lab.get("about_watched")),
            bool(store.parties(s["id"])),
            s["origin"],
        )
        out[s["id"]] = {"type": lab["type"], "visible": d.shown, "front": d.on_front}
    return out


def _run_notes(path: Path) -> dict[str, Any]:
    notes: dict[str, Any] = {}
    for r in judge.read_jsonl(path):
        notes.update(r.get("notes") or {})
    return notes


def e2_report(args: argparse.Namespace, store: Store) -> str:
    runs_dir = e2_dir(args) / "runs"
    paths = sorted(runs_dir.glob("*.jsonl"))
    runs = {p.stem: last_per_batch(judge.read_jsonl(p)) for p in paths}
    verdicts = {name: verdicts_of(store, rows) for name, rows in runs.items()}
    plan = json.loads((e2_dir(args) / "sample.json").read_text("utf-8"))
    n = sum(len(b) for b in plan["batches"])
    lines = header(
        "E2: local model against the API, same items, prompt and batches",
        command_line(),
        [
            f"Sample: {n} stories the backfill sent to the LLM, none of them in the development "
            f"subset the prompt was written from; seed {plan['seed']}, "
            f"{len(plan['batches'])} batches of {plan['batch']}",
            "Prompts: " + ", ".join(sorted({str(r[0].get("prompt")) for r in runs.values() if r})),
        ],
    )
    lines += [
        "| Run | Failed batches | Items answered | Visible | Front page | Rule violations "
        "| Prompt tokens (median) | Output tokens (median) | Seconds per batch (median) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, rows in runs.items():
        v = verdicts[name]
        answered = sum("missing" not in x["violations"] for x in v.values())
        broken = sum(len([y for y in x["violations"] if y != "missing"]) for x in v.values())
        tokens = [float(r["prompt_tokens"]) for r in rows if r.get("prompt_tokens")]
        output = [float(r["output_tokens"]) for r in rows if r.get("output_tokens")]
        seconds = [float(r["seconds"]) for r in rows if r.get("seconds")]
        lines.append(
            f"| {name} | {sum(1 for r in rows if r['error'])} | {answered} of {n} | "
            f"{sum(x['visible'] for x in v.values())} | {sum(x['front'] for x in v.values())} | "
            f"{broken} | {median_text(tokens, 0)} | {median_text(output, 0)} | "
            f"{median_text(seconds)} |"
        )
    lines += [
        "",
        "Rule violations by check (items):",
        "",
        "| Run | " + " | ".join(checks.CHECKS) + " |",
        "|---|" + "---:|" * len(checks.CHECKS),
    ]
    for name in runs:
        c = Counter(y for x in verdicts[name].values() for y in x["violations"])
        lines.append(f"| {name} | " + " | ".join(str(c.get(k, 0)) for k in checks.CHECKS) + " |")
    names = list(runs)
    if len(names) > 1:
        lines += [
            "",
            "Agreement between runs (items both answered):",
            "",
            "| A | B | n | Same type | Kappa (type) | Same visible | Same front page |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for i, a in enumerate(names):
            for b in names[i + 1 :]:
                va, vb = verdicts[a], verdicts[b]
                both = [s for s in va if va[s]["type"] and vb.get(s, {}).get("type")]
                types = [(va[s]["type"], vb[s]["type"]) for s in both]
                k = judge.kappa(types)
                lines.append(
                    f"| {a} | {b} | {len(both)} | "
                    f"{pct(sum(x == y for x, y in types), len(both))} | "
                    f"{f'{k:.2f}' if k is not None else '-'} | "
                    f"{pct(sum(va[s]['visible'] == vb[s]['visible'] for s in both), len(both))} | "
                    f"{pct(sum(va[s]['front'] == vb[s]['front'] for s in both), len(both))} |"
                )
    notes = {p.stem: _run_notes(p) for p in paths}
    if any(notes.values()):
        lines += ["", "Run notes (recorded by `e2-run` while the model was loaded):", ""]
        for name, note in notes.items():
            if note:
                lines.append(f"- {name}: " + "; ".join(f"{k} {v}" for k, v in note.items()))
    labels = judge.read_jsonl(args.data_dir / "judge" / "labels.jsonl")
    key = {r["qid"]: r["story_id"] for r in judge.read_jsonl(args.data_dir / "judge" / "key.jsonl")}
    if not labels:
        lines += ["", "Reference labels: not yet available (`data/judge/labels.jsonl`)."]
        return write(args.out, lines)
    ref = reference(store, labels, key)
    lines += [
        "",
        f"Against the blind reference labels ({len(ref)} items, labelled by {args.labelled_by}: "
        "agreement with that labeller, not accuracy):",
        "",
        "| Run | Same type | Same visible | Same front page | Front page precision | recall |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name in runs:
        v = verdicts[name]
        common = [s for s in ref if s in v]
        tp = sum(v[s]["front"] and ref[s]["front"] for s in common)
        lines.append(
            f"| {name} | {pct(sum(v[s]['type'] == ref[s]['type'] for s in common), len(common))} | "
            f"{pct(sum(v[s]['visible'] == ref[s]['visible'] for s in common), len(common))} | "
            f"{pct(sum(v[s]['front'] == ref[s]['front'] for s in common), len(common))} | "
            f"{pct(tp, sum(v[s]['front'] for s in common))} | "
            f"{pct(tp, sum(ref[s]['front'] for s in common))} |"
        )
    lines.append(f"\nReference front-page stories: {sum(r['front'] for r in ref.values())}.")
    return write(args.out, lines)


def effective(store: Store, order: list[str]) -> dict[str, dict[int, Any]]:
    """Per version, each story's answer from the newest version up to that one."""
    rows = store.rows(
        """SELECT story_id, version, shown, on_front, kind FROM answer
        WHERE version LIKE 'v%' ORDER BY id"""
    )
    by_story: dict[int, dict[str, Any]] = defaultdict(dict)
    for r in rows:
        by_story[r["story_id"]][r["version"]] = r
    out: dict[str, dict[int, Any]] = {}
    for i, version in enumerate(order):
        known = order[: i + 1]
        out[version] = {}
        for sid, per in by_story.items():
            latest = next((per[v] for v in reversed(known) if v in per), None)
            if latest is not None:
                out[version][sid] = latest
    return out


def e3_report(args: argparse.Namespace, store: Store) -> str:
    order = sorted(
        r[0] for r in store.rows("SELECT DISTINCT version FROM answer WHERE version LIKE 'v%'")
    )
    eff = effective(store, order)
    published = {r[0]: (r[1] or "")[:10] for r in store.rows("SELECT id, published FROM story")}
    base = [s for s in eff[order[0]] if published.get(s)] if order else []
    reread = {
        v: store.value("SELECT count(DISTINCT story_id) FROM answer WHERE version = ?", v)
        for v in order
    }
    lines = header(
        "E3: prompt versions, front page per period",
        command_line(),
        [
            f"Stories classified by {order[0] if order else '-'}: {len(base)}; read again by each "
            "version: " + ", ".join(f"{v} {n}" for v, n in reread.items()),
            "Front page = deal or footprint, high or medium relevance, in Spain; counted before "
            "merging repeats, so only the prompt changes between rows",
        ],
    )
    months = sorted({published[s][:7] for s in base})
    weeks = sorted({date.fromisoformat(published[s]).isocalendar()[:2] for s in base})
    lines += [
        "| Version | Read | Visible | Front page | " + " | ".join(months) + " |",
        "|---|---:|---:|---:|" + "---:|" * len(months),
    ]
    for v in order:
        verdicts = eff[v]
        visible = sum(r["shown"] for r in verdicts.values())
        front = [s for s, r in verdicts.items() if r["on_front"] and published.get(s)]
        per = Counter(published[s][:7] for s in front)
        lines.append(
            f"| {v} | {reread[v]} | {visible} | {len(front)} | "
            + " | ".join(str(per.get(m, 0)) for m in months)
            + " |"
        )
    lines += [
        "",
        "Front page per ISO week:",
        "",
        "| Version | " + " | ".join(f"{y}-W{w:02d}" for y, w in weeks) + " |",
        "|---|" + "---:|" * len(weeks),
    ]
    weekly: dict[str, Counter[tuple[int, int]]] = {}
    for v in order:
        weekly[v] = Counter(
            date.fromisoformat(published[s]).isocalendar()[:2]
            for s, r in eff[v].items()
            if r["on_front"] and published.get(s)
        )
        lines.append(f"| {v} | " + " | ".join(str(weekly[v].get(w, 0)) for w in weeks) + " |")
    if len(order) > 1:
        first, last = eff[order[0]], eff[order[-1]]
        moved = Counter(
            (first[s]["kind"], last[s]["kind"])
            for s in first
            if s in last and first[s]["kind"] != last[s]["kind"]
        )
        state = {1: "classified", 0: "discarded"}
        status = Counter(
            (state[first[s]["shown"]], state[last[s]["shown"]]) for s in first if s in last
        )
        lines += [
            "",
            f"Visibility {order[0]} -> {order[-1]}: "
            + ", ".join(f"{a} -> {b}: {n}" for (a, b), n in sorted(status.items())),
            "",
            f"Type changes {order[0]} -> {order[-1]} (top 12):",
            "",
            "| From | To | Stories |",
            "|---|---|---:|",
        ]
        lines += [f"| {a} | {b} | {n} |" for (a, b), n in moved.most_common(12)]
        lines += transitions(store, order[0], order[-1], weeks, weekly)
    return write(args.out, lines)


# how much attention a kind gets from the visibility rules: front page and alerts, alerts
# only, other business news, image, irrelevant
KIND_WEIGHT = {
    **dict.fromkeys(("deal", "footprint"), 4),
    **dict.fromkeys(("regulation", "results", "risk"), 3),
    **dict.fromkeys(("capital", "contract", "corporate", "grant", "leadership"), 2),
    "image": 1,
    "irrelevant": 0,
}
LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}


def transitions(
    store: Store,
    old: str,
    new: str,
    weeks: list[tuple[int, int]],
    weekly: dict[str, Counter[tuple[int, int]]],
) -> list[str]:
    """How the stories read by both versions moved, in each direction."""
    before, after = answers_of(store, old), answers_of(store, new)
    both = [s for s in after if s in before]
    a, b = before, after
    shown_by_both = [s for s in both if a[s]["shown"] and b[s]["shown"]]
    rows = [
        (
            "front page (entered / left)",
            sum(b[s]["on_front"] > a[s]["on_front"] for s in both),
            sum(b[s]["on_front"] < a[s]["on_front"] for s in both),
        ),
        (
            "alert (gained / lost)",
            sum(b[s]["alerts"] > a[s]["alerts"] for s in both),
            sum(b[s]["alerts"] < a[s]["alerts"] for s in both),
        ),
        (
            "relevance level, stories shown by both (higher / lower)",
            sum(LEVEL_RANK[b[s]["level"]] > LEVEL_RANK[a[s]["level"]] for s in shown_by_both),
            sum(LEVEL_RANK[b[s]["level"]] < LEVEL_RANK[a[s]["level"]] for s in shown_by_both),
        ),
        (
            "kind, by weight in the visibility rules (heavier / lighter)",
            sum(KIND_WEIGHT[b[s]["kind"]] > KIND_WEIGHT[a[s]["kind"]] for s in both),
            sum(KIND_WEIGHT[b[s]["kind"]] < KIND_WEIGHT[a[s]["kind"]] for s in both),
        ),
    ]
    more = [w for w in weeks if weekly[new].get(w, 0) > weekly[old].get(w, 0)]
    unread = sum(1 for s in before if s not in after)
    lines = [
        "",
        f"Stories read by both {old} and {new}: {len(both)}. Changes from {old} to {new}, both "
        "ways (kind weight: deal and footprint 4; regulation, results and risk 3; other "
        "business kinds 2; image 1; irrelevant 0):",
        "",
        "| Change | Up | Down |",
        "|---|---:|---:|",
    ]
    lines += [f"| {label} | {up} | {down} |" for label, up, down in rows]
    lines += [
        "",
        f"Weeks with more front-page stories under {new} than under {old}: "
        + (", ".join(f"{y}-W{w:02d}" for y, w in more) or "none")
        + ".",
        f"Stories {old} read and {new} did not: {unread} (what {new} would do with them is not "
        "measured).",
    ]
    return lines


def e4_report(args: argparse.Namespace, store: Store, companies: list[Company]) -> str:
    from company_news_radar import merge

    by_rule = dict(
        store.rows("SELECT author, count(*) FROM decision WHERE act = 'merge' GROUP BY 1")
    )
    visible = store.rows(
        """SELECT origin, count(*) AS n, sum(on_front) AS front, sum(alerts) AS alerts
        FROM story_now WHERE state = 'shown' GROUP BY 1 ORDER BY 1"""
    )
    stored = dict(
        store.rows("SELECT same, count(*) FROM decision WHERE act = 'verdict' GROUP BY 1")
    )
    items = merge.cards(store)
    ignore = merge.name_words(companies)
    strict = merge.doubtful_pairs(items, ignore, {}, None, need_word=True)
    loose = merge.doubtful_pairs(items, ignore, {}, None, need_word=False)
    n_visible = sum(r["n"] for r in visible)
    lines = header(
        "E4: merging repeats",
        command_line(),
        [
            f"Visible stories after merging: {n_visible}",
            f"Judge verdicts stored: same {stored.get(1, 0)}, not the same {stored.get(0, 0)}",
        ],
    )
    lines += ["| Rule | Merges |", "|---|---:|"]
    lines += [f"| {r} | {n} |" for r, n in sorted(by_rule.items())]
    lines += [
        f"| total | {sum(by_rule.values())} |",
        "",
        "Visible stories after merging, by source:",
        "",
        "| Source | Visible | Front page | Alerts |",
        "|---|---:|---:|---:|",
    ]
    lines += [
        f"| {r['origin']} | {r['n']} | {r['front'] or 0} | {r['alerts'] or 0} |" for r in visible
    ]
    lines += [
        f"| total | {n_visible} | {sum(r['front'] or 0 for r in visible)} | "
        f"{sum(r['alerts'] or 0 for r in visible)} |",
        "",
        "Doubtful pairs among the visible stories now (what the judge would be asked):",
        "",
        f"- production's same-day rule applied to these stories (two stories of one company "
        f"within a day): {len(loose)}",
        f"- this rebuild (within a day, also a headline word in common other than the "
        f"companies' names): {len(strict)}",
    ]
    if args.queue:
        merged = [
            (r["first_id"], r["second_id"], r["author"])
            for r in store.rows("SELECT * FROM decision WHERE act = 'merge' ORDER BY id")
        ]
        random.Random(args.seed).shuffle(merged)
        said_no = [
            (r["first_id"], r["second_id"], "judge said no")
            for r in store.rows(
                "SELECT first_id, second_id FROM decision WHERE act = 'verdict' AND same = 0"
                " ORDER BY first_id, second_id"
            )
        ]
        random.Random(args.seed + 1).shuffle(said_no)
        asked = {(a, b) for a, b, _ in said_no}
        near = [
            (a.id, b.id, "near, not asked")
            for a, b in loose
            if (min(a.id, b.id), max(a.id, b.id)) not in asked
        ]
        random.Random(args.seed + 2).shuffle(near)
        controls = (said_no + near)[: args.sample]
        names = {c.id: c.group for c in companies}
        n = judge.merge_queue(
            store, merged[: args.sample], controls, names, args.data_dir / "judge"
        )
        lines += [
            "",
            f"Blind sample written for the judge: {n} pairs ({min(len(merged), args.sample)} "
            f"merged, {len(controls)} not merged: "
            + ", ".join(f"{k} {v}" for k, v in sorted(Counter(w for _, _, w in controls).items()))
            + "), shuffled, without the merge decision.",
        ]
    labels = judge.read_jsonl(args.data_dir / "judge" / "merge_labels.jsonl")
    key = {r["pid"]: r for r in judge.read_jsonl(args.data_dir / "judge" / "merge_key.jsonl")}
    if not labels:
        lines += ["", "Blind labels: not yet available (`data/judge/merge_labels.jsonl`)."]
        return write(args.out, lines)
    same = {lab["pid"]: bool(lab.get("same")) for lab in labels if lab.get("pid") in key}
    merged_pids = [p for p in same if key[p]["merged"]]
    other = [p for p in same if not key[p]["merged"]]
    lines += [
        "",
        f"Against the blind labels (labelled by {args.labelled_by}: agreement, not accuracy):",
        "",
        f"- merged pairs labelled the same event: {sum(same[p] for p in merged_pids)} "
        f"of {len(merged_pids)}",
    ]
    for rule in sorted({key[p]["rule"] for p in merged_pids}):
        ps = [p for p in merged_pids if key[p]["rule"] == rule]
        lines.append(f"  - rule {rule}: {sum(same[p] for p in ps)} of {len(ps)}")
    lines.append(
        f"- not-merged pairs labelled the same event: {sum(same[p] for p in other)} of {len(other)}"
    )
    for why in sorted({key[p]["rule"] for p in other}):
        ps = [p for p in other if key[p]["rule"] == why]
        lines.append(f"  - {why}: {sum(same[p] for p in ps)} of {len(ps)}")
    return write(args.out, lines)


def quota_report(args: argparse.Namespace) -> str:
    from company_news_radar.quota import Quota

    q = Quota(args.data_dir / "quota.json", log_path=args.data_dir / "llm_calls.jsonl")
    caps = sorted({int(r["cap"]) for r in q.calls_log() if r.get("cap")})
    log = [r for r in q.calls_log() if not args.day or r["quota_day"] in args.day]
    answered = sorted({str(r["model_version"]) for r in log if r.get("model_version")})
    lines = header(
        "LLM quota and cost",
        command_line(),
        [
            "Gemini free tier: 500 requests a day per project, shared with another system; this "
            "project's cap (counted on disk before each request): 300 a day by default, "
            + f"caps recorded in the call log: {', '.join(map(str, caps)) or 'none'} "
            f"({sum(1 for r in log if not r.get('cap'))} requests logged without one, before "
            "`--daily-cap` existed, ran under the default)",
            f"Model requested: {', '.join(sorted({str(r['model']) for r in log})) or '-'}; "
            f"versions that answered: {', '.join(answered) or '-'}",
        ],
    )
    codes = sorted({str(r.get("status")) for r in log} - {"200"})
    lines += [
        "| Quota day | Purpose | Requests | OK | "
        + " | ".join(f"{c}" for c in codes)
        + " | Items | Items per OK request | Seconds per request (median) "
        "| Prompt tokens (mean) | Output tokens (mean) |",
        "|---|---|---:|---:|" + "---:|" * len(codes) + "---:|---:|---:|---:|---:|",
    ]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in log:
        groups[(r["quota_day"], r["purpose"])].append(r)
    for (day, purpose), rows in sorted(groups.items()):
        ok = [r for r in rows if r.get("status") == 200]
        failed = Counter(str(r.get("status")) for r in rows if r.get("status") != 200)
        cells = " | ".join(str(failed.get(c, 0)) for c in codes)
        if not ok:
            lines.append(f"| {day} | {purpose} | {len(rows)} | 0 | {cells} | - | - | - | - | - |")
            continue
        items = sum(r.get("items") or 0 for r in ok)
        pt = [r["prompt_tokens"] for r in ok if r.get("prompt_tokens")]
        ot = [r["output_tokens"] for r in ok if r.get("output_tokens")]
        secs = median_text([float(r["seconds"]) for r in ok if r.get("seconds")])
        lines.append(
            f"| {day} | {purpose} | {len(rows)} | {len(ok)} | {cells} | {items} | "
            f"{items / len(ok):.1f} | {secs} | "
            f"{sum(pt) / max(len(pt), 1):.0f} | {sum(ot) / max(len(ot), 1):.0f} |"
        )
    per_day = Counter(r["quota_day"] for r in log)
    counter = q.counts()
    lines += [
        "",
        "| Quota day | Requests in the call log | Persistent counter (`quota.json`) |",
        "|---|---:|---:|",
    ]
    lines += [f"| {d} | {n} | {counter.get(d, 0)} |" for d, n in sorted(per_day.items())]
    lines += [
        "",
        "The counter is written before each request is sent, so it can only be higher than the "
        "log (a run stopped between the two).",
    ]
    return write(args.out, lines)


def gpu_turn(lock: Path, owner: str) -> None:
    """Claims the GPU lock file; exits if another process holds it or Ollama has a model loaded."""
    if lock.exists():
        raise SystemExit(f"GPU busy, lock held: {lock.read_text('utf-8').strip()} ({lock})")
    if shutil.which("ollama"):
        ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True, check=False)
        busy = [line for line in ps.stdout.splitlines()[1:] if line.strip()]
        if busy:
            raise SystemExit("GPU busy, a model is loaded in Ollama:\n" + ps.stdout)
    lock.write_bytes(f"{owner} {datetime.now(UTC).isoformat(timespec='seconds')}\n".encode())


def add_commands(sub: Any) -> None:
    p = sub.add_parser("probe-report", help="volumes per source and stage (no LLM)")
    p.add_argument("--out", type=Path, default=Path("results/probe.md"))
    p.add_argument("--batches", default="10,15,20,25")
    dv = sub.add_parser("dev-split", help="draw the development subset into data/dev")
    dv.add_argument("--prompt", default="v1")
    dv.add_argument("--share", type=float, default=0.3)
    dv.add_argument("--seed", type=int, default=7)
    dr = sub.add_parser("dev-report", help="counts of the development subset")
    dr.add_argument("--out", type=Path, default=Path("results/dev_subset.md"))
    dr.add_argument("--read-by", default="an AI coding assistant")
    e = sub.add_parser("e1-coverage", help="E1, against a borme-radar database")
    e.add_argument("--borme-db", type=Path, required=True)
    e.add_argument("--out", type=Path, default=Path("results/e1_coverage.md"))
    s = sub.add_parser("e2-sample", help="E2, draw the sample and write the blind queue")
    s.add_argument("--n", type=int, default=150)
    s.add_argument("--batch", type=int, default=15)
    s.add_argument("--seed", type=int, default=7)
    s.add_argument("--sample", default="main", help="sample name; other than main = rebatched")
    s.add_argument("--drawn-from", default="v1", help="draw from stories this version read")
    s.add_argument("--exclude", type=Path, default=Path("data/dev/ids.json"))
    r = sub.add_parser("e2-run", help="E2, run one model on the sample")
    r.add_argument("--model", required=True, help="gemini, or an Ollama model tag")
    r.add_argument("--num-ctx", type=int, default=4096)
    r.add_argument("--name", required=True)
    r.add_argument("--prompt", default=prompts.CURRENT, choices=sorted(prompts.VERSIONS))
    r.add_argument("--gpu-lock", type=Path, default=Path("../_gpu.lock"))
    r.add_argument("--sample", default="main", help="sample name")
    rep = sub.add_parser("e2-report", help="E2, compare runs and labels")
    rep.add_argument("--out", type=Path, default=Path("results/e2_local_vs_api.md"))
    rep.add_argument("--labelled-by", default="an external blind judge")
    rep.add_argument("--sample", default="main", help="sample name")
    e3 = sub.add_parser("e3-report", help="E3, front page by version and period")
    e3.add_argument("--out", type=Path, default=Path("results/e3_prompt_versions.md"))
    e4 = sub.add_parser("e4-report", help="E4, merge counts and labels")
    e4.add_argument("--out", type=Path, default=Path("results/e4_merges.md"))
    e4.add_argument("--queue", action="store_true")
    e4.add_argument("--sample", type=int, default=40)
    e4.add_argument("--seed", type=int, default=7)
    e4.add_argument("--labelled-by", default="an external blind judge")
    tuning.add_command(sub)
    q = sub.add_parser("quota-report", help="LLM requests per day and purpose")
    q.add_argument("--out", type=Path, default=Path("results/quota.md"))
    q.add_argument("--day", action="append", default=None, help="limit to a quota day")


def run_command(args: argparse.Namespace) -> int:
    from company_news_radar import cli

    store = cli.open_store(args)
    companies = cli.companies_of(args)
    if args.command == "probe-report":
        body = probe_report(store, [int(b) for b in args.batches.split(",")])
        lines = header("Volume probe, before any LLM call", command_line())
        sys.stdout.write(write(args.out, [*lines, body]))
    elif args.command == "dev-split":
        sys.stdout.write(dev_split(args, store, companies))
    elif args.command == "dev-report":
        sys.stdout.write(dev_report(args, store))
    elif args.command == "e1-coverage":
        sys.stdout.write(e1(args, store, companies))
    elif args.command == "e2-sample":
        sys.stdout.write(e2_sample(args, store, companies))
    elif args.command == "e2-run":
        if args.model == "gemini":
            sys.stdout.write(e2_run(args, store, companies, cli.make_gemini(args), args.name))
        else:
            from company_news_radar.ollama import Ollama

            gpu_turn(args.gpu_lock, f"company-news-radar e2-run {args.name}")
            try:
                llm = Ollama(args.model, args.num_ctx)
                sys.stdout.write(e2_run(args, store, companies, llm, args.name))
            finally:
                subprocess.run(["ollama", "stop", args.model], capture_output=True, check=False)
                args.gpu_lock.unlink(missing_ok=True)
    elif args.command == "e2-report":
        sys.stdout.write(e2_report(args, store))
    elif args.command == "e3-report":
        sys.stdout.write(e3_report(args, store))
    elif args.command == "e4-report":
        sys.stdout.write(e4_report(args, store, companies))
    elif args.command == "tuning-report":
        lines = header("Thresholds checked on the stored data", command_line())
        sys.stdout.write(write(args.out, [*lines, *tuning.report(args, store, companies)]))
    elif args.command == "quota-report":
        sys.stdout.write(quota_report(args))
    else:
        raise SystemExit(f"no handler for {args.command!r}")
    return 0
