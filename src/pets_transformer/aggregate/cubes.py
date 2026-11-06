"""Noisy statistics tables: one row per cell of the dimensions' domain, never one row per person.

Every cell of the domain is published, including empty ones, so a missing row cannot reveal a zero. Each person
lands in at most one cell per table, so after contribution bounding a table's sensitivity is the bound itself.
"""

import math

import numpy as np
import pandas as pd

from pets_transformer.aggregate.dp import discrete_laplace
from pets_transformer.contracts import Aggregate, DifferentialPrivacy, Dimension, Technique
from pets_transformer.transform import TRANSFORMS, TransformContext


def dimension_values(frame: pd.DataFrame, d: Dimension, ctx: TransformContext) -> pd.Series:
    """The dimension's value for every row, coarsened with the same strategies as released columns."""
    if not d.params:
        return frame[d.column].fillna("").astype(str)
    return TRANSFORMS.get(Technique.GENERALISE).apply(frame[d.column], d.params, ctx).astype(str)


def _grid(dims: pd.DataFrame, spec: Aggregate) -> pd.MultiIndex:
    domains = [
        list(d.domain) if d.domain is not None else sorted(v for v in dims[d.output_name].unique() if v)
        for d in spec.dimensions
    ]
    return pd.MultiIndex.from_product(domains, names=[d.output_name for d in spec.dimensions])


def noisy_table(
    frame: pd.DataFrame, spec: Aggregate, dp: DifferentialPrivacy, ctx: TransformContext, rng: np.random.Generator
) -> pd.DataFrame:
    """The published table for `spec` from contribution-bounded rows."""
    for column, values in spec.exclude.items():
        frame = frame[~frame[column].astype(str).isin(values)]
    names = [d.output_name for d in spec.dimensions]
    dims = pd.DataFrame({d.output_name: dimension_values(frame, d, ctx) for d in spec.dimensions}, index=frame.index)
    grid = _grid(dims, spec)
    inside = pd.Series(pd.MultiIndex.from_frame(dims).isin(grid), index=frame.index)
    c, m = dp.max_rows_per_unit, spec.measure

    def noisy(exact: pd.Series, sensitivity: int, epsilon: float) -> np.ndarray:
        values: np.ndarray = exact.to_numpy() + discrete_laplace(rng, sensitivity, epsilon, len(exact))
        return values

    if m.kind == "count":
        exact = dims[inside].groupby(names).size().reindex(grid, fill_value=0)
        out = pd.DataFrame({"value": np.maximum(noisy(exact, c, spec.epsilon), 0)}, index=grid)
        return out.reset_index()

    assert m.column is not None  # checked by the contract
    raw = frame[m.column]
    if m.kind == "share":
        x, lo, hi = raw.astype(str).isin(m.values).astype(int).where(raw.notna() & (raw != "")), 0.0, 1.0
    else:
        assert m.upper is not None
        lo, hi = m.lower, m.upper
        x = pd.to_numeric(raw, errors="coerce").clip(lo, hi).round()
    rows = inside & x.notna()
    grouped = x[rows].groupby([dims.loc[rows, n] for n in names])
    total = grouped.sum().reindex(grid, fill_value=0)
    count = grouped.size().reindex(grid, fill_value=0)
    half = spec.epsilon / 2  # the budget is split between the sum and the count
    noisy_total = noisy(total, c * math.ceil(max(abs(lo), abs(hi))), half)
    noisy_count = np.maximum(noisy(count, c, half), 0)
    mean = np.clip(noisy_total / np.maximum(noisy_count, 1), lo, hi)
    return pd.DataFrame({"value": mean.round(4), "rows": noisy_count}, index=grid).reset_index()
