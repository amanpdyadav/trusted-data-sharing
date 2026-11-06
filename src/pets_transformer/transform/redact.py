"""Free-text redaction: names, ID codes, contacts, account numbers and secrets become typed tags like [PHONE].

params:
  known_from  ["customers.full_name", ...]  person-name columns whose values are looked for in the text;
              the tables are read for this only and need not be released themselves
  labels      ["PERSON", "PHONE", ...]       narrow or widen what is tagged (default: identifying labels)
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from pets_transformer.contracts import SpanLabel, Technique
from pets_transformer.text.redactor import build_redactor
from pets_transformer.transform.base import TRANSFORMS, TransformContext


def known_from_tables(params: Mapping[str, Any]) -> set[str]:
    """Tables a redact_text action reads names from (the pipeline loads them even if they are not released)."""
    return {_split(ref)[0] for ref in params.get("known_from", [])}


def _split(ref: str) -> tuple[str, str]:
    table, sep, column = str(ref).partition(".")
    if not sep or not table or not column:
        raise ValueError(f"known_from entries look like 'table.column', got {ref!r}")
    return table, column


@dataclass(frozen=True)
class RedactText:
    technique: Technique = Technique.REDACT_TEXT

    def apply(self, values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
        names = [v for ref in params.get("known_from", []) for v in ctx.table_column(*_split(ref)).dropna()]
        labels = [SpanLabel(label) for label in params["labels"]] if "labels" in params else None
        redactor = build_redactor(names, labels)
        return values.astype(str).map(redactor.redact)


TRANSFORMS.register(Technique.REDACT_TEXT, RedactText())
