"""The press feeds the radar follows, plus the candidates that were tried and dropped.

Run ``company-news-radar sources`` to test them again; docs/sources.md has the last run.
"""

from __future__ import annotations

from typing import NamedTuple


class Feed(NamedTuple):
    slug: str
    outlet: str
    url: str
    region: str


# slug | outlet | url | region (empty for national titles)
_TABLE = """
20minutos/economia | 20minutos, Economía | https://www.20minutos.es/rss/economia/ |
abc/economia | ABC, Economía | https://www.abc.es/rss/2.0/economia/ |
cincodias/companias | Cinco Días, Compañías | https://feeds.elpais.com/mrss-s/pages/ep/site/cincodias.elpais.com/section/companias/portada |
elconfidencial/empresas | El Confidencial, Empresas | https://rss.elconfidencial.com/empresas/ |
elconfidencial/mercados | El Confidencial, Mercados | https://rss.elconfidencial.com/mercados/ |
eldiario/economia | elDiario.es, Economía | https://www.eldiario.es/rss/economia/ |
elespanol/invertia | El Español, Invertia | https://www.elespanol.com/rss/invertia/ |
elmundo/economia | El Mundo, Economía | https://e00-elmundo.uecdn.es/elmundo/rss/economia.xml |
elpais/economia | El País, Economía | https://feeds.elpais.com/mrss-s/pages/ep/site/elpais.com/section/economia/portada |
europapress/economia | Europa Press, Economía | https://www.europapress.es/rss/rss.aspx?ch=00136 |
expansion/empresas | Expansión, Empresas | https://e00-expansion.uecdn.es/rss/empresas.xml |
expansion/mercados | Expansión, Mercados | https://e00-expansion.uecdn.es/rss/mercados.xml |
finanzas/portada | Finanzas.com | https://www.finanzas.com/feed |
idealista/news | idealista/news | https://www.idealista.com/news/rss/v2/latest-news.xml |
lavanguardia/economia | La Vanguardia, Economía | https://www.lavanguardia.com/rss/economia.xml |
merca2/portada | Merca2 | https://www.merca2.es/feed/ |
okdiario/economia | OKDiario, Economía | https://okdiario.com/economia/feed |
periodicoenergia/portada | El Periódico de la Energía | https://elperiodicodelaenergia.com/feed/ |
diariodesevilla/economia | Diario de Sevilla, Economía | https://www.diariodesevilla.es/rss/economia/ | Andalucía
diariovasco/economia | Diario Vasco, Economía | https://www.diariovasco.com/rss/2.0/?section=economia | País Vasco
elcorreo/economia | El Correo, Economía | https://www.elcorreo.com/rss/2.0/?section=economia | País Vasco
heraldo/economia | Heraldo, Economía | https://www.heraldo.es/rss/economia/ | Aragón
lavozdegalicia/economia | La Voz de Galicia, Economía | https://www.lavozdegalicia.es/economia/index.xml | Galicia
"""

FEEDS: tuple[Feed, ...] = tuple(
    Feed(*(cell.strip() for cell in line.split("|"))) for line in _TABLE.strip().splitlines()
)

# tried on 18-19 Nov 2026 and not used; none of these refusals is worked around
LEFT_OUT = """
RTVE, Economía | robots.txt disallows the feed path
elEconomista, Empresas and Mercados | HTTP 403 to this client
Prensa Ibérica regional titles, El Periódico, Deia | HTTP 406 to this client
Cinco Días, Mercados | HTTP 370, not a feed
La Información | HTTP 410, gone
Vozpópuli, Público | HTTP 404
La Razón, Economía | HTTP 503 after retries
El Plural, Bolsamanía, The Objective, Energías Renovables | answered, but no entries parsed
"""


def left_out() -> list[tuple[str, str]]:
    pairs = (line.split("|", 1) for line in LEFT_OUT.strip().splitlines())
    return [(name.strip(), why.strip()) for name, why in pairs]
