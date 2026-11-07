"""Differential privacy primitives: contribution bounding and discrete Laplace noise.

Discrete Laplace (two-sided geometric) noise on integer statistics gives exact epsilon-DP. It avoids the
floating-point weaknesses of textbook Laplace sampling (Mironov 2012), and published counts stay whole numbers.
"""

import math

import numpy as np
import pandas as pd


def bound_contributions(frame: pd.DataFrame, unit: str, max_rows: int, rng: np.random.Generator) -> pd.DataFrame:
    """Keep at most `max_rows` rows per person, chosen at random. Rows without a person id are their own person.

    This caps how much one person can change any statistic (the sensitivity), which the noise is scaled to.
    """
    if max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    raw = frame[unit].fillna("").astype(str).str.strip().to_numpy()
    rows = np.array([f"row:{i}" for i in range(len(frame))], dtype=object)
    ids = pd.Series(np.where(raw == "", rows, raw))
    order = rng.permutation(len(frame))
    keep = (ids.iloc[order].groupby(ids.iloc[order].to_numpy()).cumcount() < max_rows).to_numpy()
    kept: pd.DataFrame = frame.iloc[order[keep]].sort_index()
    return kept


def discrete_laplace(rng: np.random.Generator, sensitivity: int, epsilon: float, size: int) -> np.ndarray:
    """Integer noise with P(k) proportional to exp(-epsilon * |k| / sensitivity)."""
    if sensitivity < 1 or epsilon <= 0:
        raise ValueError("sensitivity must be >= 1 and epsilon > 0")
    p = -math.expm1(-epsilon / sensitivity)  # 1 - exp(-epsilon / sensitivity), accurate for small values
    noise: np.ndarray = rng.geometric(p, size) - rng.geometric(p, size)
    return noise
