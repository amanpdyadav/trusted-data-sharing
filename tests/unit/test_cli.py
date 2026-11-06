import json
from pathlib import Path

import pytest

from pets_transformer.cli import main


def test_schemas_are_written_for_every_shared_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schemas", "--out", str(tmp_path)]) == 0
    names = sorted(p.name for p in tmp_path.glob("*.schema.json"))
    assert names == [
        "detection.schema.json",
        "manifest.schema.json",
        "metrics.schema.json",
        "plan.schema.json",
        "scenario.schema.json",
        "spans.schema.json",
    ]
    assert json.loads((tmp_path / "plan.schema.json").read_text())["title"] == "Plan"


def test_validate_accepts_good_and_rejects_bad_files(repo: Path, tmp_path: Path) -> None:
    assert main(["validate", str(repo / "examples/contracts/plan.example.yaml"), "--kind", "plan"]) == 0
    bad = tmp_path / "bad.json"
    bad.write_text('{"dataset": "x"}', encoding="utf-8")
    assert main(["validate", str(bad), "--kind", "plan"]) == 1


def test_doctor_runs_with_local_ai_off(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PETS_LLM_ENABLED", "false")
    monkeypatch.delenv("PETS_MASTER_KEY", raising=False)
    assert main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "local AI       : off (rules only)" in out
    assert "master key     : MISSING" in out
