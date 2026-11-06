"""Interfaces for value-level transforms. One class per technique, looked up by `Technique` (open/closed)."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

import pandas as pd

from pets_transformer.contracts import Technique
from pets_transformer.keys import KeyProvider
from pets_transformer.registry import Registry


@dataclass(frozen=True)
class TransformContext:
    """What a transform may depend on. Injected, so tests can pass fakes (dependency inversion)."""

    keys: KeyProvider
    key_domain: str  # e.g. "HEALTH-S1/uni-research/2026-11": one key per receiver and release


class ColumnTransform(Protocol):
    @property
    def technique(self) -> Technique: ...

    def apply(self, values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
        """Return a new Series of the same length; never modify the input."""
        ...


TRANSFORMS: Registry[Technique, ColumnTransform] = Registry("transform")
