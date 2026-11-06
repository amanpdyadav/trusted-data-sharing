"""Interfaces for the Detect step (owner: Hari). Code depends on these, not on concrete detectors."""

from collections.abc import Iterable
from typing import Protocol

import pandas as pd

from pets_transformer.contracts import ColumnDetection, Subtype


class Validator(Protocol):
    """Checks one value's format, e.g. a Finnish ID-code checksum. Shared with the text step (DRY)."""

    @property
    def name(self) -> str: ...

    @property
    def subtype(self) -> Subtype: ...

    def is_valid(self, value: str) -> bool: ...


class ColumnDetector(Protocol):
    """Labels every column of one table. Must work from names and values only (production rule 1)."""

    def detect(self, table: str, frame: pd.DataFrame) -> list[ColumnDetection]: ...


def match_rate(values: Iterable[str], validator: Validator) -> float:
    """Share of non-empty values that pass the validator; 0.0 when there are none."""
    total = hits = 0
    for v in values:
        if not v:
            continue
        total += 1
        hits += validator.is_valid(v)
    return hits / total if total else 0.0
