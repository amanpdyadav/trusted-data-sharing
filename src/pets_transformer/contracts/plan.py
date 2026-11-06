"""plan.yaml: the protection chosen for each column, with a reason (written by Plan, approved in Review)."""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from pets_transformer.contracts.base import SCHEMA_VERSION, Contract


class Technique(StrEnum):
    KEEP = "keep"
    DROP = "drop"
    PSEUDONYMISE = "pseudonymise"  # keyed HMAC code; joins survive, reversal needs the key
    GENERALISE = "generalise"  # age bands, shorter postcodes, coarser time, 3-char ICD-10 ...
    SUPPRESS = "suppress"  # blank out values in rare groups
    REDACT_TEXT = "redact_text"  # replace personal details in free text with tags
    AGGREGATE = "aggregate"  # publish counts instead of rows
    NOISE = "noise"  # differential privacy on published counts
    SYNTHESISE = "synthesise"  # synthetic rows instead of real ones


class ColumnAction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    table: str
    column: str
    technique: Technique
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(min_length=3)


class Dimension(BaseModel):
    """One 'group by' of a published table, coarsened like a released column (same generalise params)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str
    params: dict[str, Any] = Field(default_factory=dict)  # e.g. {"to": "time", "unit": "week"}; empty = as is
    name: str | None = None  # column name in the published table (default: the source column)
    # Public list of categories. Cells are published for every listed value, so an empty cell is not hidden
    # by its absence. None = the categories seen in the data (only for values that are public anyway, e.g. weeks).
    domain: list[str] | None = None

    @property
    def output_name(self) -> str:
        return self.name or self.column


class Measure(BaseModel):
    """count: rows per cell; mean: average of a numeric column; share: fraction of rows whose value is listed."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["count", "mean", "share"] = "count"
    column: str | None = None
    lower: float = 0.0  # mean: values are clipped to [lower, upper] (public bounds, part of the privacy claim)
    upper: float | None = None
    values: list[str] = Field(default_factory=list)  # share: the values that count as 'yes'

    @model_validator(mode="after")
    def _complete(self) -> "Measure":
        if self.kind != "count" and not self.column:
            raise ValueError(f"a {self.kind} measure needs a column")
        if self.kind == "mean" and (self.upper is None or self.upper <= self.lower):
            raise ValueError("a mean measure needs public bounds with upper > lower")
        if self.kind == "share" and not self.values:
            raise ValueError("a share measure needs the values that count as 'yes'")
        return self


class Aggregate(BaseModel):
    """A published table of noisy statistics, e.g. weekly visits by age band and diagnosis group."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")  # file name of the published table
    table: str
    dimensions: list[Dimension] = Field(min_length=1)
    measure: Measure = Field(default_factory=Measure)
    epsilon: float = Field(gt=0)  # this table's share of the release budget (sequential composition)
    reason: str = Field(min_length=3)


class DifferentialPrivacy(BaseModel):
    """The privacy claim behind every aggregate: who is protected and how much one of them can contribute."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    unit: str  # column naming the protected person, e.g. patient_hetu; rows without one count as their own person
    max_rows_per_unit: int = Field(ge=1)  # contribution bound: extra rows of one person are left out at random
    mechanism: Literal["discrete_laplace"] = "discrete_laplace"
    delta: Literal[0] = 0


class Plan(Contract):
    schema_version: Literal["1"] = SCHEMA_VERSION
    dataset: str
    scenario_id: str
    created_at: datetime
    k_target: int = Field(default=5, ge=2)
    epsilon: float | None = Field(default=None, gt=0)
    # table -> released column names checked together for k, most important first (suppression blanks from the end)
    quasi_identifiers: dict[str, list[str]] = Field(default_factory=dict)
    record_keys: dict[str, str] = Field(default_factory=dict)  # table -> source row-id column, for private row maps
    actions: list[ColumnAction] = Field(default_factory=list)
    aggregates: list[Aggregate] = Field(default_factory=list)  # published noisy statistics (public dashboards)
    differential_privacy: DifferentialPrivacy | None = None
    approved: bool = False
    approved_by: str | None = None

    @model_validator(mode="after")
    def _approval_needs_a_name(self) -> "Plan":
        if self.approved and not self.approved_by:
            raise ValueError("an approved plan must name who approved it")
        return self

    @model_validator(mode="after")
    def _one_action_per_column(self) -> "Plan":
        seen: set[tuple[str, str]] = set()
        for a in self.actions:
            key = (a.table, a.column)
            if key in seen:
                raise ValueError(f"two actions for {a.table}.{a.column}")
            seen.add(key)
        return self

    @model_validator(mode="after")
    def _aggregates_state_their_privacy(self) -> "Plan":
        if not self.aggregates:
            return self
        if self.differential_privacy is None:
            raise ValueError("aggregates need a differential_privacy section (unit and contribution bound)")
        names = [a.name for a in self.aggregates]
        if len(set(names)) != len(names):
            raise ValueError("two aggregates share a name")
        if self.epsilon is not None and self.epsilon_spent > self.epsilon + 1e-9:
            raise ValueError(f"aggregates spend epsilon {self.epsilon_spent:g}, more than the plan's {self.epsilon:g}")
        return self

    @property
    def epsilon_spent(self) -> float:
        """Total epsilon of this release: aggregates compose sequentially (each person may be in all of them)."""
        return sum(a.epsilon for a in self.aggregates)

    @property
    def tables(self) -> list[str]:
        """Tables the plan releases, in first-mentioned order. Tables not named here are withheld."""
        return list(dict.fromkeys(a.table for a in self.actions))

    def action_for(self, table: str, column: str) -> ColumnAction | None:
        return next((a for a in self.actions if a.table == table and a.column == column), None)
