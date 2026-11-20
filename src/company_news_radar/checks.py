"""Rule checks on a classifier answer that need no reference label (used by E2).

``violations`` returns the names in ``CHECKS`` that the answer fails. ``person_in_summary``
relies on ``privacy.scrub``, which can also flag a capitalised word after a first name, and
``market_noise_kept`` looks for stock-market wording in the headline when the answer kept
the item as something other than irrelevant or results.
"""

from __future__ import annotations

import re
from typing import Any

from company_news_radar.models import RELEVANCES, TYPES
from company_news_radar.privacy import scrub
from company_news_radar.textutil import without_accents

CHECKS = (
    "missing",
    "summary_too_long",
    "person_in_summary",
    "bad_fact_key",
    "company_out_of_range",
    "market_noise_kept",
)
_KEY = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MARKET = re.compile(
    r"\b(?:precio\s+objetivo|recomendacion|analistas?|cotiza(?:cion)?|valores\s+del\s+ibex|"
    r"bolsa\s+hoy|lidera\s+las\s+(?:subidas|caidas)|acciones\s+de\s+\S+(?:\s+\S+)?\s+"
    r"(?:suben|bajan|caen|se\s+disparan|se\s+desploman))\b",
    re.IGNORECASE,
)


def violations(item: dict[str, Any], answer: dict[str, Any] | None, n_candidates: int) -> list[str]:
    if not answer or answer.get("type") not in TYPES or answer.get("relevance") not in RELEVANCES:
        return ["missing"]
    found = []
    summary = str(answer.get("summary") or "")
    if len(summary.split()) > 25:
        found.append("summary_too_long")
    if scrub(summary) != summary:
        found.append("person_in_summary")
    if not _KEY.fullmatch(str(answer.get("fact_key") or "")):
        found.append("bad_fact_key")
    picked = [k for k in answer.get("companies") or [] if isinstance(k, int)]
    if any(k < 1 or k > n_candidates for k in picked):
        found.append("company_out_of_range")
    headline = without_accents(str(item.get("headline") or ""))
    if _MARKET.search(headline) and answer["type"] not in ("irrelevant", "results"):
        found.append("market_noise_kept")
    return found
