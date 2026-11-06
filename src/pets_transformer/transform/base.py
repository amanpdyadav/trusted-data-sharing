"""Interfaces for value-level transforms. One class per technique, looked up by `Technique` (open/closed)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
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
    source: pd.DataFrame = field(default_factory=pd.DataFrame)  # the whole input table, read-only (e.g. age at arrival)
    tables: Mapping[str, pd.DataFrame] = field(default_factory=dict)  # other input tables, read-only (known names)

    def source_column(self, name: str) -> pd.Series:
        if name not in self.source.columns:
            raise KeyError(f"transform needs column {name!r}, which the table does not have")
        return self.source[name]

    def table_column(self, table: str, column: str) -> pd.Series:
        frame = self.tables.get(table)
        if frame is None or column not in frame.columns:
            raise KeyError(f"transform needs {table}.{column}, which the input does not have")
        return frame[column]


class ColumnTransform(Protocol):
    @property
    def technique(self) -> Technique: ...

    def apply(self, values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
        """Return a new Series of the same length; never modify the input."""
        ...


TRANSFORMS: Registry[Technique, ColumnTransform] = Registry("transform")
