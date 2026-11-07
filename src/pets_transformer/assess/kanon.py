"""k-anonymity: every person should look the same as at least k-1 others on the quasi-identifiers."""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class KAnonymityResult:
    quasi_identifiers: tuple[str, ...]
    k_target: int
    rows: int
    groups: int
    k_min: int
    share_below_k: float  # share of rows in groups smaller than k_target

    @property
    def passes(self) -> bool:
        return self.rows == 0 or self.k_min >= self.k_target


def group_sizes(frame: pd.DataFrame, quasi_identifiers: Sequence[str]) -> pd.Series:
    """Size of each row's group on the quasi-identifiers, aligned with the frame's index."""
    missing = [c for c in quasi_identifiers if c not in frame.columns]
    if missing:
        raise KeyError(f"quasi-identifiers not in table: {missing}")
    if not quasi_identifiers:
        return pd.Series(len(frame), index=frame.index, dtype="int64")
    return frame.groupby(list(quasi_identifiers), dropna=False)[quasi_identifiers[0]].transform("size")


def k_anonymity(frame: pd.DataFrame, quasi_identifiers: Sequence[str], k_target: int = 5) -> KAnonymityResult:
    sizes = group_sizes(frame, quasi_identifiers)
    rows = len(frame)
    return KAnonymityResult(
        quasi_identifiers=tuple(quasi_identifiers),
        k_target=k_target,
        rows=rows,
        groups=int(frame.groupby(list(quasi_identifiers), dropna=False).ngroups)
        if quasi_identifiers
        else int(rows > 0),
        k_min=int(sizes.min()) if rows else 0,
        share_below_k=float((sizes < k_target).mean()) if rows else 0.0,
    )
