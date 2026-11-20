"""Three public registers: BORME Section C, BDNS grants and TED contract awards.

A register record already names its company and its kind, so the LLM never sees it. Each
record becomes its own story; process.py does not fold two of them into one.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from typing import Any

from company_news_radar import config
from company_news_radar.models import Item
from company_news_radar.net import Client
from company_news_radar.textutil import iso_utc, normalise

BOE_SUMMARY = "https://www.boe.es/datosabiertos/api/borme/sumario/{day:%Y%m%d}"
BOE_NOTICE = "https://www.boe.es/diario_borme/txt.php?id={record}"
BDNS_SEARCH = "https://www.infosubvenciones.es/bdnstrans/api/concesiones/busqueda"
BDNS_PAGE = "https://www.infosubvenciones.es/bdnstrans/GE/es/convocatorias/{call}"
TED_SEARCH = "https://api.ted.europa.eu/v3/notices/search"
TED_PAGE = "https://ted.europa.eu/en/notice/-/detail/{number}"
TED_IDS_PER_QUERY = 50
TED_FIELDS = (
    "publication-number publication-date winner-identifier winner-name buyer-name"
    " notice-title result-value-notice"
).split()

# Section C headings mapped to a story kind; '_' stands for a space. Any other heading is
# corporate/low. When words of several kinds appear, the higher level wins, then the kind
# that sorts first.
HEADING_WORDS = {
    "capital": "ACCIONES_PROPIAS CAPITAL EMISION OBLIGACIONES",
    "deal": "ABSORCION CESION_GLOBAL ESCISION FUSION SEGREGACION",
    "risk": "CONCURSO DISOLUCION LIQUIDACION",
}
KIND_LEVEL = {"capital": "medium", "deal": "high", "risk": "high"}
LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}


def listify(value: Any) -> list[Any]:
    """None, one object or a list, always as a list (the BOE JSON uses all three)."""
    return [] if value is None else value if isinstance(value, list) else [value]


def pluck(node: Any, *path: str) -> Iterator[Any]:
    for each in listify(node):
        if not path:
            yield each
        elif isinstance(each, dict):
            yield from pluck(each.get(path[0]), *path[1:])


def euros(amount: float | None) -> str:
    return f"{amount:,.0f}".replace(",", ".") + " EUR" if amount else "unstated amount"


def name_key(name: str) -> str:
    return normalise(name)


PUBLISHER = {"borme_c": "BORME", "bdns": "BDNS", "ted": "TED"}
IDENT_PREFIX = {"borme_c": "borme", "bdns": "bdns", "ted": "ted"}


def record(
    register: str,
    rid: str,
    url: str,
    headline: str,
    when: str,
    typed: tuple[str, str],
    company: str,
    tax_ids: tuple[str, ...] = (),
    amount: float | None = None,
) -> Item:
    return Item(
        ident=f"{IDENT_PREFIX[register]}:{rid}",
        url=url,
        headline=headline,
        origin=register,
        channel=register,
        published=iso_utc(when),
        publisher=PUBLISHER[register],
        subject=company,
        record_type=typed[0],
        record_level=typed[1],
        amount_eur=amount,
        tax_ids=tax_ids,
    )


# BORME Section C


def heading_type(heading: str) -> tuple[str, str]:
    text = normalise(heading)
    kinds = [
        kind
        for kind, listed in HEADING_WORDS.items()
        if any(w.replace("_", " ") in text for w in listed.split())
    ]
    if not kinds:
        return "corporate", "low"
    best = min(kinds, key=lambda k: (-LEVEL_RANK[KIND_LEVEL[k]], k))
    return best, KIND_LEVEL[best]


def without_role(line: str) -> str:
    """Drops trailing brackets: 'X, S.A. (SOCIEDAD ABSORBIDA)' gives 'X, S.A.'."""
    text = line.strip()
    while text.endswith(")") and "(" in text:
        text = text[: text.rindex("(")].rstrip()
    return text


def names_in(title: str) -> list[str]:
    return list(filter(None, map(without_role, title.splitlines())))


@dataclass
class BormeC:
    company_of: dict[str, str]  # key: name_key of a registered name

    def parse(self, data: dict[str, Any], day: date) -> list[Item]:
        found = []
        for section in pluck(data, "data", "sumario", "diario", "seccion"):
            for part in pluck(section, "apartado") if section.get("codigo") == "C" else ():
                heading = str(part.get("nombre") or "")
                for notice in pluck(part, "item"):
                    names = names_in(str(notice.get("titulo") or ""))
                    ours = [self.company_of.get(name_key(n)) for n in names]
                    owner = next(filter(None, ours), None)
                    if owner is None:
                        continue
                    rid = str(notice.get("identificador"))
                    headline = f"BORME-C, {heading.capitalize()}: {'; '.join(names)}"
                    url = notice.get("url_html") or BOE_NOTICE.format(record=rid)
                    found.append(
                        record(
                            "borme_c",
                            rid,
                            str(url),
                            headline,
                            day.isoformat(),
                            heading_type(heading),
                            owner,
                        )
                    )
        return found

    def fetch(self, client: Client, day: date) -> list[Item]:
        url = BOE_SUMMARY.format(day=day)
        answer = client.get(
            url, headers={"Accept": "application/json"}, pause_s=config.PAUSE_SUMMARY_S
        )
        return self.parse(answer.json(), day)


# BDNS


def bdns_items(rows: Iterable[dict[str, Any]], tax_id: str, company: str) -> list[Item]:
    def one(g: dict[str, Any]) -> Item:
        amount = float(g.get("importe") or 0) or None
        giver = g.get("nivel3") or g.get("nivel2")
        headline = f"BDNS grant of {euros(amount)}: {g.get('convocatoria') or ''}"
        return record(
            "bdns",
            str(g.get("codConcesion") or g.get("id")),
            BDNS_PAGE.format(call=g.get("numeroConvocatoria") or ""),
            headline + (f" ({giver})" if giver else ""),
            str(g.get("fechaConcesion") or ""),
            ("grant", "medium"),
            company,
            (tax_id,),
            amount,
        )

    return [one(g) for g in rows]


def bdns(
    client: Client, tax_id: str, company: str, since: date, page_size: int = 200
) -> list[Item]:
    query = {
        "vpd": "GE",
        "nifCif": tax_id,
        "fechaDesde": since.strftime("%d/%m/%Y"),
        "pageSize": page_size,
    }
    found: list[Item] = []
    for page in range(10_000):
        data = client.get(BDNS_SEARCH, params={**query, "page": page}).json()
        rows = listify(data.get("content"))
        found += bdns_items(rows, tax_id, company)
        last = data.get("totalPages")
        if len(rows) < page_size or (isinstance(last, int) and page + 1 >= last):
            break
    return found


# TED


def ted_text(value: Any) -> str:
    """Text of a field that may be split by language; prefers spa, then eng, then any."""
    while isinstance(value, dict | list):
        if isinstance(value, list):
            value = value[0] if value else ""
        else:
            lang = next((k for k in ("spa", "eng", *value) if k in value), None)
            value = value[lang] if lang else ""
    return str(value or "").strip()


def ted_items(notices: Iterable[dict[str, Any]], company_of_tax_id: dict[str, str]) -> list[Item]:
    found = []
    for n in notices:
        winners = (str(w).upper() for w in listify(n.get("winner-identifier")))
        ours = tuple(
            dict.fromkeys(
                t
                for t in (w.removeprefix("ES") if len(w) == 11 else w for w in winners)
                if t in company_of_tax_id
            )
        )
        if not ours:
            continue
        head, dash, rest = ted_text(n.get("notice-title")).partition(f" {chr(0x2013)} ")
        title = rest if dash and normalise(head) in ("ESPANA", "SPAIN") else head + dash + rest
        try:
            amount = float(ted_text(n.get("result-value-notice"))) or None
        except ValueError:
            amount = None
        buyer = ted_text(n.get("buyer-name"))
        number = str(n.get("publication-number"))
        found.append(
            record(
                "ted",
                number,
                TED_PAGE.format(number=number),
                f"TED award of {euros(amount)}: {title}" + (f" ({buyer})" if buyer else ""),
                str(n.get("publication-date") or ""),
                ("contract", "medium"),
                company_of_tax_id[ours[0]],
                ours,
                amount,
            )
        )
    return found


def ted(
    client: Client, company_of_tax_id: dict[str, str], since: date, limit: int = 250
) -> list[Item]:
    ids = sorted(company_of_tax_id)
    found: list[Item] = []
    for start in range(0, len(ids), TED_IDS_PER_QUERY):
        chunk = ids[start : start + TED_IDS_PER_QUERY]
        wanted = " ".join(chunk + [f"ES{t}" for t in chunk])
        body = {
            "query": f"winner-identifier IN ({wanted}) AND publication-date>={since:%Y%m%d}",
            "fields": TED_FIELDS,
            "limit": limit,
            "scope": "ALL",
            "paginationMode": "PAGE_NUMBER",
        }
        for page in range(1, 10_000):
            notices = listify(
                client.post(TED_SEARCH, json={**body, "page": page}).json().get("notices")
            )
            found += ted_items(notices, company_of_tax_id)
            if len(notices) < limit:
                break
    return found
