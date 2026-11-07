"""Planning published statistics: coarsening per detected type, budget split, unit of privacy, no rows."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pets_transformer.contracts import ColumnDetection, DetectionReport, Measure, PrivacyRole, Subtype, TrustLevel
from pets_transformer.plan.policy import REVIEW, RulePolicy
from pets_transformer.plan.scenario import Need, PrivacyTargets, Scenario, Statistic
from pets_transformer.plan.statistics import age_bands, load_codelists

R, S = PrivacyRole, Subtype
CODES = {"diagnosis_group": {"groups": {"J10": "ILI", "S": "injury"}, "default": "other"}}


def _col(column: str, role: PrivacyRole, sub: Subtype) -> ColumnDetection:
    return ColumnDetection(table="visits", column=column, privacy_role=role, subtype=sub, confidence=0.9)


def _detections(person: bool = True) -> DetectionReport:
    cols = [
        _col("visit_id", R.RECORD_KEY, S.RECORD_ID),
        _col("born", R.QUASI_IDENTIFIER, S.BIRTH_DATE),
        _col("arrived", R.QUASI_IDENTIFIER, S.TIMESTAMP),
        _col("icd", R.SENSITIVE_ATTRIBUTE, S.DIAGNOSIS_CODE),
        _col("town", R.QUASI_IDENTIFIER, S.MUNICIPALITY),
        _col("los", R.SENSITIVE_ATTRIBUTE, S.MEASUREMENT),
    ]
    if person:
        cols.append(_col("hetu", R.DIRECT_IDENTIFIER, S.NATIONAL_ID))
    return DetectionReport(
        dataset="toy", generated_at=datetime(2026, 11, 7, tzinfo=UTC), tool_version="t", columns=cols
    )


def _scenario(**kw: object) -> Scenario:
    stats = [
        Statistic(
            name="weekly", table="visits", weight=2,
            by=[
                Need(column="arrived", detail="week"), Need(column="born"),
                Need(column="icd", detail="diagnosis_group"),
            ],
        ),
        Statistic(name="hours", table="visits", by=[Need(column="arrived", detail="time_of_day")]),
        Statistic(
            name="stay", table="visits", by=[Need(column="town")],
            measure=Measure(kind="mean", column="los", upper=1440),
        ),
    ]  # fmt: skip
    base: dict[str, object] = {
        "id": "TOY-S2", "dataset": "toy", "title": "t", "recipient": "anyone", "purpose": "p",
        "trust_level": TrustLevel.PUBLIC, "threat_model": "tm", "statistics": stats,
        "targets": PrivacyTargets(epsilon=1.0, epsilon_cap=4.0, rows_per_person=2),
    }  # fmt: skip
    return Scenario.model_validate(base | kw)


def test_statistics_only_scenario_releases_no_rows_and_states_its_privacy() -> None:
    plan = RulePolicy(CODES).plan(_detections(), _scenario())
    assert plan.actions == []
    assert [a.name for a in plan.aggregates] == ["weekly", "hours", "stay"]
    dp = plan.differential_privacy
    assert dp is not None
    assert (dp.unit, dp.max_rows_per_unit, dp.budget_cap) == ("hetu", 2, 4.0)
    assert plan.epsilon == 1.0
    assert [a.epsilon for a in plan.aggregates] == [0.5, 0.25, 0.25]


def test_each_variable_is_coarsened_by_its_detected_type() -> None:
    weekly = RulePolicy(CODES).plan(_detections(), _scenario()).aggregates[0]
    week, age, group = weekly.dimensions
    assert (week.output_name, week.params) == ("week", {"to": "time", "unit": "week"})
    assert age.output_name == "age_band"
    assert age.params["reference_column"] == "arrived"  # age at the visit, not today
    assert age.domain == age_bands()
    assert group.params["to"] == "code_group"
    assert group.domain == ["ILI", "injury", "other"]


def test_hour_of_day_and_plain_categories() -> None:
    plan = RulePolicy(CODES).plan(_detections(), _scenario())
    hour = plan.aggregates[1].dimensions[0]
    town = plan.aggregates[2].dimensions[0]
    assert (hour.output_name, hour.params["unit"]) == ("hour", "time_of_day")
    assert (town.output_name, town.params, town.domain) == ("town", {}, None)


def test_without_a_person_identifier_rows_are_the_unit_and_a_person_must_review() -> None:
    plan = RulePolicy(CODES).plan(_detections(person=False), _scenario())
    assert plan.differential_privacy is not None
    assert plan.differential_privacy.unit == "visit_id"
    assert all(a.reason.startswith(REVIEW) for a in plan.aggregates)


def test_unknown_column_is_an_error() -> None:
    bad = Statistic(name="x", table="visits", by=[Need(column="ghost")])
    with pytest.raises(ValueError, match=r"visits\.ghost"):
        RulePolicy(CODES).plan(_detections(), _scenario(statistics=[bad]))


def test_code_lists_load_by_file_name(tmp_path: Path) -> None:
    (tmp_path / "diagnosis_group.yaml").write_text("default: other\ngroups: {J10: ILI}\n", encoding="utf-8")
    assert load_codelists(tmp_path) == {"diagnosis_group": {"default": "other", "groups": {"J10": "ILI"}}}
    assert load_codelists(tmp_path / "missing") == {}


def test_shipped_code_list_and_scenario_parse() -> None:
    root = Path(__file__).resolve().parents[2]
    assert "diagnosis_group" in load_codelists(root / "codelists")
    s2 = Scenario.load(root / "scenarios" / "HEALTH-S2.yaml")
    assert s2.trust_level is TrustLevel.PUBLIC
    assert s2.needs == []
    assert len(s2.statistics) == 6
