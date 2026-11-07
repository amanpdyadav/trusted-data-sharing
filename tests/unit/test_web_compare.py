"""Comparing receivers: one made for other data is left out with its reason, never breaking the comparison."""

from dataclasses import replace
from pathlib import Path

import pandas as pd
import yaml

from pets_transformer.config import Settings
from pets_transformer.web.service import App
from pets_transformer.web.workspace import Workspace

REPO = Path(__file__).resolve().parents[2]


def test_receivers_for_other_data_are_left_out(tmp_path: Path) -> None:
    folder = tmp_path / "upload"
    folder.mkdir()
    pd.DataFrame({"person_id": [f"P{i}" for i in range(30)], "zone": ["A", "B", "C"] * 10}).to_csv(
        folder / "footfall_15min.csv", index=False
    )
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    city = yaml.safe_load((REPO / "scenarios" / "CITY-S1.yaml").read_text(encoding="utf-8"))
    (scenarios / "CITY-S1.yaml").write_text(
        yaml.safe_dump(city), encoding="utf-8"
    )  # its table is here, its columns not
    (scenarios / "HEALTH-S1.yaml").write_text((REPO / "scenarios" / "HEALTH-S1.yaml").read_text(encoding="utf-8"))
    settings = replace(Settings.from_env({}), out_dir=tmp_path / "out", scenario_dirs=(scenarios,))
    app = App(settings, Workspace(tmp_path / "out" / "web"))
    s = app.workspace.from_folder("footfall", folder)
    app.scan(s)

    result = app.compare(s, ["CITY-S1", "HEALTH-S1", "NOT-A-RECEIVER"])

    assert result["receivers"] == []
    reasons = {x["id"]: x["reason"] for x in result["left_out"]}
    assert set(reasons) == {"CITY-S1", "HEALTH-S1"}
    assert "made for the health data; needs ed_visits, lab_results" in reasons["HEALTH-S1"]
    assert "sensor_id" in reasons["CITY-S1"] or "device_count" in reasons["CITY-S1"]
