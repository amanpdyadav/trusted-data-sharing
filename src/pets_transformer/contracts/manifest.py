"""manifest.json: the release note that travels with protected files (production rule 7: audit-ready).

It embeds the approved Plan and the Metrics instead of copying their fields (DRY).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from pets_transformer.contracts.base import SCHEMA_VERSION, Contract
from pets_transformer.contracts.metrics import Metrics
from pets_transformer.contracts.plan import Plan


class ReleasedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(pattern=r"^[^/\\]+$")  # a bare file name, never a path
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    rows: int = Field(ge=0)

    @field_validator("name")
    @classmethod
    def _never_a_row_map(cls, name: str) -> str:
        if name.startswith("rowmap_") or name in {".", ".."}:
            raise ValueError("row maps and special names never ship in a release")
        return name


class LlmUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model: str
    digest: str | None = None
    used_for: list[str]


class ReleaseManifest(Contract):
    schema_version: Literal["1"] = SCHEMA_VERSION
    release_id: str
    created_at: datetime
    tool_version: str
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    key_domain: str  # which derived key was used; never the key itself
    plan: Plan
    metrics: Metrics
    files: list[ReleasedFile]
    residual_risks: list[str] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
    llm: LlmUsage | None = None

    @model_validator(mode="after")
    def _only_approved_plans_ship(self) -> "ReleaseManifest":
        if not self.plan.approved:
            raise ValueError("a release needs an approved plan")
        if self.plan.scenario_id != self.metrics.scenario_id:
            raise ValueError("plan and metrics are for different scenarios")
        return self
