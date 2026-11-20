"""Writes the shown stories of a date range as Markdown.

With details, each story is one line under Alerts, Front page or Other: date, companies,
kind and level, the scrubbed gist, publisher and story id. Headlines and URLs are left out
because they carry people's names more often than the gists do. Without details, the page
only has a table of counts by company and kind.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from company_news_radar.privacy import scrub
from company_news_radar.store import Store
from company_news_radar.watchlist import Company

SHOWN_IN_RANGE = """
SELECT s.*,
       (SELECT group_concat(company) FROM party p WHERE p.story_id = s.id AND p.confirmed = 1)
           AS who
FROM story_now s
WHERE s.state = 'shown' AND substr(s.published, 1, 10) BETWEEN ? AND ?
ORDER BY s.published DESC, s.id
"""


def _rows(store: Store, start: date, end: date) -> list[dict[str, object]]:
    found = store.rows(SHOWN_IN_RANGE, start.isoformat(), end.isoformat())
    return [dict(r) for r in found]


def render(
    store: Store, companies: dict[str, Company], start: date, end: date, details: bool
) -> str:
    rows = _rows(store, start, end)
    name = {c.id: c.group for c in companies.values()}

    def who(r: dict[str, object]) -> str:
        ids = [x for x in str(r["who"] or "").split(",") if x]
        return ", ".join(name.get(i, i) for i in ids) or "(no company confirmed)"

    alerts = [r for r in rows if r["alerts"]]
    front = [r for r in rows if r["on_front"]]
    lines = [
        f"# Company news radar: {start.isoformat()} to {end.isoformat()}",
        "",
        f"Visible stories: {len(rows)}; front page: {len(front)}; alerts: {len(alerts)}.",
        "",
    ]
    if not details:
        counts = Counter((who(r), str(r["kind"])) for r in rows)
        kinds = sorted({k for _, k in counts})
        lines += ["| Company | " + " | ".join(kinds) + " |", "|---|" + "---:|" * len(kinds)]
        for company in sorted({c for c, _ in counts}):
            lines.append(
                f"| {company} | "
                + " | ".join(str(counts.get((company, k), 0)) for k in kinds)
                + " |"
            )
        lines += ["", "No headlines, summaries or links: generated with `--no-details`."]
        return "\n".join(lines) + "\n"

    def line(r: dict[str, object]) -> str:
        return (
            f"- {str(r['published'])[:10]} · **{who(r)}** · {r['kind']} / {r['level']} · "
            f"{scrub(str(r['gist'] or ''))} ({r['publisher'] or ''}; story {r['id']})"
        )

    listed: set[object] = set()
    for heading, group in (
        ("Alerts", alerts),
        ("Front page", front),
        ("Other visible stories", rows),
    ):
        todo = [r for r in group if r["id"] not in listed]
        if not todo:
            continue
        lines += [f"## {heading} ({len(todo)})", ""]
        lines += [line(r) for r in todo]
        lines.append("")
        listed |= {r["id"] for r in todo}
    return "\n".join(lines)
