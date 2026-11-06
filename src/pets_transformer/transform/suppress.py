"""Local suppression to reach k-anonymity on a table's quasi-identifiers.

The plan lists the quasi-identifiers most important first. Only rows in groups smaller than k are touched:
their least important quasi-identifier is blanked first, then the next, and so on. Rows that are still in a
small group after every quasi-identifier is blanked are removed. Everything changed is counted for the manifest.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

import pandas as pd

from pets_transformer.assess.kanon import KAnonymityResult, group_sizes, k_anonymity

SUPPRESSED = ""  # a blank, so every suppressed value of a column falls into one shared group


@dataclass(frozen=True)
class SuppressionResult:
    frame: pd.DataFrame
    cells_blanked: dict[str, int] = field(default_factory=dict)
    rows_removed: int = 0
    check: KAnonymityResult | None = None


def suppress_to_k(frame: pd.DataFrame, quasi_identifiers: Sequence[str], k: int) -> SuppressionResult:
    if k < 2:
        raise ValueError("k must be at least 2")
    qis = list(quasi_identifiers)
    if not qis:
        return SuppressionResult(frame.copy(), check=k_anonymity(frame, qis, k))
    out = frame.copy()
    blanked: dict[str, int] = {}
    for col in reversed(qis):
        small = group_sizes(out, qis) < k
        if not small.any():
            break
        changed = small & (out[col] != SUPPRESSED)
        blanked[col] = int(changed.sum())
        out.loc[small, col] = SUPPRESSED
    still_small = group_sizes(out, qis) < k
    kept = out.loc[~still_small]
    return SuppressionResult(kept, blanked, int(still_small.sum()), k_anonymity(kept, qis, k))
