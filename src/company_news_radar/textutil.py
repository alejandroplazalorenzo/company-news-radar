"""Small helpers for text normalisation, dates, URLs and XML."""

from __future__ import annotations

import html
import unicodedata
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from lxml import etree
from lxml import html as lxml_html

# query parameters dropped from URLs because they only track the click
TRACKING_PREFIXES = ("utm_", "mc_", "pk_", "_hs")
TRACKING_PARAMS = frozenset("fbclid gclid dclid msclkid igshid yclid ocid cmpid ref_src".split())


def without_accents(text: str) -> str:
    """Decomposes accents and drops every byte that is not ASCII."""
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")


def words(text: str | None) -> list[str]:
    """Splits on anything but letters and digits; the words come back in ASCII upper case."""
    folded = without_accents(text or "").upper()
    return "".join(ch if ch.isalnum() else " " for ch in folded).split()


def normalise(text: str | None) -> str:
    """Canonical form for comparing names, e.g. 'Ferrovial, S.E.' gives 'FERROVIAL S E'."""
    return " ".join(words(text))


def slug(text: str | None, limit: int = 80) -> str | None:
    """Lower-case words joined by hyphens, cut at a word boundary within ``limit``."""
    joined = "-".join(words(text)).lower()
    if len(joined) > limit:
        joined = joined[:limit].rsplit("-", 1)[0]
    return joined or None


def _moment(raw: str) -> datetime | None:
    if len(raw) > 10 and raw[10] in "+-" and raw[4] == "-":  # a date with an offset, no time
        raw = raw[:10]
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        pass
    for layout in ("%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(raw, layout)
        except ValueError:
            continue
    return None


def iso_utc(text: str | None) -> str | None:
    """ISO 8601 in UTC from ISO, RFC 822, dd/mm/yyyy or yyyymmdd input; None if unreadable."""
    if not text or not text.strip():
        return None
    moment = _moment(text.strip())
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).isoformat(timespec="seconds")


def day_of(stamp: str | None) -> date | None:
    return date.fromisoformat(stamp[:10]) if stamp else None


def to_text(fragment: str | None, limit: int = 600) -> str | None:
    """Text content of an HTML snippet on one line, shortened to about ``limit`` characters."""
    if not fragment or not fragment.strip():
        return None
    try:
        text = lxml_html.fragment_fromstring(fragment, create_parent="div").text_content()
    except (etree.ParserError, ValueError):
        text = fragment
    flat = " ".join(html.unescape(text).split())
    if len(flat) > limit:
        flat = flat[:limit].rsplit(" ", 1)[0] + " …"
    return flat or None


def _keeps(param: tuple[str, str]) -> bool:
    name = param[0].lower()
    return name not in TRACKING_PARAMS and not name.startswith(TRACKING_PREFIXES)


def canonical_url(url: str) -> str:
    scheme, netloc, path, query, _fragment = urlsplit(url.strip())
    query = urlencode(list(filter(_keeps, parse_qsl(query, keep_blank_values=True))))
    return urlunsplit((scheme.lower(), netloc.lower(), path or "/", query, ""))


def host(url: str | None) -> str:
    """Host name in lower case without a leading www; accepts a bare host too."""
    if not url:
        return ""
    name = urlsplit(url if "//" in url else "//" + url).hostname or ""
    return name.lower().removeprefix("www.")


# recover from broken markup, never expand entities or fetch anything; one parser per call
XML_OPTIONS = {"recover": True, "resolve_entities": False, "no_network": True}


def parse_xml(content: bytes) -> etree._Element | None:
    data = content.lstrip() or b"<empty/>"
    try:
        root: etree._Element | None = etree.fromstring(data, etree.XMLParser(**XML_OPTIONS))
    except etree.XMLSyntaxError:
        root = None
    return root


def tag(el: etree._Element) -> str:
    return str(el.xpath("local-name()"))


def kids(el: etree._Element, name: str) -> list[etree._Element]:
    found: list[etree._Element] = el.xpath("./*[local-name() = $n]", n=name)
    return found


def text_of(el: etree._Element, *names: str) -> str | None:
    """Stripped text of the first named child that is not empty, trying ``names`` in order."""
    texts = (
        str(el.xpath("string(./*[local-name() = $n][normalize-space()][1])", n=n)).strip()
        for n in names
    )
    return next((x for x in texts if x), None)
