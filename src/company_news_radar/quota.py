"""Daily request budget for the LLM, kept in a JSON file.

``reserve`` adds one to today's count before a request leaves, under a lock that other
processes respect, and refuses once the cap is reached; a crash therefore never hides a
request. A quota day runs from 09:00 to 09:00 Madrid time, matching the Gemini free tier.
The cap defaults to ``config.DAILY_CAP`` and can never exceed ``config.FREE_TIER_PER_DAY``,
since the key is shared with another system. ``log`` appends one line per attempt (purpose,
item count, status, time, tokens) to ``llm_calls.jsonl``; prompts and the key stay out of it.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time as clock
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from company_news_radar import config


class QuotaExhausted(RuntimeError):
    """The cap for the current quota day has been reached."""


def quota_day(
    moment: datetime, zone: str = config.QUOTA_ZONE, starts_at: int = config.QUOTA_DAY_STARTS_AT
) -> date:
    local = moment.astimezone(ZoneInfo(zone))
    return local.date() if local.hour >= starts_at else local.date() - timedelta(days=1)


def next_reset(
    moment: datetime, zone: str = config.QUOTA_ZONE, starts_at: int = config.QUOTA_DAY_STARTS_AT
) -> datetime:
    following = quota_day(moment, zone, starts_at) + timedelta(days=1)
    return datetime.combine(following, time(starts_at), tzinfo=ZoneInfo(zone))


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    """Holds an OS-level exclusive lock on ``path`` for the duration of the block."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        if sys.platform == "win32":
            import msvcrt

            while True:
                try:
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    clock.sleep(0.05)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class Quota:
    def __init__(
        self,
        path: Path,
        cap: int = config.DAILY_CAP,
        log_path: Path | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if cap > config.FREE_TIER_PER_DAY:
            raise ValueError(f"daily cap {cap} is over the limit of {config.FREE_TIER_PER_DAY}")
        self.path = path
        self.cap = cap
        self.log_path = log_path or path.with_name("llm_calls.jsonl")
        self.now = now
        self._threads = threading.Lock()

    def counts(self) -> dict[str, int]:
        if not self.path.exists():
            return {}
        stored: dict[str, int] = json.loads(self.path.read_text(encoding="utf-8")).get("calls", {})
        return stored

    def _save(self, counts: dict[str, int]) -> None:
        scratch = self.path.with_name(self.path.name + ".tmp")
        scratch.write_bytes(json.dumps({"calls": counts}, indent=1, sort_keys=True).encode("utf-8"))
        os.replace(scratch, self.path)

    def used_today(self) -> int:
        return self.counts().get(quota_day(self.now()).isoformat(), 0)

    def used_total(self) -> int:
        return sum(self.counts().values())

    def remaining(self) -> int:
        return max(0, self.cap - self.used_today())

    def reserve(self) -> None:
        with self._threads, file_lock(self.path.with_name(self.path.name + ".lock")):
            counts = self.counts()
            today = quota_day(self.now()).isoformat()
            if counts.get(today, 0) >= self.cap:
                reset = next_reset(self.now()).isoformat(timespec="minutes")
                raise QuotaExhausted(f"{today}: all {self.cap} requests used; next day {reset}")
            counts[today] = counts.get(today, 0) + 1
            self._save(counts)

    def log(self, **record: Any) -> None:
        moment = self.now()
        line = {
            "at": moment.isoformat(timespec="seconds"),
            "quota_day": quota_day(moment).isoformat(),
            **record,
        }
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("ab") as out:
            out.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))

    def calls_log(self) -> list[dict[str, Any]]:
        if not self.log_path.exists():
            return []
        text = self.log_path.read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines() if line.strip()]
