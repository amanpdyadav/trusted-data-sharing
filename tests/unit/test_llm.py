import json
from collections.abc import Mapping
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

    def post_json(
        self, url: str, payload: dict[str, Any], timeout_s: float, headers: Mapping[str, str] | None = None
    ) -> dict[str, Any]:
        self.calls.append({"url": url, "payload": payload, "timeout_s": timeout_s, "headers": dict(headers or {})})
        if url.endswith("/chat/completions"):
            return {"choices": [{"message": {"content": self.response}}]}
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


def test_a_named_host_is_allowed_and_others_still_refused() -> None:
    LocalLlm(
        LlmSettings(enabled=True, url="http://aipc.example.ts.net:4000/v1", allowed_hosts=("aipc.example.ts.net",))
    )
    with pytest.raises(ValueError, match="PETS_LLM_ALLOWED_HOSTS"):
        LocalLlm(LlmSettings(enabled=True, url="http://other.example:4000/v1", allowed_hosts=("aipc.example.ts.net",)))


def test_openai_api_detected_from_v1_url_and_settings_from_env() -> None:
    llm = Settings.from_env({
        "PETS_LLM_URL": "http://h:4000/v1", "PETS_LLM_API_KEY": "k", "PETS_LLM_ALLOWED_HOSTS": "h, other",
    }).llm  # fmt: skip
    assert (llm.api, llm.api_key, llm.allowed_hosts) == ("openai", "k", ("h", "other"))
    assert Settings.from_env({}).llm.api == "ollama"
    assert Settings.from_env({"PETS_LLM_URL": "http://h/v1", "PETS_LLM_API": "ollama"}).llm.api == "ollama"


def test_openai_request_sends_schema_key_and_reads_the_message() -> None:
    t = FakeTransport('```json\n{"ok": true}\n```')
    settings = LlmSettings(enabled=True, url="http://localhost:4000/v1", model="m", api="openai", api_key="secret")
    assert LocalLlm(settings, transport=t).ask_json("p", SCHEMA) == {"ok": True}
    sent = t.calls[0]
    assert sent["url"] == "http://localhost:4000/v1/chat/completions"
    assert sent["headers"] == {"Authorization": "Bearer secret"}
    assert sent["payload"]["temperature"] == 0
    assert sent["payload"]["response_format"]["json_schema"]["schema"] == SCHEMA
    assert sent["payload"]["messages"][-1] == {"role": "user", "content": "p"}


def test_no_key_no_auth_header() -> None:
    t = FakeTransport(json.dumps({"ok": True}))
    LocalLlm(LlmSettings(enabled=True), transport=t).ask_json("p", SCHEMA)
    assert t.calls[0]["headers"] == {}


@pytest.mark.ollama
def test_real_local_model_answers() -> None:
    llm = build_llm(LlmSettings(enabled=True))
    assert llm.ask_json('Reply with {"ok": true}', SCHEMA) == {"ok": True}
