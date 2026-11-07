"""What the receiver can still do with the release: per-column changes and the accuracy of published statistics.

For the data controller's own review before release. It compares raw and protected data, so its output stays with
the controller (the raw side is never part of a release).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from pets_transformer.aggregate.cubes import noisy_table
from pets_transformer.contracts import Plan, Technique
from pets_transformer.keys import KeyScope
from pets_transformer.transform import TransformContext

TOP_VALUES = 8
CATEGORY_LIMIT = 50  # value distributions are shown for columns with at most this many values
MIN_CELL = 10  # relative error is only meaningful on cells that are not tiny


@dataclass(frozen=True)
class ColumnChange:
    column: str  # source column
    released_as: str | None  # None = withheld
    technique: str
    filled_before: int
    filled_after: int
    distinct_before: int
    distinct_after: int
    top_after: list[tuple[str, float]] = field(default_factory=list)  # value, share


def _top(values: pd.Series) -> list[tuple[str, float]]:
    filled = values[values.astype(str) != ""]
    shares = filled.astype(str).value_counts(normalize=True).head(TOP_VALUES)
    return [(str(k), round(float(v), 4)) for k, v in shares.items()]


def column_changes(plan: Plan, table: str, raw: pd.DataFrame, released: pd.DataFrame | None) -> list[ColumnChange]:
    out = []
    for a in (a for a in plan.actions if a.table == table):
        before = raw[a.column].fillna("").astype(str)
        name = str(a.params.get("rename_to", a.column))
        after = None if released is None or a.technique is Technique.DROP else released[name].fillna("").astype(str)
        out.append(
            ColumnChange(
                column=a.column, released_as=None if after is None else name, technique=a.technique.value,
                filled_before=int((before != "").sum()), filled_after=0 if after is None else int((after != "").sum()),
                distinct_before=int(before[before != ""].nunique()),
                distinct_after=0 if after is None else int(after[after != ""].nunique()),
                top_after=[] if after is None or after.nunique() > CATEGORY_LIMIT else _top(after),
            )
        )  # fmt: skip
    return out


@dataclass(frozen=True)
class TableAccuracy:
    name: str
    epsilon: float
    cells: int
    compared_cells: int  # cells whose true value is at least MIN_CELL (counts) or that have rows (means)
    mean_relative_error: float | None
    within_10pct: float | None  # share of compared cells within 10% of the true value


def dp_accuracy(
    plan: Plan,
    inputs: Mapping[str, pd.DataFrame],
    published: Mapping[str, pd.DataFrame],
    scope: KeyScope,
) -> list[TableAccuracy]:
    """Noisy published values against exact values from all rows (so bounding bias counts as error too)."""
    dp = plan.differential_privacy
    if dp is None:
        return []
    out = []
    for a in plan.aggregates:
        frame = inputs[a.table]
        ctx = TransformContext(keys=scope.keys, key_domain=scope.domain, source=frame, tables=inputs)
        exact = noisy_table(frame, a, dp, ctx, None)
        names = [d.output_name for d in a.dimensions]
        merged = exact.merge(published[a.name], on=names, suffixes=("_true", "_published"))
        truth, noisy = merged["value_true"].astype(float), merged["value_published"].astype(float)
        mask = truth >= MIN_CELL if a.measure.kind == "count" else merged.get("rows_true", truth) > 0
        rel = (noisy[mask] - truth[mask]).abs() / truth[mask].abs().clip(lower=1e-9)
        out.append(
            TableAccuracy(
                name=a.name, epsilon=a.epsilon, cells=len(merged), compared_cells=int(mask.sum()),
                mean_relative_error=float(np.minimum(rel, 1).mean()) if len(rel) else None,
                within_10pct=float((rel <= 0.1).mean()) if len(rel) else None,
            )
        )  # fmt: skip
    return out
