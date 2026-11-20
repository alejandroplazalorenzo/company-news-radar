"""Replaces likely personal names in generated text with ``[person]``.

The pattern is a known first name followed by one to three capitalised words (particles
such as "de la" allowed in between). It will miss names it does not know, which is why the
shareable digest (``--no-details``) prints no generated text at all.
"""

from __future__ import annotations

import re

from company_news_radar.textutil import without_accents

# common Spanish, Catalan, Basque and English first names, accents removed
FIRST_NAMES = frozenset(
    """
    adrian agustin ainhoa alba albert alberto alejandro alicia alvaro amparo ana andrea
    andres andrew angel angela anne antonia antonio arantxa beatriz begona belen blanca
    borja carlos carlota carmen catherine claudia concepcion consuelo cristina cristobal
    daniel david diego dolores eduardo elena emilio emma enrique esther eva felix
    fernando francisca francisco gabriel george gloria gonzalo gorka guillermo helen
    hugo ignacio inaki ines inigo inmaculada irene isabel ismael ivan jaime james javier
    jennifer jesus joan joaquin john jordi jorge jose josep juan julia julio karen laura
    linda lisa lourdes lucia luis manuel manuela marc marcos margarita maria marina
    mario mark marta martin mary mercedes michael miguel miren monica montserrat nancy
    natalia nerea nicolas noelia nuria olga oscar pablo patricia paul paula pedro peter
    pilar rafael ramon raquel raul rebeca richard robert roberto rocio rosa ruben
    salvador santiago sara sarah sergio silvia sofia sonia steven susana teresa thomas
    tomas veronica vicente victor william xavier yolanda
    """.split()
)
_TOKEN = re.compile(r"[A-ZÁÉÍÓÚÑ][\wáéíóúñü'-]+")


def scrub(text: str | None) -> str:
    if not text:
        return ""
    out: list[str] = []
    pos = 0
    for m in _TOKEN.finditer(text):
        if m.start() < pos:
            continue
        if without_accents(m.group()).lower() not in FIRST_NAMES:
            continue
        rest = text[m.end() :]
        follow = re.match(
            r"(\s+(?:de\s+(?:la\s+|los\s+)?|del\s+|y\s+)?[A-ZÁÉÍÓÚÑ][\wáéíóúñü'-]+){1,3}", rest
        )
        if not follow:
            continue
        out.append(text[pos : m.start()])
        out.append("[person]")
        pos = m.end() + follow.end()
    out.append(text[pos:])
    return "".join(out)
