"""Keyed pseudonyms (HMAC-SHA256). Same value + same key domain -> same code, so joins and revisits survive.

Unlike a plain hash, nobody can reverse it by hashing a list of guesses without the secret key.
"""

import hashlib
import hmac
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from pets_transformer.contracts import Technique
from pets_transformer.transform.base import TRANSFORMS, TransformContext

DEFAULT_LENGTH = 16
MIN_LENGTH = 12  # shorter codes start to collide on tables of this size


@dataclass(frozen=True)
class Pseudonymise:
    technique: Technique = Technique.PSEUDONYMISE

    def apply(self, values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
        length = int(params.get("length", DEFAULT_LENGTH))
        if not MIN_LENGTH <= length <= 64:
            raise ValueError(f"pseudonym length must be {MIN_LENGTH}-64, got {length}")
        normalise = bool(params.get("case_insensitive", False))
        key = ctx.keys.key_for(ctx.key_domain)

        def code(value: str) -> str:
            if not value:
                return ""  # keep 'missing' visible; it is not an identifier
            v = value.strip().lower() if normalise else value.strip()
            return hmac.new(key, v.encode("utf-8"), hashlib.sha256).hexdigest()[:length]

        return values.astype(str).map(code)


TRANSFORMS.register(Technique.PSEUDONYMISE, Pseudonymise())
