"""Entry point. Each stage is its own command and runs only when called:

fetch      --since DAY [--weekly]   read the sources (--weekly adds BDNS and TED)
process                             parties, triage, page standfirsts, exact repeats
probe                               volumes and LLM requests needed, no LLM call
classify   [--prompt V]             verdicts for stories that have none
reclassify --prompt V               drop model verdicts and classify again
merge      [--judge]                fold repeats
digest     --since DAY              Markdown digest (--no-details: counts only)
quota                               LLM requests used today
sources                             test the feeds and their robots.txt
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from company_news_radar import config, entities, env
from company_news_radar.store import Store
from company_news_radar.watchlist import Company, load, load_newsrooms, with_newsrooms

log = logging.getLogger("company_news_radar")


def _day(text: str) -> date:
    return date.fromisoformat(text)


def build_parser() -> argparse.ArgumentParser:
    from company_news_radar import experiments, prompts

    ap = argparse.ArgumentParser(
        prog="company-news-radar",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--data-dir", type=Path, default=Path("data"))
    ap.add_argument("--watchlist", type=Path, default=Path("examples/watchlist.csv"))
    ap.add_argument("--newsrooms", type=Path, default=Path("examples/newsrooms.json"))
    ap.add_argument("--env", type=Path, default=Path(".env"))
    ap.add_argument(
        "--daily-cap",
        type=int,
        default=config.DAILY_CAP,
        help=f"daily limit on LLM requests; {config.DAILY_CAP} by default, never over "
        f"{config.FREE_TIER_PER_DAY}",
    )
    sub = ap.add_subparsers(dest="command", required=True)

    f = sub.add_parser("fetch", help="read the sources")
    f.add_argument(
        "--since",
        type=_day,
        help="start date; when left out, resume a day before the previous fetch",
    )
    f.add_argument("--until", type=_day, default=None)
    f.add_argument("--weekly", action="store_true", help="include the BDNS and TED registers")
    f.add_argument("--no-feeds", action="store_true")
    f.add_argument("--official-only", action="store_true", help="registers only")
    f.add_argument(
        "--only",
        action="append",
        choices=("bing_news", "feed", "newsroom", "borme_c", "bdns", "ted"),
        help="limit to this origin; may be given more than once",
    )

    sub.add_parser("process", help="turn new captures into stories")
    p = sub.add_parser("probe", help="print the probe report")
    p.add_argument("--batches", default="10,15,20,25")

    for name, what in (
        ("classify", "give a verdict to stories without one"),
        ("reclassify", "delete model verdicts, then classify"),
    ):
        c = sub.add_parser(name, help=what)
        c.add_argument("--prompt", default=prompts.CURRENT, choices=sorted(prompts.VERSIONS))
        c.add_argument("--batch", type=int, default=config.BATCH_SIZE)
        c.add_argument("--max-calls", type=int, default=None)
        c.add_argument("--llm", choices=("gemini", "none"), default="gemini")
        if name == "reclassify":
            c.add_argument(
                "--only-visible",
                action="store_true",
                help="limit to stories shown now",
            )
            c.add_argument(
                "--ids", type=Path, default=None, help="JSON file with a list of story ids"
            )

    m = sub.add_parser("merge", help="fold stories about one event")
    m.add_argument("--judge", action="store_true", help="put unclear pairs to the LLM judge")
    m.add_argument("--manual", type=Path, default=None, help="JSON-lines file of pair verdicts")

    d = sub.add_parser("digest", help="write the shown stories of a period")
    d.add_argument("--since", type=_day, required=True)
    d.add_argument("--until", type=_day, default=None)
    d.add_argument("--no-details", action="store_true")
    d.add_argument("--out", type=Path, default=None)

    sub.add_parser("quota", help="show today's LLM request count against the cap")
    sub.add_parser("stats", help="counts from the store")
    sub.add_parser("sources", help="test each feed and report robots.txt per host")
    sub.add_parser("newsrooms", help="print the newsroom configuration")

    experiments.add_commands(sub)
    return ap


def companies_of(args: argparse.Namespace) -> list[Company]:
    return with_newsrooms(load(args.watchlist), load_newsrooms(args.newsrooms))


def open_store(args: argparse.Namespace) -> Store:
    return Store(args.data_dir / "radar.sqlite")


def make_quota(args: argparse.Namespace) -> Any:
    from company_news_radar.quota import Quota

    return Quota(
        args.data_dir / "quota.json", cap=args.daily_cap, log_path=args.data_dir / "llm_calls.jsonl"
    )


def make_gemini(args: argparse.Namespace) -> Any:
    from company_news_radar.gemini import Gemini

    key = env.get("GEMINI_API_KEY", args.env)
    if not key:
        raise SystemExit("set GEMINI_API_KEY in the environment or in .env first")
    return Gemini(key, make_quota(args))


# Calibration texts: every capture from a general press feed. Search and newsroom captures
# are left out because they were fetched for one company and overstate how often it appears.
CALIBRATION_TEXTS = (
    "SELECT headline || ' ' || coalesce(standfirst, '') FROM capture WHERE origin = 'feed'"
)


def dictionary(store: Store, companies: list[Company]) -> entities.Dictionary:
    d = entities.build(companies)
    dropped = entities.calibrate(d, [r[0] for r in store.rows(CALIBRATION_TEXTS)])
    if dropped:
        log.info(
            "calibration removed %d derived keys: %s", len(dropped), ", ".join(sorted(dropped))
        )
    return d


def cmd_fetch(args: argparse.Namespace) -> int:
    from company_news_radar.extract import Window, extract
    from company_news_radar.net import Client

    store = open_store(args)
    until = args.until or date.today()
    last = store.last_fetch()
    since = args.since or (
        datetime.fromisoformat(last).date() - timedelta(days=1)
        if last
        else until - timedelta(days=2)
    )
    window = Window(
        since,
        until,
        weekly=args.weekly,
        feeds=not args.no_feeds,
        official_only=args.official_only,
        only=frozenset(args.only) if args.only else None,
    )
    purpose = "fetch weekly" if args.weekly else "fetch"
    client = Client()
    try:
        with store.logged_run(purpose, since.isoformat()) as report:
            report.update(extract(store, client, companies_of(args), window))
    finally:
        client.close()
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


def cmd_process(args: argparse.Namespace) -> int:
    from company_news_radar.net import Client
    from company_news_radar.process import process

    store = open_store(args)
    client = Client()
    try:
        with store.logged_run("process", None) as report:
            report.update(process(store, dictionary(store, companies_of(args)), client))
            report.update(client.summary())
    finally:
        client.close()
    print(json.dumps(report, indent=1, ensure_ascii=False))
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    from company_news_radar.classify import classify, reopen

    store = open_store(args)
    companies = {c.id: c for c in companies_of(args)}
    if args.command == "reclassify":
        ids = json.loads(args.ids.read_text("utf-8")) if args.ids else None
        print(f"stories reopened: {reopen(store, only_visible=args.only_visible, story_ids=ids)}")
    llm = None if args.llm == "none" else make_gemini(args)
    stats = classify(
        store, companies, llm, args.prompt, batch_size=args.batch, max_calls=args.max_calls
    )
    print(json.dumps(stats, indent=1))
    return 0


def cmd_merge(args: argparse.Namespace) -> int:
    from company_news_radar.merge import load_manual, merge

    store = open_store(args)
    manual = args.manual or args.data_dir / "judge" / "manual_verdicts.jsonl"
    print(f"pair verdicts read from file: {load_manual(store, manual)}")
    judge = make_gemini(args) if args.judge else None
    print(json.dumps(merge(store, companies_of(args), judge=judge), indent=1))
    return 0


def cmd_digest(args: argparse.Namespace) -> int:
    from company_news_radar.digest import render

    text = render(
        open_store(args),
        {c.id: c for c in companies_of(args)},
        args.since,
        args.until or date.today(),
        details=not args.no_details,
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_bytes(text.encode("utf-8"))
        print(f"digest written to {args.out}")
    else:
        sys.stdout.write(text)
    return 0


def cmd_quota(args: argparse.Namespace) -> int:
    from company_news_radar.quota import next_reset, quota_day

    q = make_quota(args)
    now = datetime.now(UTC)
    print(
        f"quota day {quota_day(now)}: used {q.used_today()} of {q.cap}; left {q.remaining()}; "
        f"all days {q.used_total()}; resets {next_reset(now).isoformat(timespec='minutes')}"
    )
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    store = open_store(args)
    queries = {
        "captures by origin": "SELECT origin, count(*) FROM capture GROUP BY 1",
        "triage": "SELECT coalesce(triage, 'waiting'), count(*) FROM capture GROUP BY 1",
        "stories by state": "SELECT state, count(*) FROM story_now GROUP BY 1",
        "why hidden": """SELECT CASE WHEN why_hidden LIKE 'repeat of%' THEN 'repeat'
                      ELSE why_hidden END, count(*) FROM verdict WHERE shown = 0 GROUP BY 1""",
        "shown by kind": "SELECT kind, count(*) FROM verdict WHERE shown = 1 GROUP BY 1",
        "front page and alerts": """SELECT 'front page', count(*) FROM verdict WHERE on_front = 1
                       UNION ALL SELECT 'alerts', count(*) FROM verdict WHERE alerts = 1""",
    }
    out: dict[str, Any] = {
        label: dict(map(tuple, store.rows(sql))) for label, sql in queries.items()
    }
    failing, idle = store.health()
    out["failing sources"] = {r["source"]: r["error"] for r in failing}
    out["silent sources"] = [r["source"] for r in idle]
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    return 0


def cmd_sources(args: argparse.Namespace) -> int:
    from company_news_radar.net import Client, Disallowed, HttpError
    from company_news_radar.sources import catalogue, press

    client = Client()
    try:
        for f in catalogue.FEEDS:
            try:
                items = press.read_feed(client, f.url, press.Channel(f.slug, f.outlet))
            except Disallowed:
                print(f"robots.txt {f.slug:28} disallowed")
                continue
            except HttpError as exc:
                print(f"failed     {f.slug:28} {str(exc)[:90]}")
                continue
            newest = max((i.published or "" for i in items), default="")
            print(f"ok         {f.slug:28} entries={len(items):4} newest={newest[:10]}")
        for name, why in catalogue.left_out():
            print(f"left out   {name}: {why}")
        for name, verdict in client.robots_report().items():
            print(f"robots     {name}: {verdict}")
    finally:
        client.close()
    return 0


def cmd_newsrooms(args: argparse.Namespace) -> int:
    print(json.dumps(load_newsrooms(args.newsrooms), indent=1, ensure_ascii=False))
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    from company_news_radar.experiments import probe_report

    print(probe_report(open_store(args), [int(b) for b in args.batches.split(",")]))
    return 0


COMMANDS = {
    "fetch": cmd_fetch,
    "process": cmd_process,
    "probe": cmd_probe,
    "classify": cmd_classify,
    "reclassify": cmd_classify,
    "merge": cmd_merge,
    "digest": cmd_digest,
    "quota": cmd_quota,
    "stats": cmd_stats,
    "sources": cmd_sources,
    "newsrooms": cmd_newsrooms,
}


def main(argv: Sequence[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S"
    )
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    args = build_parser().parse_args(argv)
    if args.command in COMMANDS:
        return COMMANDS[args.command](args)
    from company_news_radar import experiments

    return experiments.run_command(args)
