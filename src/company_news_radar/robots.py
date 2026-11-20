"""A robots.txt parser following RFC 9309.

Groups naming this client's product token win over ``*`` groups, and several matching
groups are merged. Patterns support ``*`` and a trailing ``$``. When rules conflict, the
longest matching pattern decides, and allow wins a tie. Both rule and request paths are
normalised the same way before comparing. How the file was obtained matters too: a 2xx is
parsed, a 4xx (but 429) means no restrictions, and a 429, 5xx or network error means the
host is not asked at all. The robots.txt path itself is always allowed.
"""

from __future__ import annotations

import re
import string
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import urlsplit

MAX_BYTES = 512_000  # the RFC asks parsers to handle at least 500 KiB
_UNRESERVED = frozenset(string.ascii_letters + string.digits + "-._~")


def _canon(path: str) -> str:
    """Escapes non-ASCII and reserved bytes, unescapes unreserved ones (RFC 9309, 2.2.2)."""
    out: list[str] = []
    raw = path.encode("utf-8")
    i = 0
    while i < len(raw):
        byte, pair = raw[i], raw[i + 1 : i + 3]
        if byte == 0x25 and _is_hex(pair):
            char = chr(int(pair, 16))
            out.append(char if char in _UNRESERVED else "%" + pair.decode("ascii").upper())
            i += 3
        else:
            out.append(chr(byte) if byte < 0x80 else f"%{byte:02X}")
            i += 1
    return "".join(out)


def _is_hex(pair: bytes) -> bool:
    return len(pair) == 2 and all(chr(b) in string.hexdigits for b in pair)


@lru_cache(maxsize=4096)
def _compiled(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    joined = ".*".join(re.escape(chunk) for chunk in body.split("*"))
    return re.compile(joined + (r"\Z" if anchored else ""), re.DOTALL)


@dataclass(frozen=True)
class Rule:
    allow: bool
    pattern: str  # already normalised; '*' and a trailing '$' allowed

    @property
    def length(self) -> int:
        return len(self.pattern)

    def matches(self, path: str) -> bool:
        return _compiled(self.pattern).match(path) is not None


@dataclass
class Robots:
    verdict: str  # how the rules were obtained, e.g. 'rules' or 'no_file'
    rules: list[Rule] = field(default_factory=list)
    blocked: bool = False  # set when no request at all is allowed

    def allows(self, url: str) -> bool:
        parts = urlsplit(url)
        target = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if parts.path == "/robots.txt":
            return True
        if self.blocked:
            return False
        path = _canon(target)
        best: Rule | None = None
        for rule in self.rules:
            if not rule.matches(path):
                continue
            if (
                best is None
                or rule.length > best.length
                or (rule.length == best.length and rule.allow)
            ):
                best = rule
        return best is None or best.allow


@dataclass
class _Group:
    agents: list[str] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)


def _groups(text: str) -> list[_Group]:
    groups: list[_Group] = []
    current: _Group | None = None
    last_was_agent = False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        key, sep, value = line.partition(":")
        if not sep:
            continue
        key, value = key.strip().lower(), value.strip()
        if key == "user-agent":
            if current is None or not last_was_agent:
                current = _Group()
                groups.append(current)
            current.agents.append(value.lower())
            last_was_agent = True
            continue
        last_was_agent = False
        if key in ("allow", "disallow") and current is not None and value:
            current.rules.append(Rule(allow=key == "allow", pattern=_canon(value)))
    return groups


def parse(text: str, token: str) -> list[Rule]:
    groups = _groups(text[:MAX_BYTES])
    mine = [g for g in groups if token.lower() in g.agents]
    chosen = mine or [g for g in groups if "*" in g.agents]
    return [rule for g in chosen for rule in g.rules]


def from_response(status: int, content_type: str, body: str, token: str) -> Robots:
    if 200 <= status < 300:
        if body.lstrip()[:1] == "<":  # markup instead of a robots file
            return Robots("not_robots")
        return Robots("rules", parse(body, token))
    if 400 <= status < 500 and status != 429:
        return Robots("no_file")
    return Robots("unreachable", blocked=True)


def unreachable() -> Robots:
    return Robots("unreachable", blocked=True)
