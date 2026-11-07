"""One shared helper for the local AI (Ollama). Everyone gets a client from `build_llm()` and calls `ask_json`.

The local AI is optional. When it is off (the default) `build_llm` returns `DisabledLlm`, whose `ask_json`
raises `LlmUnavailableError` straight away. Callers handle that one error by falling back to rules, so the
same code path covers "turned off", "not installed", "timed out" and "bad answer".

Rules built in: localhost only unless a host is named in PETS_LLM_ALLOWED_HOSTS (production rule 2),
temperature 0 and a JSON schema for repeatable answers, answers cached on disk keyed by model + prompt + schema.
The model never decides privacy settings.
Two wire formats: Ollama's /api/generate, and the OpenAI-style /chat/completions (LiteLLM, vLLM, llama.cpp).
"""

import hashlib
import json
import re
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

from pets_transformer.config import LlmSettings

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
JsonDict = dict[str, Any]


class LlmUnavailableError(RuntimeError):
    """The local model could not answer (not running, timeout, bad JSON). Callers should fall back to rules."""


class Transport(Protocol):
    def post_json(
        self, url: str, payload: JsonDict, timeout_s: float, headers: Mapping[str, str] | None = None
    ) -> JsonDict: ...


class UrllibTransport:
    """Plain-stdlib HTTP; no extra dependency for a single POST."""

    def post_json(
        self, url: str, payload: JsonDict, timeout_s: float, headers: Mapping[str, str] | None = None
    ) -> JsonDict:
        all_headers = {"Content-Type": "application/json", **(headers or {})}
        req = urllib.request.Request(url, json.dumps(payload).encode("utf-8"), all_headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                data: JsonDict = json.load(resp)
                return data
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LlmUnavailableError(str(exc)) from exc


class JsonFileCache:
    def __init__(self, folder: Path) -> None:
        self._folder = folder

    def get(self, key: str) -> JsonDict | None:
        p = self._folder / f"{key}.json"
        if not p.exists():
            return None
        data: JsonDict = json.loads(p.read_text(encoding="utf-8"))
        return data

    def put(self, key: str, value: JsonDict) -> None:
        self._folder.mkdir(parents=True, exist_ok=True)
        (self._folder / f"{key}.json").write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def ensure_local(url: str, allowed_hosts: tuple[str, ...] = ()) -> None:
    """Only this machine, plus hosts the operator named on purpose (PETS_LLM_ALLOWED_HOSTS)."""
    host = urlparse(url).hostname or ""
    if host not in LOCAL_HOSTS and host not in allowed_hosts:
        raise ValueError(
            f"local AI must run on this machine; refusing host {host!r} (name it in PETS_LLM_ALLOWED_HOSTS to allow it)"
        )


class LlmClient(Protocol):
    """What callers depend on. `available` lets the UI and the manifest say whether AI was used."""

    @property
    def available(self) -> bool: ...

    @property
    def model(self) -> str | None: ...

    def ask_json(self, prompt: str, schema: JsonDict) -> JsonDict: ...


class DisabledLlm:
    """Null object used when the local AI is off: every call fails fast so callers use their rule path."""

    @property
    def available(self) -> bool:
        return False

    @property
    def model(self) -> str | None:
        return None

    def ask_json(self, prompt: str, schema: JsonDict) -> JsonDict:
        raise LlmUnavailableError("local AI is turned off (set PETS_LLM_ENABLED=true to use it)")


def build_llm(settings: LlmSettings, transport: Transport | None = None) -> LlmClient:
    """The only place that decides between the real client and the disabled one."""
    return LocalLlm(settings, transport) if settings.enabled else DisabledLlm()


class LocalLlm:
    def __init__(
        self,
        settings: LlmSettings,
        transport: Transport | None = None,
        cache: JsonFileCache | None = None,
    ) -> None:
        ensure_local(settings.url, settings.allowed_hosts)
        if settings.api not in ("ollama", "openai"):
            raise ValueError(f"PETS_LLM_API must be 'ollama' or 'openai', not {settings.api!r}")
        self._settings = settings
        self._transport = transport or UrllibTransport()
        self._cache = cache or (JsonFileCache(settings.cache_dir) if settings.cache_dir else None)

    @property
    def available(self) -> bool:
        return True

    @property
    def model(self) -> str | None:
        return self._settings.model

    def ask_json(self, prompt: str, schema: JsonDict) -> JsonDict:
        """Ask for an answer that must match `schema`. Returns the parsed JSON object."""
        key = self._cache_key(prompt, schema)
        if self._cache and (hit := self._cache.get(key)) is not None:
            return hit
        answer = (
            self._ask_openai(prompt, schema) if self._settings.api == "openai" else self._ask_ollama(prompt, schema)
        )
        if self._cache:
            self._cache.put(key, answer)
        return answer

    def _post(self, path: str, payload: JsonDict) -> JsonDict:
        key = self._settings.api_key
        headers = {"Authorization": f"Bearer {key}"} if key else {}
        url = self._settings.url.rstrip("/") + path
        return self._transport.post_json(url, payload, self._settings.timeout_s, headers=headers)

    def _ask_ollama(self, prompt: str, schema: JsonDict) -> JsonDict:
        raw = self._post("/api/generate", {
            "model": self._settings.model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "think": False,  # reasoning models answer straight away; the schema already shapes the answer
            "options": {"temperature": 0},
        })  # fmt: skip
        try:
            return _parse_object(raw["response"])
        except (KeyError, TypeError) as exc:
            raise LlmUnavailableError(f"model returned no valid JSON: {exc}") from exc

    def _ask_openai(self, prompt: str, schema: JsonDict) -> JsonDict:
        raw = self._post("/chat/completions", {
            "model": self._settings.model,
            "messages": [
                {"role": "system", "content": "Answer with one JSON object only, matching this JSON schema: "
                                              + json.dumps(schema)},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "stream": False,
            "response_format": {"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
        })  # fmt: skip
        try:
            return _parse_object(raw["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmUnavailableError(f"model returned no valid JSON: {exc}") from exc

    def _cache_key(self, prompt: str, schema: JsonDict) -> str:
        blob = json.dumps({"m": self._settings.model, "p": prompt, "s": schema}, sort_keys=True)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def _parse_object(text: Any) -> JsonDict:
    """The model's text as a JSON object; tolerates a ```json fence some chat models add."""
    if not isinstance(text, str):
        raise LlmUnavailableError("model returned no text")
    try:
        answer = json.loads(_FENCE.sub("", text.strip()))
    except json.JSONDecodeError as exc:
        raise LlmUnavailableError(f"model returned no valid JSON: {exc}") from exc
    if not isinstance(answer, dict):
        raise LlmUnavailableError("model returned JSON that is not an object")
    return answer
