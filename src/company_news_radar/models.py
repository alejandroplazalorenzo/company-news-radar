"""Shared vocabulary: the story types, where items come from, the item and the link to a
company, and the two policies that pick front-page stories and alerts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Kind:
    name: str
    meaning: str


TAXONOMY: tuple[Kind, ...] = (
    Kind(
        "deal",
        "Ownership or control changes hands: the company buys, sells or merges a business, "
        "launches or receives a takeover bid, forms a joint venture, or a holder crosses a "
        "significant stake in it.",
    ),
    Kind(
        "results",
        "Figures of a closed period (quarter, half, year) or a change in the targets the "
        "company gave the market, including profit warnings.",
    ),
    Kind(
        "capital",
        "Money raised or returned: shares issued or bought back, a dividend declared, bonds "
        "or loans signed, or a rating agency changing the company's rating.",
    ),
    Kind(
        "leadership",
        "Someone joins or leaves the board or the top executive team.",
    ),
    Kind(
        "footprint",
        "Where the company operates changes: a plant, office, store, branch network or data "
        "centre opens, closes or moves, or it enters or leaves a country or a business.",
    ),
    Kind(
        "contract",
        "An order or contract of significant size is won or lost, public tenders included.",
    ),
    Kind(
        "grant",
        "A public body awards the company a grant or a subsidy.",
    ),
    Kind(
        "risk",
        "Something that can hurt operations or money: layoffs, strikes, fines and "
        "sanctions, lawsuits and investigations, insolvency, a cyber-attack, an accident "
        "that halts activity.",
    ),
    Kind(
        "regulation",
        "A dated rule from a lawmaker, regulator or court (a law, a tax, a tariff, a "
        "licence decision) that changes the business of the company or of its sector in "
        "Spain.",
    ),
    Kind(
        "corporate",
        "Governance and legal housekeeping of the company itself: a shareholders' meeting, "
        "amended articles, a new registered office or company name, a strategic plan "
        "presented to investors.",
    ),
    Kind(
        "image",
        "Publicity with nothing new in what the company owns, where it operates or how it "
        "is financed: a product or service on sale, advertising, a sponsorship, a prize or "
        "a ranking, an event it hosts, a foundation or social programme, an interview or a "
        "profile.",
    ),
    Kind(
        "irrelevant",
        "Nothing changes in the company's business: share-price moves, analyst notes and "
        "price targets, lists and rankings of stocks, a homonym, or the company only in "
        "passing.",
    ),
)
TYPES: dict[str, str] = {k.name: k.meaning for k in TAXONOMY}
RELEVANCES = ("high", "medium", "low")

PRESS = frozenset({"bing_news", "feed", "newsroom"})
# Register records arrive typed and owned, so they never go through the LLM.
OFFICIAL = frozenset({"borme_c", "bdns", "ted"})
SOURCES = tuple(sorted(PRESS | OFFICIAL))


@dataclass
class Item:
    """A result fetched from a source; ``ident`` keeps a rerun from storing it twice."""

    ident: str
    url: str
    headline: str
    origin: str  # a value in SOURCES
    channel: str  # the search query, feed, sitemap or register that produced it
    published: str | None = None  # UTC, ISO 8601
    publisher: str | None = None
    publisher_host: str | None = None
    standfirst: str | None = None
    subject: str | None = None  # set by company-specific channels
    record_type: str | None = None  # registers only, like record_level
    record_level: str | None = None
    amount_eur: float | None = None
    tax_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Mention:
    """Why an item is linked to a watched company."""

    company: str
    how: str  # alias, name, query, newsroom, tax_id; merged when a merge copied it
    evidence: str = ""
    tax_id: str | None = None


# Front page: deals and footprint changes, high or medium, in Spain.
FRONT_PAGE = {"types": frozenset({"deal", "footprint"}), "relevance": frozenset({"high", "medium"})}

# Each rule: the types it covers, whether a watched company must be confirmed, the levels.
ALERT_POLICY: tuple[tuple[frozenset[str], bool, frozenset[str]], ...] = (
    (frozenset({"deal", "footprint", "results", "risk"}), True, frozenset(RELEVANCES)),
    (frozenset({"regulation", "risk"}), False, frozenset({"high"})),
)

# Story types the topic rule of the merger may join.
TOPIC_TYPES = frozenset({"regulation", "risk", "results"})


def front_page(kind: str | None, relevance: str | None, in_spain: bool) -> bool:
    return in_spain and kind in FRONT_PAGE["types"] and relevance in FRONT_PAGE["relevance"]


def alerts(kind: str | None, about_watched: bool, relevance: str | None) -> bool:
    return any(
        kind in kinds and (about_watched or not needs_company) and relevance in levels
        for kinds, needs_company, levels in ALERT_POLICY
    )
