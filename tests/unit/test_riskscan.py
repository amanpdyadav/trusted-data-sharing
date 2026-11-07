"""Risk scan of raw data: links between tables, exposure per table, one person across tables."""

from datetime import UTC, datetime

import pandas as pd

from pets_transformer.assess.riskscan import scan
from pets_transformer.contracts import ColumnDetection, DetectionReport, PrivacyRole, Subtype

R, S = PrivacyRole, Subtype


def _c(table: str, column: str, role: PrivacyRole, sub: Subtype) -> ColumnDetection:
    return ColumnDetection(table=table, column=column, privacy_role=role, subtype=sub, confidence=0.9)


DET = DetectionReport(
    dataset="toy", generated_at=datetime(2026, 11, 7, tzinfo=UTC), tool_version="t",
    columns=[
        _c("visits", "visit_id", R.RECORD_KEY, S.RECORD_ID),
        _c("visits", "hetu", R.DIRECT_IDENTIFIER, S.NATIONAL_ID),
        _c("visits", "name", R.DIRECT_IDENTIFIER, S.PERSON_NAME),
        _c("visits", "town", R.QUASI_IDENTIFIER, S.MUNICIPALITY),
        _c("labs", "lab_id", R.RECORD_KEY, S.RECORD_ID),
        _c("labs", "visit_id", R.TECHNICAL_IDENTIFIER, S.RECORD_ID),
        _c("labs", "crp", R.SENSITIVE_ATTRIBUTE, S.MEASUREMENT),
    ],
)  # fmt: skip
FRAMES = {
    "visits": pd.DataFrame({
        "visit_id": ["V1", "V2", "V3"], "hetu": ["H1", "H1", "H2"], "name": ["Ann", "Ann", "Bo"],
        "town": ["A", "A", "B"],
    }),
    "labs": pd.DataFrame({"lab_id": ["L1", "L2", "L3"], "visit_id": ["V1", "V2", "V9"], "crp": ["5", "80", "1"]}),
}  # fmt: skip


def test_links_follow_shared_keys() -> None:
    (link,) = scan(DET, FRAMES).links
    assert (link.from_table, link.from_column, link.to_table, link.meaning) == (
        "labs",
        "visit_id",
        "visits",
        "same record",
    )
    assert link.overlap == round(2 / 3, 3)


def test_exposure_names_what_links_outside_and_who_stands_out() -> None:
    visits = next(t for t in scan(DET, FRAMES).tables if t.table == "visits")
    assert visits.outside_links == ["hetu", "name"]
    assert visits.quasi_identifiers == ["town"]
    assert visits.unique_share == round(1 / 3, 4)


def test_person_card_gathers_one_person_across_tables() -> None:
    card = scan(DET, FRAMES).person
    assert [r["visit_id"] for r in card["visits"]] == ["V1", "V2"]  # the person with most records
    assert [r["crp"] for r in card["labs"]] == ["5", "80"]


def test_no_person_identifier_means_no_card() -> None:
    det = DET.model_copy(update={"columns": [c for c in DET.columns if c.column != "hetu"]})
    assert scan(det, FRAMES).person == {}
