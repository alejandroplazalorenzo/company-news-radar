"""Client for a local model served by Ollama; E2 uses it next to Gemini.

The context size is always passed as ``num_ctx``: when a prompt does not fit, Ollama cuts
tokens without saying so, and an 8 GB card holds qwen3:8b with a 4,096-token context. Each
call keeps the token counts Ollama reports, so a report can show how close a batch came.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

import httpx


def gpu_name() -> str | None:
    """Name and memory of the first GPU, as nvidia-smi prints them; None without it."""
    tool = shutil.which("nvidia-smi")
    if not tool:
        return None
    out = subprocess.run(
        [tool, "--query-gpu=name,memory.total", "--format=csv,noheader"],
        capture_output=True,
        text=True,
        check=False,
    )
    return out.stdout.strip().splitlines()[0] if out.stdout.strip() else None


class Ollama:
    def __init__(
        self,
        model: str,
        num_ctx: int,
        host: str = "http://127.0.0.1:11434",
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 900.0,
    ) -> None:
        self.model = model
        self.num_ctx = num_ctx
        self.http = httpx.Client(base_url=host, timeout=timeout_s, transport=transport)
        self.last: dict[str, Any] = {}
        self._loaded: dict[str, Any] = {}

    def __call__(
        self, prompt: str, schema: dict[str, Any], purpose: str, n_items: int
    ) -> dict[str, Any]:
        started = time.monotonic()
        r = self.http.post(
            "/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "format": schema,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_ctx": self.num_ctx},
            },
        )
        r.raise_for_status()
        data = r.json()
        self.last = {
            "purpose": purpose,
            "items": n_items,
            "seconds": round(time.monotonic() - started, 2),
            "prompt_tokens": data.get("prompt_eval_count"),
            "output_tokens": data.get("eval_count"),
            "num_ctx": self.num_ctx,
        }
        self._loaded = self._ps() or self._loaded
        content = data.get("message", {}).get("content", "")
        parsed: dict[str, Any] = json.loads(content)
        return parsed

    def _ps(self) -> dict[str, Any]:
        try:
            data = self.http.get("/api/ps").json()
        except (httpx.HTTPError, ValueError):
            return {}
        return next(
            (m for m in data.get("models", []) if m.get("name", "").startswith(self.model)), {}
        )

    def processor(self) -> str:
        """CPU/GPU split of the loaded model, computed from the sizes in /api/ps."""
        m = self._loaded or self._ps()
        size, vram = m.get("size") or 0, m.get("size_vram") or 0
        if not size:
            return "not loaded"
        if vram >= size:
            return "100% GPU"
        gpu = round(100 * vram / size)
        return f"{100 - gpu}%/{gpu}% CPU/GPU"

    def notes(self) -> dict[str, Any]:
        """Hardware, versions and settings of this run, for the report."""
        try:
            version = self.http.get("/api/version").json().get("version")
        except (httpx.HTTPError, ValueError):
            version = None
        m = self._loaded or self._ps()
        return {
            "gpu": gpu_name(),
            "ollama": version,
            "model": self.model,
            "digest": str(m.get("digest") or "")[:12] or None,
            "num_ctx": self.num_ctx,
            "think": False,
            "processor": self.processor(),
            "loaded size (GB)": round((m.get("size") or 0) / 1e9, 1) or None,
        }
