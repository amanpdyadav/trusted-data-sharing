"""Scenarios as config files (production rule 4). A company adds a YAML file; no code change needed."""

from collections.abc import Iterable
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from pets_transformer.contracts import DetectionReport, Plan, TrustLevel
from pets_transformer.contracts.base import SCHEMA_VERSION, Contract


class PrivacyTargets(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    k: int | None = Field(default=None, ge=2)
    epsilon: float | None = Field(default=None, gt=0)
    text_recall: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None


class Need(BaseModel):
    """One variable the receiver asked for. `detail` names the resolution, e.g. age_band or time_of_day."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str
    table: str | None = None
    detail: str | None = None


class Scenario(Contract):
    schema_version: Literal["1"] = SCHEMA_VERSION
    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]*$")
    dataset: str
    title: str
    recipient: str
    purpose: str
    trust_level: TrustLevel
    threat_model: str
    legal_context: str | None = None
    utility_requirements: list[str] = Field(default_factory=list)
    targets: PrivacyTargets = Field(default_factory=PrivacyTargets)
    # the data request, most important first: anything not listed is not released (data minimisation)
    needs: list[Need] = Field(default_factory=list)
    notes: str | None = None


def load_scenarios(folders: Iterable[Path]) -> dict[str, Scenario]:
    """All *.yaml scenarios from the given folders, in order. Duplicate ids are an error."""
    found: dict[str, Scenario] = {}
    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.y*ml")):
            scenario = Scenario.load(path)
            if scenario.id in found:
                raise ValueError(f"scenario {scenario.id} defined twice (second time in {path})")
            found[scenario.id] = scenario
    return found


class PolicyEngine(Protocol):
    """Turns detections + a scenario into a plan. Deterministic: the same inputs give the same plan."""

    def plan(self, detections: DetectionReport, scenario: Scenario) -> Plan: ...
