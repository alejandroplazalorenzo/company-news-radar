from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from company_news_radar import cli, experiments, prompts
from company_news_radar.ollama import Ollama


def test_ollama_sends_explicit_context_and_records_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "qwen3:8b",
                            "size": 10_000_000_000,
                            "size_vram": 7_000_000_000,
                            "digest": "abcdef1234567890",
                        }
                    ]
                },
            )
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "9.9.9"})
        sent.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "message": {"content": '{"items": []}'},
                "prompt_eval_count": 4096,
                "eval_count": 300,
            },
        )

    monkeypatch.setattr("company_news_radar.ollama.gpu_name", lambda: "Test GPU, 8192 MiB")
    llm = Ollama("qwen3:8b", 4096, transport=httpx.MockTransport(handler))
    assert llm("p", prompts.SCHEMA, "e2", 15) == {"items": []}
    body = sent[0]
    assert body["options"] == {"temperature": 0, "num_ctx": 4096} and body["think"] is False
    assert body["format"] == prompts.SCHEMA and llm.last["prompt_tokens"] == 4096
    notes = llm.notes()
    assert notes["processor"] == "30%/70% CPU/GPU" and notes["ollama"] == "9.9.9"
    assert notes["loaded size (GB)"] == 10.0 and notes["digest"] == "abcdef123456"
    assert notes["gpu"] == "Test GPU, 8192 MiB"


def test_the_prompt_shows_the_schema_and_items_as_json() -> None:
    item = prompts.payload(
        7, "Rovi abre una planta ficticia", "Diario", "2026-11-04T09:00:00+00:00", "Texto", ["Rovi"]
    )
    text = prompts.classifier("v1", [item])
    assert '"fact_key"' in text and "Two items about one event" in text
    assert prompts.compact(item) in text
    pair = prompts.judge("j1", [({"id": 1, "headline": "a"}, {"id": 2, "headline": "b"})])
    assert '"same"' in pair and '{"a":1,"b":2' in pair


def test_gpu_lock_refuses_when_taken(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(experiments.shutil, "which", lambda _name: None)
    lock = tmp_path / "_gpu.lock"
    experiments.gpu_turn(lock, "me")
    assert lock.read_text("utf-8").startswith("me ")
    with pytest.raises(SystemExit, match="GPU busy"):
        experiments.gpu_turn(lock, "other")


def test_cli_offline_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--data-dir", str(tmp_path), "--watchlist", "examples/watchlist.csv"]
    assert cli.main([*base, "quota"]) == 0
    assert "used 0 of 300" in capsys.readouterr().out
    assert cli.main([*base, "stats"]) == 0
    assert cli.main([*base, "probe-report", "--out", str(tmp_path / "probe.md")]) == 0
    assert "Stories for the LLM: **0**" in (tmp_path / "probe.md").read_text("utf-8")
    assert cli.main([*base, "quota-report", "--out", str(tmp_path / "q.md")]) == 0
    with pytest.raises(SystemExit):
        cli.main([*base, "--env", str(tmp_path / "missing.env"), "classify"])


def test_watchlist_is_complete() -> None:
    from company_news_radar.watchlist import load, load_newsrooms

    companies = load(Path("examples/watchlist.csv"))
    assert len(companies) == 32
    with_tax_id = [c for c in companies if c.tax_id]
    assert len(with_tax_id) == 31 and all(c.tax_id_source for c in companies)
    assert all(len(c.tax_id) == 9 for c in with_tax_id if c.tax_id)
    assert set(load_newsrooms(Path("examples/newsrooms.json"))) <= {c.id for c in companies}
