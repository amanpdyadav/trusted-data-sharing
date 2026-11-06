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
    actions: list[ColumnAction]
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

    @property
    def tables(self) -> list[str]:
        """Tables the plan releases, in first-mentioned order. Tables not named here are withheld."""
        return list(dict.fromkeys(a.table for a in self.actions))

    def action_for(self, table: str, column: str) -> ColumnAction | None:
        return next((a for a in self.actions if a.table == table and a.column == column), None)
