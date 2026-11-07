"""The attacker's view: how many look-alikes does each person have on what an outsider could know?

An attacker who knows someone's quasi-identifiers (age, town, visit time ...) can single them out when nobody else
shares those values. This compares the raw table with the release on the same columns, using only the data itself,
so it works on company data without any answer key.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from pets_transformer.assess.kanon import group_sizes
from pets_transformer.contracts import Plan

BUCKETS: tuple[tuple[str, int, int], ...] = (
    ("alone", 1, 1), ("2-4", 2, 4), ("5-9", 5, 9), ("10-49", 10, 49), ("50+", 50, 10**12),
)  # fmt: skip


@dataclass(frozen=True)
class Lookalikes:
    rows: int
    unique_share: float  # people nobody else resembles: singled out by anyone who knows these facts
    guess_chance: float  # average chance that an attacker who picks one look-alike at random picks the right person
    buckets: dict[str, float]  # share of people per look-alike count

    def as_dict(self) -> dict[str, object]:
        return {
            "rows": self.rows, "unique_share": round(self.unique_share, 4),
            "guess_chance": round(self.guess_chance, 4), "buckets": {k: round(v, 4) for k, v in self.buckets.items()},
        }  # fmt: skip


def lookalikes(frame: pd.DataFrame, columns: Sequence[str]) -> Lookalikes:
    if len(frame) == 0:
        return Lookalikes(0, 0.0, 0.0, {b[0]: 0.0 for b in BUCKETS})
    sizes = group_sizes(frame, list(columns))
    buckets = {name: float(((sizes >= lo) & (sizes <= hi)).mean()) for name, lo, hi in BUCKETS}
    return Lookalikes(len(frame), float((sizes == 1).mean()), float((1 / sizes).mean()), buckets)


@dataclass(frozen=True)
class AttackerView:
    table: str
    known: list[str]  # source columns the attacker is assumed to know
    released_as: list[str]  # the same facts in the release (after renaming)
    before: Lookalikes
    after: Lookalikes

    def as_dict(self) -> dict[str, object]:
        return {
            "table": self.table, "known": self.known, "released_as": self.released_as,
            "before": self.before.as_dict(), "after": self.after.as_dict(),
        }  # fmt: skip


def source_columns(plan: Plan, table: str, released: Sequence[str]) -> list[str]:
    """Map released column names back to the source columns they came from (undoing rename_to)."""
    renamed = {str(a.params.get("rename_to", a.column)): a.column for a in plan.actions if a.table == table}
    return [renamed.get(c, c) for c in released]


def attacker_views(
    plan: Plan, raw: Mapping[str, pd.DataFrame], released: Mapping[str, pd.DataFrame]
) -> list[AttackerView]:
    """Before/after look-alikes for every table checked for k, on the plan's quasi-identifiers."""
    views = []
    for table, qis in plan.quasi_identifiers.items():
        if table not in raw or table not in released:
            continue
        known = source_columns(plan, table, qis)
        before, after = lookalikes(raw[table], known), lookalikes(released[table], list(qis))
        views.append(AttackerView(table, known, list(qis), before, after))
    return views
