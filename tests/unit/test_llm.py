import json
from pathlib import Path
from typing import Any

import pytest

from pets_transformer.config import LlmSettings, Settings
from pets_transformer.llm import DisabledLlm, JsonFileCache, LlmUnavailableError, LocalLlm, build_llm

SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}}


class FakeTransport:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def post_json(self, url: str, payload: dict[str, Any], timeout_s: float) -> dict[str, Any]:
        self.calls.append({"url": url, "payload": payload, "timeout_s": timeout_s})
        return {"response": self.response}


def test_off_by_default_so_everything_runs_on_rules() -> None:
    assert Settings.from_env({}).llm.enabled is False
    llm = build_llm(LlmSettings())
    assert isinstance(llm, DisabledLlm)
    assert not llm.available
    with pytest.raises(LlmUnavailableError, match="turned off"):
        llm.ask_json("anything", SCHEMA)


def test_enabled_from_env() -> None:
    assert Settings.from_env({"PETS_LLM_ENABLED": "true"}).llm.enabled
    assert build_llm(LlmSettings(enabled=True), FakeTransport("{}")).available


@pytest.mark.parametrize("url", ["https://api.example.com", "http://10.0.0.5:11434"])
def test_refuses_anything_but_this_machine(url: str) -> None:
    with pytest.raises(ValueError, match="this machine"):
        LocalLlm(LlmSettings(enabled=True, url=url))


def test_sends_repeatable_request_and_parses_json() -> None:
    t = FakeTransport(json.dumps({"ok": True}))
    llm = LocalLlm(LlmSettings(enabled=True, model="m"), transport=t)
    assert llm.ask_json("p", SCHEMA) == {"ok": True}
    sent = t.calls[0]
    assert sent["url"].endswith("/api/generate")
    assert sent["payload"]["options"]["temperature"] == 0
    assert sent["payload"]["format"] == SCHEMA
    assert sent["payload"]["stream"] is False


def test_cache_answers_repeat_questions(tmp_path: Path) -> None:
    t = FakeTransport(json.dumps({"ok": True}))
    llm = LocalLlm(LlmSettings(enabled=True), transport=t, cache=JsonFileCache(tmp_path))
    assert llm.ask_json("p", SCHEMA) == llm.ask_json("p", SCHEMA)
    assert len(t.calls) == 1


@pytest.mark.parametrize("bad", ["not json", None])
def test_bad_answer_becomes_unavailable_error(bad: Any) -> None:
    llm = LocalLlm(LlmSettings(enabled=True), transport=FakeTransport(bad))
    with pytest.raises(LlmUnavailableError):
        llm.ask_json("p", SCHEMA)


@pytest.mark.ollama
def test_real_local_model_answers() -> None:
    llm = build_llm(LlmSettings(enabled=True))
    assert llm.ask_json('Reply with {"ok": true}', SCHEMA) == {"ok": True}
