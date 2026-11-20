"""Rule-based checks used by process.py and classify.py; no model is involved.

``foreign_outlet`` reads the country-code domain of the publisher, ``worth_keeping`` asks
for a named company or a company-specific channel, ``market_noise`` spots quote pages and
market-session reports by their wording, and ``below_floor`` compares a grant or contract
amount with its minimum (a missing or zero amount never counts as below).
"""

from __future__ import annotations

import re

from company_news_radar import config
from company_news_radar.models import Mention
from company_news_radar.textutil import host, without_accents

# headlines of quote and tag pages rather than news
QUOTE_PAGE = re.compile(
    r"^(?:cotizacion\b|acciones\s+de\s+\S.*\bhoy\b|ultima\s+hora\s+de\s+|noticias\s+(?:de|sobre)\s+)"
    r"|\b(?:en\s+bolsa\s+hoy|precio\s+de\s+la\s+accion)\b",
    re.IGNORECASE,
)
# market report: an index or 'the market' as subject, followed by a move or a session word
MARKET_WORDS = (
    r"(?:el\s+)?(?:ibex(?:[\s-]*35)?|selectivo|parque|bolsas?(?:\s+espanola)?|mercados?"
    r"|wall\s+street)"
)
MOVES = (
    r"(?:abre|abren|cierra|cierran|arranca|empieza|termina|sube|suben|baja|bajan|cae|caen|"
    r"avanza|retrocede|recupera|mantiene|pierde|gana|se\s+dispara|se\s+desploma|sesion|"
    r"jornada|semana|en\s+(?:rojo|verde)|al\s+alza|a\s+la\s+baja|puntos)"
)
SESSION = re.compile(rf"^\W*{MARKET_WORDS}\b.{{0,70}}?\b{MOVES}\b", re.IGNORECASE)


def foreign_outlet(web: str | None) -> bool:
    name = host(web)
    return bool(name) and name.rsplit(".", 1)[-1] in config.FOREIGN_CCTLDS


def market_noise(title: str, named_in_title: bool) -> str | None:
    """Name of the noise found, or None; session reports count only if no company leads."""
    text = without_accents(title or "").strip()
    if QUOTE_PAGE.search(text):
        return "share-price page"
    if not named_in_title and SESSION.search(text):
        return "market session report"
    return None


def worth_keeping(source_type: str, mentions: list[Mention], watched: str | None) -> bool:
    return bool(mentions) or (source_type in ("bing_news", "newsroom") and watched is not None)


def below_floor(story_type: str | None, amount: float | None) -> bool:
    if not amount:
        return False
    floor = {"grant": config.GRANT_FLOOR_EUR, "contract": config.CONTRACT_FLOOR_EUR}
    return story_type in floor and amount < floor[story_type]
