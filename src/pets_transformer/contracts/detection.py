"""detection.json: what each column holds and why we think so (written by Detect, read by Plan and the UI)."""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pets_transformer.contracts.base import SCHEMA_VERSION, Contract
from pets_transformer.contracts.taxonomy import PrivacyRole, Subtype


class EvidenceKind(StrEnum):
    VALIDATOR = "validator"  # format check, e.g. ID-code checksum
    NAME_HINT = "name_hint"  # column header looks like a known field
    STATISTICS = "statistics"  # uniqueness, cardinality, value lengths
    LLM = "llm"  # local AI second opinion; never decisive on its own
    MANUAL = "manual"  # a person set or changed it in review


class Evidence(BaseModel):
    """One reason a reviewer can check. Production rule 5: a person approves with evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: EvidenceKind
    detail: str
    score: float | None = Field(default=None, ge=0.0, le=1.0)


class ColumnDetection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    table: str
    column: str
    privacy_role: PrivacyRole
    subtype: Subtype
    confidence: float = Field(ge=0.0, le=1.0)
    special_category: bool = False  # GDPR Art. 9: health, union membership, religion ...
    evidence: list[Evidence] = Field(default_factory=list)
    basis: list[str] = Field(default_factory=list)  # IDs of the laws and standards behind the label (docs/SOURCES.md)
    needed_by: list[str] = Field(default_factory=list)  # scenarios whose data request includes this column
    source_column: str | None = None  # the input header, when the column had no name and a person named it


class DetectionReport(Contract):
    schema_version: Literal["1"] = SCHEMA_VERSION
    dataset: str
    generated_at: datetime
    tool_version: str
    notes: str | None = None
    columns: list[ColumnDetection]

    def to_pets_eval_rows(self) -> list[dict[str, str]]:
        """Rows in the `dataset,table,column,privacy_role,subtype` format that `pets-eval detect` scores."""
        return [
            {
                "dataset": self.dataset,
                "table": c.table,
                "column": c.column,
                "privacy_role": c.privacy_role.value,
                "subtype": c.subtype.value,
            }
            for c in self.columns
        ]
