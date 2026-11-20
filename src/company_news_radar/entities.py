"""Company linker: which watched companies does a headline or standfirst mention?

Texts and keys are compared as sequences of normalised words, and a key only matches a run
of whole words, never part of a longer word. Keys come from two places. The watchlist's
aliases are taken as given. Other keys are built from the group name and the registered
names, and survive only if ``distinguishes`` accepts them and ``calibrate`` finds no sign
that the feeds use them as everyday words. When a text contains one of a company's
``exclude`` phrases, the linker reports nothing for that company in that text.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from company_news_radar import config
from company_news_radar.models import Mention
from company_news_radar.textutil import normalise, without_accents, words
from company_news_radar.watchlist import Company

# written for this watchlist of listed groups: organisation and sector words, Spanish places
GENERIC = frozenset(
    """
    GRUPO GROUP BANCO BANK BANCA CAIXA CAJA CORPORACION CORPORATION COMPANIA COMPANY
    SOCIEDAD HOLDING HOLDINGS INTERNACIONAL INTERNATIONAL GLOBAL GENERAL NACIONAL
    CONSOLIDATED ACTIVIDADES SERVICIOS SERVICES SISTEMAS SYSTEMS SOLUCIONES SOLUTIONS
    INDUSTRIA INDUSTRIAS INDUSTRIAL CONSTRUCCION CONSTRUCCIONES INFRAESTRUCTURAS OBRAS
    ENERGIA ENERGY ENERGIAS RENOVABLES ELECTRICA ELECTRICIDAD GAS AGUA AGUAS PETROLEOS
    TELECOM TELECOMUNICACIONES TELEFONICA REDES RED INMOBILIARIA INMOBILIARIAS
    PROPERTIES REAL ESTATE SEGUROS SEGURO INSURANCE FINANCIERA FINANCIAL CAPITAL
    INVERSIONES INVESTMENTS LABORATORIOS FARMACEUTICA FARMACEUTICOS PHARMA TECNOLOGIA
    TECNOLOGIAS TECHNOLOGIES DISENO TEXTIL MODA AIRLINES AIRPORTS AEROPUERTOS LOGISTICA
    TRANSPORTES ACERO STEEL SOLAR NUEVA NUEVO NUEVOS ESPANA ESPANOLA ESPANOL IBERICA
    IBERIA EUROPA EUROPEA EUROPE AMERICA LATAM SANTANDER BILBAO VIZCAYA BIZKAIA MADRID
    BARCELONA SEVILLA VALENCIA MALAGA ZARAGOZA ALICANTE CORDOBA GRANADA CADIZ MURCIA
    VALLADOLID OVIEDO GIJON CORUNA VIGO PAMPLONA TOLEDO BURGOS LEON SALAMANCA ANDALUCIA
    CATALUNA CATALUNYA GALICIA ASTURIAS CANARIAS BALEARES ARAGON NAVARRA CASTILLA
    EUSKADI CANTABRIA EXTREMADURA RIOJA
    """.split()
)
LEGAL_ENDINGS = [
    tuple(form.split())
    for form in "S A U|S L U|S M E|S C A|S A|S L|SAU|SLU|SA|SL|SOCIMI|SICAV|SE|PLC|N V|AG".split(
        "|"
    )
]  # longest first, so 'S A U' is cut before 'S A'


def strip_legal_form(name: str) -> str:
    """Normalised name without its legal-form suffixes ('X SOCIMI, S.A.' -> 'X')."""
    tokens = words(name)
    ending = next(
        (e for e in LEGAL_ENDINGS if len(tokens) > len(e) and tuple(tokens[-len(e) :]) == e), None
    )
    return strip_legal_form(" ".join(tokens[: -len(ending)])) if ending else " ".join(tokens)


def distinguishes(
    key: str, generic: frozenset[str] = GENERIC, min_letters: int = config.MIN_ONE_WORD_LETTERS
) -> bool:
    parts = key.split()
    informative = [p for p in parts if p not in generic]
    return bool(informative) and (len(parts) > 1 or len(parts[0]) >= min_letters)


def contains(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    n = len(phrase)
    return n > 0 and any(tuple(tokens[i : i + n]) == phrase for i in range(len(tokens) - n + 1))


@dataclass(frozen=True)
class Key:
    phrase: tuple[str, ...]
    company: str
    explicit: bool  # an alias from the watchlist, as opposed to a derived name

    @property
    def text(self) -> str:
        return " ".join(self.phrase)


@dataclass
class Dictionary:
    entries: list[Key] = field(default_factory=list)
    homonyms: dict[str, list[tuple[str, ...]]] = field(default_factory=dict)
    tax_ids: dict[str, str] = field(default_factory=dict)  # keyed by tax id

    def add(self, phrase: str, company: str, explicit: bool) -> None:
        if phrase.split():
            self.entries.append(Key(tuple(phrase.split()), company, explicit))

    def phrases(self, explicit: bool | None = None) -> set[str]:
        """Key texts; pass ``explicit`` to get only aliases (True) or only derived keys (False)."""
        return {k.text for k in self.entries if explicit in (None, k.explicit)}

    def drop(self, phrases: set[str]) -> int:
        """Deletes derived keys with these texts and returns how many went; aliases stay."""
        before = len(self.entries)
        self.entries = [k for k in self.entries if k.explicit or k.text not in phrases]
        return before - len(self.entries)

    def homonym_in(self, company: str, text: str | None) -> bool:
        tokens = words(text)
        return any(contains(tokens, phrase) for phrase in self.homonyms.get(company, []))

    def find(self, text: str | None) -> list[Mention]:
        """One mention per company found; ``how`` is 'alias' when an alias matched."""
        tokens = words(text)
        present = set(tokens)
        hits: dict[str, Mention] = {}
        for key in sorted(self.entries, key=lambda k: not k.explicit):
            if (
                key.company in hits
                or key.phrase[0] not in present
                or not contains(tokens, key.phrase)
            ):
                continue
            hits[key.company] = Mention(key.company, "alias" if key.explicit else "name", key.text)
        return [m for m in hits.values() if not self.homonym_in(m.company, text)]


def build(
    companies: Iterable[Company], min_letters: int = config.MIN_ONE_WORD_LETTERS
) -> Dictionary:
    d = Dictionary()
    for c in companies:
        for alias in dict.fromkeys(normalise(a) for a in c.aliases):
            d.add(alias, c.id, explicit=True)
        derived = {normalise(c.group)} | {strip_legal_form(n) for n in c.all_registered_names}
        for phrase in sorted(derived - d.phrases(explicit=True)):
            if distinguishes(phrase, min_letters=min_letters):
                d.add(phrase, c.id, explicit=False)
        d.homonyms[c.id] = [tuple(normalise(x).split()) for x in c.exclude if normalise(x)]
        if c.tax_id:
            d.tax_ids[c.tax_id] = c.id
    return d


LETTER_RUNS = re.compile(r"[^\W\d_]+")


def word_counts(d: Dictionary, texts: list[str]) -> tuple[Counter[str], Counter[str]]:
    """For each derived one-word key: texts with it in lower case, and texts it matches."""
    single = {p for p in d.phrases(explicit=False) if " " not in p}
    lower: Counter[str] = Counter()
    matched: Counter[str] = Counter()
    for text in texts if single else []:
        lowered = {without_accents(w).upper() for w in LETTER_RUNS.findall(text) if w.islower()}
        lower.update(single & lowered)
        matched.update(single.intersection(words(text)))
    return lower, matched


def calibrate(
    d: Dictionary,
    texts: list[str],
    min_lowercase: int = config.CALIBRATION_MIN_LOWERCASE,
    max_share: float = config.CALIBRATION_MAX_SHARE,
    floor: int = config.CALIBRATION_FLOOR,
) -> set[str]:
    """Drops derived one-word keys that ``texts`` show to be common words; returns them.

    A key goes when at least ``min_lowercase`` texts use it in lower case, or when it matches
    more texts than ``max_share`` of the corpus (never fewer than ``floor``).
    """
    single = {p for p in d.phrases(explicit=False) if " " not in p}
    lower, matched = word_counts(d, texts)
    limit = max(floor, max_share * len(texts))
    noisy = {p for p in single if lower[p] >= min_lowercase or matched[p] > limit}
    d.drop(noisy)
    return noisy
