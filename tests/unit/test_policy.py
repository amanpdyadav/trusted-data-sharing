from datetime import UTC, datetime

import pytest

from pets_transformer.contracts import ColumnDetection, DetectionReport, PrivacyRole, Subtype, Technique, TrustLevel
from pets_transformer.plan.policy import REVIEW, RulePolicy
from pets_transformer.plan.scenario import Need, Scenario

R, S, T = PrivacyRole, Subtype, Technique


def _col(table: str, column: str, role: PrivacyRole, sub: Subtype, conf: float = 0.9) -> ColumnDetection:
    return ColumnDetection(table=table, column=column, privacy_role=role, subtype=sub, confidence=conf)


DETECTIONS = DetectionReport(
    dataset="toy",
    generated_at=datetime(2026, 11, 7, tzinfo=UTC),
    tool_version="test",
    columns=[
        _col("visits", "visit_id", R.RECORD_KEY, S.RECORD_ID),
        _col("visits", "hetu", R.DIRECT_IDENTIFIER, S.NATIONAL_ID),
        _col("visits", "name", R.DIRECT_IDENTIFIER, S.PERSON_NAME),
        _col("visits", "born", R.QUASI_IDENTIFIER, S.BIRTH_DATE),
        _col("visits", "arrived", R.QUASI_IDENTIFIER, S.TIMESTAMP),
        _col("visits", "town", R.QUASI_IDENTIFIER, S.MUNICIPALITY),
        _col("visits", "sex", R.QUASI_IDENTIFIER, S.SEX),
        _col("visits", "icd", R.SENSITIVE_ATTRIBUTE, S.DIAGNOSIS_CODE),
        _col("visits", "doctor_id", R.TECHNICAL_IDENTIFIER, S.EMPLOYEE_ID),
        _col("visits", "note", R.FREE_TEXT, S.FREE_TEXT),
        _col("labs", "lab_id", R.RECORD_KEY, S.RECORD_ID),
        _col("labs", "visit_id", R.TECHNICAL_IDENTIFIER, S.RECORD_ID),
        _col("labs", "result", R.TECHNICAL_IDENTIFIER, S.RECORD_ID, conf=0.45),
        _col("stats", "stat_id", R.RECORD_KEY, S.RECORD_ID),
        _col("stats", "count", R.NON_SENSITIVE, S.MEASUREMENT),
    ],
)


def _scenario(trust: TrustLevel = TrustLevel.CONTROLLED_RESEARCH, needs: list[Need] | None = None) -> Scenario:
    default = [
        Need(column="arrived", detail="time_of_day"),
        Need(column="town"),
        Need(column="born"),
        Need(column="icd"),
        Need(column="hetu"),
        Need(column="name"),
        Need(table="labs", column="result"),
    ]
    return Scenario(
        id="TOY-S1", dataset="toy", title="t", recipient="r", purpose="p", trust_level=trust, threat_model="tm",
        needs=default if needs is None else needs,
    )  # fmt: skip


def _plan(**kw: object) -> dict[tuple[str, str], tuple[Technique, dict[str, object], str]]:
    plan = RulePolicy().plan(DETECTIONS, _scenario(**kw))  # type: ignore[arg-type]
    return {(a.table, a.column): (a.technique, a.params, a.reason) for a in plan.actions}


def test_contact_details_never_leave_even_when_requested() -> None:
    technique, _, reason = _plan()[("visits", "name")]
    assert technique is T.DROP
    assert "never leave" in reason


def test_unrequested_columns_and_tables_are_dropped() -> None:
    plan = RulePolicy().plan(DETECTIONS, _scenario())
    assert plan.tables == ["visits", "labs"]  # "stats" is withheld entirely
    actions = _plan()
    assert actions[("visits", "sex")][0] is T.DROP
    assert actions[("visits", "doctor_id")][0] is T.DROP
    assert actions[("visits", "note")][0] is T.DROP


def test_keys_and_joins_become_keyed_codes() -> None:
    actions = _plan()
    for key in [("visits", "visit_id"), ("visits", "hetu"), ("labs", "visit_id"), ("labs", "lab_id")]:
        assert actions[key][0] is T.PSEUDONYMISE, key


def test_requested_quasi_identifiers_are_generalised_and_checked_in_request_order() -> None:
    plan = RulePolicy().plan(DETECTIONS, _scenario())
    actions = _plan()
    assert actions[("visits", "born")][1]["reference_column"] == "arrived"
    assert actions[("visits", "born")][1]["rename_to"] == "age"
    assert actions[("visits", "arrived")][1] == {"to": "time", "unit": "time_of_day"}
    assert actions[("visits", "icd")][1] == {"to": "truncate", "length": 3}
    assert plan.quasi_identifiers == {"visits": ["arrived", "town", "age"]}
    assert plan.record_keys == {"visits": "visit_id", "labs": "lab_id"}


def test_weak_evidence_on_a_requested_column_is_kept_and_flagged() -> None:
    technique, _, reason = _plan()[("labs", "result")]
    assert technique is T.KEEP
    assert reason.startswith(REVIEW)


def test_public_release_has_no_linking_codes() -> None:
    actions = _plan(trust=TrustLevel.PUBLIC)
    assert actions[("visits", "visit_id")][0] is T.DROP
    assert actions[("visits", "hetu")][0] is T.DROP


def test_without_a_data_request_non_identifiers_are_kept() -> None:
    plan = RulePolicy().plan(DETECTIONS, _scenario(needs=[]))
    actions = {(a.table, a.column): a.technique for a in plan.actions}
    assert "stats" in plan.tables
    assert actions[("visits", "sex")] is T.KEEP
    assert actions[("visits", "arrived")] is T.GENERALISE


def test_the_planner_never_approves() -> None:
    plan = RulePolicy().plan(DETECTIONS, _scenario())
    assert not plan.approved
    assert plan.approved_by is None


@pytest.mark.parametrize("trust", list(TrustLevel))
def test_every_column_gets_a_reason(trust: TrustLevel) -> None:
    assert all(len(reason) > 10 for _, _, reason in _plan(trust=trust).values())
