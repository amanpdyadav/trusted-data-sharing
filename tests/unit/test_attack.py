"""Attack replay: one person singled out in the raw data, followed into the release through the private row map."""

from datetime import UTC, datetime

import pandas as pd

from pets_transformer.assess import attack
from pets_transformer.assess.riskscan import find_links
from pets_transformer.contracts import ColumnDetection, DetectionReport, Plan, PrivacyRole, Subtype

R, S = PrivacyRole, Subtype


def _c(table: str, column: str, role: PrivacyRole, sub: Subtype) -> ColumnDetection:
    return ColumnDetection(table=table, column=column, privacy_role=role, subtype=sub, confidence=0.9)


DET = DetectionReport(
    dataset="toy", generated_at=datetime(2026, 11, 7, tzinfo=UTC), tool_version="t",
    columns=[
        _c("visits", "visit_id", R.RECORD_KEY, S.RECORD_ID),
        _c("visits", "hetu", R.DIRECT_IDENTIFIER, S.NATIONAL_ID),
        _c("visits", "name", R.DIRECT_IDENTIFIER, S.PERSON_NAME),
        _c("visits", "born", R.QUASI_IDENTIFIER, S.BIRTH_DATE),
        _c("visits", "town", R.QUASI_IDENTIFIER, S.MUNICIPALITY),
        _c("visits", "arrived", R.QUASI_IDENTIFIER, S.TIMESTAMP),
        _c("labs", "lab_id", R.RECORD_KEY, S.RECORD_ID),
        _c("labs", "visit_id", R.TECHNICAL_IDENTIFIER, S.RECORD_ID),
    ],
)  # fmt: skip
FRAMES = {
    "visits": pd.DataFrame({
        "visit_id": ["V1", "V2", "V3", "V4"], "hetu": ["H1", "H1", "H2", "H3"], "name": ["Ann", "Ann", "Bo", "Cy"],
        "born": ["1958", "1958", "1990", "1990"], "town": ["A", "A", "B", "B"], "arrived": ["t1", "t2", "t3", "t4"],
    }),
    "labs": pd.DataFrame({"lab_id": ["L1", "L2", "L3"], "visit_id": ["V1", "V2", "V3"]}),
}  # fmt: skip


def _plan(actions: list[tuple[str, str, dict[str, object]]]) -> Plan:
    return Plan.model_validate({
        "scenario_id": "T", "dataset": "toy", "created_at": "2026-11-07T00:00:00Z", "k_target": 2,
        "record_keys": {"visits": "visit_id"},
        "actions": [{"table": "visits", "column": c, "technique": t, "params": p, "reason": "test"}
                    for c, t, p in actions],
    })  # fmt: skip


def test_background_prefers_personal_facts_over_event_times() -> None:
    assert attack.background(DET, "visits") == ["born", "town"]


def test_raw_attack_singles_out_one_person_and_reaches_linked_rows() -> None:
    target = attack.pick_target(DET, FRAMES)
    assert target == attack.Target("visits", 0)  # the person with several visits
    reach = attack.reach(DET, FRAMES, find_links(DET, FRAMES), target)
    result = attack.on_raw(DET, FRAMES, target, reach)
    assert result.matches == 1  # two rows, one person
    assert result.outcome == "identified"
    assert result.revealed == {"hetu": "H1", "name": "Ann"}
    assert result.linked == {"visits": 2, "labs": 2}


def test_release_attack_follows_the_row_map_and_counts_people() -> None:
    plan = _plan([
        ("visit_id", "pseudonymise", {}), ("hetu", "pseudonymise", {}), ("name", "drop", {}),
        ("born", "generalise", {"rename_to": "age"}), ("town", "drop", {}), ("arrived", "drop", {}),
    ])  # fmt: skip
    released = pd.DataFrame({"visit_id": ["c3", "c1", "c2", "c4"], "hetu": ["p2", "p1", "p1", "p3"],
                             "age": ["30-39", "60-69", "60-69", "30-39"]})  # fmt: skip
    copy = attack.ReleasedCopy(plan, {"visits": released}, {"visits": ["V3", "V1", "V2", "V4"]})
    result = attack.on_release(DET, FRAMES, attack.Target("visits", 0), copy)
    assert result.usable == ["age"]  # the town was dropped
    assert result.matches == 1  # only one person is in their 60s here: the replay says so honestly
    assert result.hidden == {"hetu": "pseudonymise", "name": "drop"}
    assert result.revealed == {}


def test_release_attack_reports_withheld_and_removed_rows() -> None:
    plan = _plan([("visit_id", "pseudonymise", {})])
    withheld = attack.on_release(DET, FRAMES, attack.Target("visits", 0), attack.ReleasedCopy(plan, {}, {}))
    assert withheld.outcome == "withheld"
    copy = attack.ReleasedCopy(plan, {"visits": pd.DataFrame({"visit_id": ["c3"]})}, {"visits": ["V3"]})
    assert attack.on_release(DET, FRAMES, attack.Target("visits", 0), copy).outcome == "removed"
