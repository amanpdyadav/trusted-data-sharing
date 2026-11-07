from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from pets_transformer.contracts import (
    ColumnAction,
    DetectionReport,
    Metrics,
    Plan,
    RecordSpans,
    ReleasedFile,
    ReleaseManifest,
    Span,
    SpanLabel,
    Technique,
)
from pets_transformer.plan.scenario import Scenario

NOW = datetime(2026, 11, 6, 22, 0, tzinfo=UTC)
SHA = "a" * 64


def _plan(**kw: object) -> Plan:
    base: dict[str, object] = {
        "dataset": "health",
        "scenario_id": "HEALTH-S1",
        "created_at": NOW,
        "actions": [ColumnAction(table="t", column="c", technique=Technique.DROP, reason="not needed")],
    }
    return Plan.model_validate(base | kw)


def _metrics() -> Metrics:
    return Metrics(run_id="r1", dataset="health", scenario_id="HEALTH-S1", created_at=NOW)


# ---------------------------------------------------------------- example files are valid (contract tests)
@pytest.mark.parametrize(
    ("model", "path"),
    [
        (DetectionReport, "examples/contracts/detection.example.json"),
        (Plan, "examples/contracts/plan.example.yaml"),
        (Metrics, "examples/contracts/metrics.quickstart-baseline.json"),
        (Scenario, "scenarios/HEALTH-S1.yaml"),
    ],
)
def test_example_files_validate(repo: Path, model: type, path: str) -> None:
    assert model.load(repo / path)


def test_round_trip_yaml_and_json(tmp_path: Path) -> None:
    plan = _plan()
    for suffix in (".yaml", ".json"):
        assert Plan.load(plan.save(tmp_path / f"plan{suffix}")) == plan


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        _plan(surprise=True)


# ---------------------------------------------------------------- plan rules
def test_approved_plan_needs_approver() -> None:
    with pytest.raises(ValidationError, match="name who approved"):
        _plan(approved=True)
    assert _plan(approved=True, approved_by="Aman").approved


def test_one_action_per_column() -> None:
    a = ColumnAction(table="t", column="c", technique=Technique.DROP, reason="not needed")
    with pytest.raises(ValidationError, match="two actions"):
        _plan(actions=[a, a])


def test_action_lookup() -> None:
    assert _plan().action_for("t", "c") is not None
    assert _plan().action_for("t", "missing") is None


# ---------------------------------------------------------------- manifest rules
def _manifest(plan: Plan, files: list[ReleasedFile]) -> ReleaseManifest:
    return ReleaseManifest(
        release_id="rel-1",
        created_at=NOW,
        tool_version="0.1.0",
        input_fingerprint=SHA,
        key_domain="HEALTH-S1/test/2026-11",
        plan=plan,
        metrics=_metrics(),
        files=files,
        residual_risks=["arrival hour still narrows candidates"],
    )


def test_release_requires_approved_plan() -> None:
    with pytest.raises(ValidationError, match="approved plan"):
        _manifest(_plan(), [])
    assert _manifest(_plan(approved=True, approved_by="Aman"), [])


def test_release_never_lists_row_maps_or_paths() -> None:
    with pytest.raises(ValidationError):
        ReleasedFile(name="rowmap_ed_visits.csv", sha256=SHA, rows=1)
    with pytest.raises(ValidationError):
        ReleasedFile(name="../secret.csv", sha256=SHA, rows=1)
    assert ReleasedFile(name="ed_visits.csv", sha256=SHA, rows=1)


# ---------------------------------------------------------------- detection and spans
def test_detection_exports_pets_eval_rows(repo: Path) -> None:
    report = DetectionReport.load(repo / "examples/contracts/detection.example.json")
    rows = report.to_pets_eval_rows()
    assert rows[0] == {
        "dataset": "health",
        "table": "ed_visits",
        "column": "patient_hetu",
        "privacy_role": "direct_identifier",
        "subtype": "NATIONAL_ID",
    }


def test_span_offsets_must_match_text() -> None:
    with pytest.raises(ValidationError, match="length"):
        Span(start=0, end=5, label=SpanLabel.PERSON, text="Aino")
    s = Span(start=0, end=4, label=SpanLabel.PERSON, text="Aino")
    assert RecordSpans(record_id="T1", spans=[s]).to_pets_eval() == {
        "record_id": "T1",
        "spans": [{"start": 0, "end": 4, "label": "PERSON"}],
    }
