"""Planner for published statistics: scenario statistics + detections -> aggregates with a privacy claim.

Each variable is coarsened according to what the detector found (timestamps to weeks, birth dates to age bands at
the event, codes through a code list), the epsilon budget is split by weight, and the protected person is the
table's detected person identifier. Without one, each row counts as a person and the plan asks for review.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pets_transformer.contracts import (
    Aggregate,
    ColumnDetection,
    DetectionReport,
    DifferentialPrivacy,
    Dimension,
    PrivacyRole,
    Subtype,
)
from pets_transformer.plan.common import PERSON_KEYS, REVIEW
from pets_transformer.plan.scenario import Need, Scenario, Statistic

R, S = PrivacyRole, Subtype
DEFAULT_EPSILON = 1.0
DEFAULT_ROWS_PER_PERSON = 3
AGE_WIDTH, AGE_TOP = 10, 80
TIME_NAMES = {"time_of_day": "hour"}

CodeList = Mapping[str, Any]  # {"groups": {prefix: group}, "default": group}


def load_codelists(folder: Path) -> dict[str, CodeList]:
    """Code lists by name (the file stem), e.g. codelists/diagnosis_group.yaml -> 'diagnosis_group'."""
    if not folder.is_dir():
        return {}
    return {p.stem: yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("*.y*ml"))}


def age_bands(width: int = AGE_WIDTH, top: int = AGE_TOP) -> list[str]:
    return [f"{lo}-{lo + width - 1}" for lo in range(0, top, width)] + [f"{top}+"]


@dataclass(frozen=True)
class StatisticsPlanner:
    detections: DetectionReport
    scenario: Scenario
    codelists: Mapping[str, CodeList]

    def plan(self) -> tuple[list[Aggregate], DifferentialPrivacy | None]:
        stats = self.scenario.statistics
        if not stats:
            return [], None
        unit, unit_reason = self._unit(stats[0].table)
        targets = self.scenario.targets
        budget = targets.epsilon or DEFAULT_EPSILON
        weights = sum(s.weight for s in stats)
        aggregates = [
            self._aggregate(s, int(budget * s.weight / weights * 10_000) / 10_000, unit_reason) for s in stats
        ]
        dp = DifferentialPrivacy(
            unit=unit,
            max_rows_per_unit=targets.rows_per_person or DEFAULT_ROWS_PER_PERSON,
            budget_cap=targets.epsilon_cap,
        )
        return aggregates, dp

    def _columns(self, table: str) -> list[ColumnDetection]:
        return [c for c in self.detections.columns if c.table == table]

    def _column(self, table: str, name: str) -> ColumnDetection:
        found = next((c for c in self._columns(table) if c.column == name), None)
        if found is None:
            raise ValueError(f"statistic needs {table}.{name}, which the detection report does not have")
        return found

    def _unit(self, table: str) -> tuple[str, str]:
        cols = self._columns(table)
        person = next((c for c in cols if c.subtype in PERSON_KEYS), None)
        if person is not None:
            return person.column, f"one person = one {person.column}"
        row = next((c for c in cols if c.privacy_role is R.RECORD_KEY), None)
        if row is None:
            raise ValueError(f"{table}: no person or row identifier found to bound contributions")
        return row.column, (
            f"{REVIEW}: no person identifier found, so each row counts as a person; people with several rows "
            "are protected less. Confirm or set differential_privacy.unit before approving"
        )

    def _aggregate(self, stat: Statistic, epsilon: float, unit_reason: str) -> Aggregate:
        dims = [self._dimension(stat, n) for n in stat.by]
        what = "mean " + str(stat.measure.column) if stat.measure.kind == "mean" else stat.measure.kind
        text = f"{what} by {', '.join(d.output_name for d in dims)}; epsilon {epsilon:g} of the release"
        reason = f"{unit_reason}. {text}." if unit_reason.startswith(REVIEW) else f"{text}; {unit_reason}."
        return Aggregate(
            name=stat.name, table=stat.table, dimensions=dims, measure=stat.measure, exclude=stat.exclude,
            epsilon=epsilon, reason=reason,
        )  # fmt: skip

    def _dimension(self, stat: Statistic, need: Need) -> Dimension:
        col = self._column(stat.table, need.column)
        detail = need.detail
        if detail is not None and detail in self.codelists:
            code = self.codelists[detail]
            groups = {str(k): str(v) for k, v in dict(code["groups"]).items()}
            default = str(code.get("default", "other"))
            coded = {"to": "code_group", "groups": groups, "default": default}
            return Dimension(column=col.column, name=detail, params=coded, domain=sorted({*groups.values(), default}))
        if col.subtype is S.BIRTH_DATE:
            params: dict[str, Any] = {"to": "age_band", "width": AGE_WIDTH, "top": AGE_TOP}
            if ref := self._event_time(stat):
                params["reference_column"] = ref
            return Dimension(column=col.column, name="age_band", params=params, domain=age_bands())
        if col.subtype in (S.TIMESTAMP, S.DATE):
            unit = detail or "week"
            return Dimension(column=col.column, name=TIME_NAMES.get(unit, unit), params={"to": "time", "unit": unit})
        return Dimension(column=col.column)

    def _event_time(self, stat: Statistic) -> str | None:
        """Age at the event: the statistic's own timestamp, else the table's first timestamp."""
        stamps = [c.column for c in self._columns(stat.table) if c.subtype is S.TIMESTAMP]
        own = [n.column for n in stat.by if n.column in stamps]
        candidates = own or stamps
        return candidates[0] if candidates else None
