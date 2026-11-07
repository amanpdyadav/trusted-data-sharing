"""Release audit: every release made in the app is listed with its record; the benchmark file is read as data."""

import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from evaluation import receivers, screens
from pets_transformer.config import Settings
from pets_transformer.web import service
from pets_transformer.web.service import App
from pets_transformer.web.workspace import Workspace, WorkspaceError
from tests.conftest import TEST_MASTER_KEY

RECEIVER = {
    "id": "TEST-S1", "title": "Test", "recipient": "Research group", "purpose": "Visits by age",
    "trust_level": "controlled_research", "threat_model": "An outsider",
    "needs": [{"table": "visits", "column": "visit_id"}, {"table": "visits", "column": "age"}],
}  # fmt: skip


@pytest.fixture
def released(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[App, object]:
    monkeypatch.setenv("PETS_MASTER_KEY", TEST_MASTER_KEY.decode())
    monkeypatch.chdir(tmp_path)  # results/ is read relative to the working folder
    folder = tmp_path / "upload"
    folder.mkdir()
    pd.DataFrame({"visit_id": [f"V{i}" for i in range(40)], "age": [str(20 + i % 4) for i in range(40)]}).to_csv(
        folder / "visits.csv", index=False
    )
    app = App(replace(Settings.from_env({}), out_dir=tmp_path / "out"), Workspace(tmp_path / "out" / "web"))
    s = app.workspace.from_folder("clinic", folder)
    app.scan(s)
    app.make_plan(s, None, RECEIVER)
    app.approve(s, "Auditor Test", confirm_review=True)
    app.run(s, "research")
    return app, s


def test_every_release_is_listed_with_its_dataset(released: tuple[App, object]) -> None:
    app, _ = released
    [item] = app.audit_releases()
    assert item["dataset"] == "clinic"
    assert item["approved_by"] == "Auditor Test"
    assert item["published"] is False


def test_a_release_record_carries_the_manifest(released: tuple[App, object]) -> None:
    app, s = released
    rid = app.audit_releases()[0]["release_id"]
    record = app.audit_release(s, rid)  # type: ignore[arg-type]
    assert record["manifest"]["release_id"] == rid
    assert {a["column"] for a in record["manifest"]["plan"]["actions"]} >= {"visit_id", "age"}
    assert record["manifest"]["files"][0]["sha256"]
    assert record["scorecard"] is None  # not scored with the organisers' toolkit
    with pytest.raises(WorkspaceError):
        app.audit_release(s, "nope")  # type: ignore[arg-type]


def test_the_benchmark_is_read_from_results(released: tuple[App, object]) -> None:
    app, _ = released
    assert app.receivers_benchmark() == {"rows": [], "measured_at": None}
    row = receivers.ReceiverResult(
        "CS-S3",
        "customer_service",
        "QA partner",
        "contractual",
        "rows",
        "generated",
        1.0,
        0.9,
        0.95,
        1,
        None,
        "ready",
        "",
        "2026-11-07T15:00:00+00:00",
        "abc",
    )
    receivers.write([row], service.RESULTS / "receivers.csv")
    bench = app.receivers_benchmark()
    assert bench["rows"][0]["composite"] == 0.95
    assert bench["rows"][0]["epsilon"] is None
    assert bench["measured_at"] == "2026-11-07T15:00:00+00:00"


def test_a_partial_benchmark_keeps_the_other_rows(tmp_path: Path) -> None:
    path = tmp_path / "receivers.csv"
    base = ["d", "r", "public", "rows", "generated", None, None, None, 1, None, "unscored", "", "t", "c"]
    receivers.write([receivers.ReceiverResult("A-S1", *base), receivers.ReceiverResult("B-S1", *base)], path)  # type: ignore[arg-type]
    receivers.write([receivers.ReceiverResult("B-S1", *base[:10], "failed", "x", "t", "c")], path)  # type: ignore[arg-type]
    rows = {r["id"]: r["status"] for r in receivers.read(path)}
    assert rows == {"A-S1": "unscored", "B-S1": "failed"}


def test_status_follows_the_combined_score() -> None:
    assert receivers.status_of(0.7, scored=True) == "ready"
    assert receivers.status_of(0.69, scored=True) == "needs tuning"
    assert receivers.status_of(None, scored=False) == "unscored"


def test_the_demo_finds_the_newest_app_release(tmp_path: Path) -> None:
    for name, scenario, created in (
        ("a", "HEALTH-S1", "2026-11-01"),
        ("b", "HEALTH-S1", "2026-11-05"),
        ("c", "X", "2026-11-09"),
    ):
        rel = tmp_path / name / "release"
        rel.mkdir(parents=True)
        (rel / "manifest.json").write_text(json.dumps({"created_at": created, "plan": {"scenario_id": scenario}}))
    found = screens.latest_app_release(tmp_path)
    assert found == (tmp_path / "b" / "release", tmp_path / "b" / "private")
    assert screens.latest_app_release(tmp_path, "NOPE") is None
