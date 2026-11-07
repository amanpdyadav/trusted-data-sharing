"""needed_by: scenarios that request a column."""

from datetime import UTC, datetime

from pets_transformer.contracts import ColumnDetection, DetectionReport, PrivacyRole, Subtype
from pets_transformer.detect.needs import annotate_needs
from pets_transformer.plan.scenario import Scenario


def test_columns_are_marked_with_the_scenarios_that_request_them() -> None:
    cols = [ColumnDetection(table="ed", column=c, privacy_role=PrivacyRole.SENSITIVE_ATTRIBUTE,
                            subtype=Subtype.HEALTH_DATA, confidence=0.9) for c in ("los_minutes", "pain")]  # fmt: skip
    report = DetectionReport(dataset="health", generated_at=datetime.now(UTC), tool_version="t", columns=cols)
    sc = Scenario.model_validate({"id": "HEALTH-S1", "dataset": "health", "title": "t", "recipient": "r",
                                  "purpose": "p", "trust_level": "controlled_research", "threat_model": "t",
                                  "needs": [{"table": "ed", "column": "los_minutes"}]})  # fmt: skip
    got = {c.column: c.needed_by for c in annotate_needs(report, [sc]).columns}
    assert got == {"los_minutes": ["HEALTH-S1"], "pain": []}
