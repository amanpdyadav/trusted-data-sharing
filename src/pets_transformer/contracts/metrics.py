"""metrics.json: the scores the UI and the video show (written by Check, read by the UI and the release note)."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pets_transformer.contracts.base import SCHEMA_VERSION, Contract

Share = float  # 0..1


class MetricSource(StrEnum):
    OURS = "ours"  # our own risk engine (works on real data, no answer key)
    PETS_EVAL = "pets-eval"  # organisers' scorer (practice data only)


class RiskComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    value: Share = Field(ge=0.0, le=1.0)
    source: MetricSource


class AttackResult(BaseModel):
    """One attack, before vs after. `unit` says how to read the numbers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    unit: Literal["share_reidentified", "candidates_left"]
    before: float = Field(ge=0.0)
    after: float | None = Field(default=None, ge=0.0)
    source: MetricSource


class UtilityTaskScore(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    description: str
    score: Share | None = Field(default=None, ge=0.0, le=1.0)  # None = not answerable


class Metrics(Contract):
    schema_version: Literal["1"] = SCHEMA_VERSION
    run_id: str
    dataset: str
    scenario_id: str
    created_at: datetime
    privacy: Share | None = Field(default=None, ge=0.0, le=1.0)
    utility: Share | None = Field(default=None, ge=0.0, le=1.0)
    composite: Share | None = Field(default=None, ge=0.0, le=1.0)
    k_min: int | None = Field(default=None, ge=0)
    share_below_k: Share | None = Field(default=None, ge=0.0, le=1.0)
    epsilon_spent: float | None = Field(default=None, ge=0.0)
    risks: list[RiskComponent] = Field(default_factory=list)
    attacks: list[AttackResult] = Field(default_factory=list)
    utility_tasks: list[UtilityTaskScore] = Field(default_factory=list)
    notes: str | None = None
