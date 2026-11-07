"""The four shared files plus text spans. One typed model each; JSON schemas are generated from these."""

from pets_transformer.contracts.base import Contract
from pets_transformer.contracts.detection import ColumnDetection, DetectionReport, Evidence, EvidenceKind
from pets_transformer.contracts.manifest import LlmUsage, ReleasedFile, ReleaseManifest
from pets_transformer.contracts.metrics import (
    AttackResult,
    Metrics,
    MetricSource,
    RiskComponent,
    UtilityTaskScore,
)
from pets_transformer.contracts.plan import (
    Aggregate,
    ColumnAction,
    ColumnName,
    DifferentialPrivacy,
    Dimension,
    Measure,
    Plan,
    Technique,
)
from pets_transformer.contracts.spans import RecordSpans, Span
from pets_transformer.contracts.taxonomy import PrivacyRole, SpanLabel, Subtype, TrustLevel

CONTRACTS: dict[str, type[Contract]] = {
    "detection": DetectionReport,
    "plan": Plan,
    "metrics": Metrics,
    "manifest": ReleaseManifest,
}

__all__ = [
    "CONTRACTS",
    "Aggregate",
    "AttackResult",
    "ColumnAction",
    "ColumnDetection",
    "ColumnName",
    "Contract",
    "DetectionReport",
    "DifferentialPrivacy",
    "Dimension",
    "Evidence",
    "EvidenceKind",
    "LlmUsage",
    "Measure",
    "MetricSource",
    "Metrics",
    "Plan",
    "PrivacyRole",
    "RecordSpans",
    "ReleaseManifest",
    "ReleasedFile",
    "RiskComponent",
    "Span",
    "SpanLabel",
    "Subtype",
    "Technique",
    "TrustLevel",
    "UtilityTaskScore",
]
