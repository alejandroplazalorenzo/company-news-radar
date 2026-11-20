"""Settings from the environment or a local .env file; the values are never logged."""

from __future__ import annotations

import os
from pathlib import Path


def read_env(path: Path = Path(".env")) -> dict[str, str]:
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip("'\"")
    return values


def get(name: str, path: Path = Path(".env")) -> str | None:
    return os.environ.get(name) or read_env(path).get(name) or None
