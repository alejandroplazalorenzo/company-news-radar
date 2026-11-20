"""Text sent to the models: the classifier prompt (one per version) and the pair judge.

The meaning of every answer field sits in its JSON-schema ``description``, and the prompt
includes the schema, so the hosted and the local model read the same definitions. Items and
pairs go in as one JSON object per line, with public fields only.
"""

from __future__ import annotations

import json
from typing import Any

from company_news_radar.models import RELEVANCES, TAXONOMY, TYPES

SNIPPET_CHARS = 300  # a batch of 15 then fits the 4,096-token context of the local model

# classifier

ITEM_FIELDS: dict[str, Any] = {
    "ref": {"type": "integer", "description": "The ref of the item this entry answers."},
    "type": {
        "type": "string",
        "enum": list(TYPES),
        "description": (
            "Kind of business news, from the list of types. If the item tells several facts, "
            "type the one in the headline."
        ),
    },
    "relevance": {
        "type": "string",
        "enum": list(RELEVANCES),
        "description": "How much the fact changes the business of the company it is about.",
    },
    "summary": {
        "type": "string",
        "description": (
            "One English sentence of 25 words or fewer: the actor, the action and its object. "
            "Companies, public bodies and job titles only; never the name of a person."
        ),
    },
    "companies": {
        "type": "array",
        "items": {"type": "integer"},
        "description": (
            "The n of each candidate that is a party to the fact. An empty list when no "
            "candidate is, for instance when the name belongs to someone else."
        ),
    },
    "country": {
        "type": "string",
        "description": (
            "English name of the country where the fact happens: where the plant, market, "
            "buyer, court or regulator is. For a fact of the whole company with no place (its "
            "results, a bond, a board change), the country of its head office."
        ),
    },
    "fact_key": {
        "type": "string",
        "description": (
            "Identifier of the event in lower-case ASCII words joined by hyphens, built as "
            "actor-action-object, then place or period if they tell events apart, e.g. "
            "acerinox-buys-plant-alabama. Fixed forms: yearly results "
            "<company>-results-<year>; a quarter or half <company>-results-<q1|h1|9m>-<year>; "
            "a takeover bid <bidder>-bid-<target>. Two items about one event should get one key."
        ),
    },
}
SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {"type": "object", "properties": ITEM_FIELDS, "required": list(ITEM_FIELDS)},
        }
    },
    "required": ["items"],
}


_TYPES_BLOCK = "\n".join(f"- {k.name}: {k.meaning}" for k in TAXONOMY)

_V1 = f"""You sort short news items about large Spanish listed groups for an analyst who \
follows those groups. Read only what each item gives (headline, outlet, date, snippet) and \
classify it.

Types:
{_TYPES_BLOCK}

Relevance is high, medium or low.

Each item lists candidate companies, numbered by n: watched groups whose name the item \
contains. Some are homonyms or passing mentions."""

# added in v2, see docs/prompt_versions.md
_V2_RULES = """

How much it matters (relevance), for someone who follows the company:
- high: decided or done, and it changes the size, ownership, sites or finances of the company: \
a purchase or sale agreed or closed, a new or closed site of real weight, a period's results, \
a large fine, a strike that stops work, a new chief executive or chair.
- medium: a real change of a smaller size, or a large one not decided yet (talks, studies, an \
offer not yet accepted, a project announced without a final decision).
- low: real but routine for a group of this size: a regional reorganisation, a minor \
appointment, a local incident, a payment already announced.

Rules:
1. Stock-market items are irrelevant: share-price moves and their causes, analysts' ratings \
and targets, chart signals, buy-or-sell advice, dividend calendars. That holds even when the \
reason for the move is a deal or a set of results.
2. A deal needs a business, or a stake of 3% or more, to change owner: agreed, closed, or \
offered formally. Commercial alliances, joint offers to customers, technology partnerships, \
consortia and talks about working together are not deals (a signed large order is a contract; \
the rest is image).
3. The company must be the one acting or the one the event happens to. Do not list a candidate \
that is only a competitor, partner, lender, adviser, landlord, former owner or the place where \
something happens, nor a company whose shareholders, founding family or managers act on their \
own account: if no candidate is left, the item is irrelevant.
4. Footprint is only a site that opens, closes or moves, or a country, market or business line \
the company enters or leaves. Works, upgrades, maintenance and investment in sites or networks \
it already runs, grid connections and substations, progress or delays of a project already \
announced, new routes or capacity from existing sites, a regional reorganisation, feasibility \
tests and visits are not footprint.
5. Capital is money the company raises or returns. An investment plan or budget is corporate. \
The payment date of a dividend already declared, dividend calendars and the rates of savings \
products are irrelevant.
6. A contract is an order the company wins or loses as a supplier. When it is the client (it \
hires a technology provider) or has only bid, it is not a contract: image, or irrelevant.
7. Opinions and statements without a decision (an executive, a politician or a mayor defends, \
warns or asks for something), political proposals, profiles of executives and their pay, and \
consumer offers are irrelevant."""

VERSIONS: dict[str, str] = {
    "v1": _V1,
    "v2": _V1 + _V2_RULES,
}
CURRENT = "v2"


def compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def payload(
    story_id: int,
    headline: str,
    publisher: str | None,
    published: str | None,
    standfirst: str | None,
    candidates: list[str],
) -> dict[str, Any]:
    return {
        "ref": story_id,
        "headline": headline,
        "outlet": publisher or "",
        "date": (published or "")[:10],
        "snippet": " ".join((standfirst or "")[:SNIPPET_CHARS].split()),
        "candidates": [{"n": n, "company": c} for n, c in enumerate(candidates, start=1)],
    }


def classifier(version: str, items: list[dict[str, Any]]) -> str:
    lines = "\n".join(compact(i) for i in items)
    return (
        f"{VERSIONS[version]}\n\n"
        "Reply with one JSON object that follows this schema; the description of each field "
        "says what goes in it. One entry per item, every item answered.\n"
        f"{compact(SCHEMA)}\n\n"
        f"Items, one JSON object per line:\n{lines}\n"
    )


# judge

PAIR_FIELDS: dict[str, Any] = {
    "a": {"type": "integer", "description": "The a of the pair, copied."},
    "b": {"type": "integer", "description": "The b of the pair, copied."},
    "same": {
        "type": "boolean",
        "description": "true only if both items are about one single event.",
    },
}
JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "items": {"type": "object", "properties": PAIR_FIELDS, "required": list(PAIR_FIELDS)},
        }
    },
    "required": ["pairs"],
}

JUDGES: dict[str, str] = {
    "j1": """A digest of business news about Spanish listed groups shows each event once. \
Below are pairs of items the radar could not settle by itself. For each pair, decide whether \
the two items are about one single event.

One event: the same parties, the same action, the same object. The headline wording, how \
much detail each item gives, which name it uses for the company (the parent, a subsidiary, a \
brand) and the day it came out do not matter. For example, "Repsol sells 25% of its \
renewables arm to a fund" and "The oil group closes the sale of a renewables stake" are one \
event.

Two events: another action on the same object (a bid launched and the same bid accepted, a \
plan announced and the plan approved), another object for the same action (two contracts, \
two plants, two bond issues, two quarters' results), or a later step that brings a new fact \
rather than retelling the old one.

In doubt, answer false: a wrong merge hides news, a missed one only repeats it.""",
}
CURRENT_JUDGE = "j1"


def card(story: dict[str, Any]) -> dict[str, Any]:
    return {
        "headline": story["headline"],
        "outlet": story.get("publisher") or "",
        "date": (story.get("published") or "")[:10],
        "type": story.get("kind") or "",
        "summary": story.get("gist") or "",
        "snippet": " ".join((story.get("standfirst") or "")[:SNIPPET_CHARS].split()),
        "companies": story.get("companies") or [],
    }


def judge(version: str, pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> str:
    lines = "\n".join(
        compact({"a": x["id"], "b": y["id"], "first": card(x), "second": card(y)}) for x, y in pairs
    )
    return (
        f"{JUDGES[version]}\n\n"
        "Reply with one JSON object that follows this schema, one entry per pair:\n"
        f"{compact(JUDGE_SCHEMA)}\n\n"
        f"Pairs, one JSON object per line:\n{lines}\n"
    )
