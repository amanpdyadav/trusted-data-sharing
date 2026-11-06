"""Secret keys for pseudonyms (production rule 3: keys never live in code).

One master secret comes from the environment. Each receiver/release gets its own derived key, so two releases
cannot be joined on their pseudonyms (no mosaic effect between receivers).
"""

import hashlib
import hmac
import os
from collections.abc import Mapping
from typing import Protocol

MIN_MASTER_KEY_CHARS = 32
ENV_VAR = "PETS_MASTER_KEY"


class MissingKeyError(RuntimeError):
    """Raised when no usable master key is configured."""


class KeyProvider(Protocol):
    def key_for(self, domain: str) -> bytes:
        """Return the secret key for one key domain, e.g. 'HEALTH-S1/uni-turku/2026-11'."""
        ...


class DerivedKeyProvider:
    """Derives a separate key per domain from one master secret with HMAC-SHA256."""

    def __init__(self, master: bytes) -> None:
        if len(master) < MIN_MASTER_KEY_CHARS:
            raise MissingKeyError(f"master key must be at least {MIN_MASTER_KEY_CHARS} characters")
        self._master = master

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "DerivedKeyProvider":
        e = os.environ if env is None else env
        value = e.get(ENV_VAR, "")
        if not value:
            raise MissingKeyError(
                f"{ENV_VAR} is not set: add it to .env (see .env.example) or `export` it in your shell"
            )
        return cls(value.encode("utf-8"))

    def key_for(self, domain: str) -> bytes:
        if not domain:
            raise ValueError("key domain must not be empty")
        return hmac.new(self._master, b"pets-transformer/" + domain.encode("utf-8"), hashlib.sha256).digest()
