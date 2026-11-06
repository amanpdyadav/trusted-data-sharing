import json
import os
from pathlib import Path

import pytest

from pets_transformer.cli import main

KEY = "test-only-master-key-0123456789abcdef"


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run in an empty folder with a private copy of the environment and no PETS_ variables.

    Keeps a developer's real .env and shell settings out of the tests, and the tests out of the shell.
    """
    env = {k: v for k, v in os.environ.items() if not k.startswith("PETS_")}
    monkeypatch.setattr(os, "environ", env)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _doctor(capsys: pytest.CaptureFixture[str], *flags: str) -> str:
    assert main([*flags, "doctor"]) == 0
    return capsys.readouterr().out


def test_schemas_are_written_for_every_shared_file(isolated: Path) -> None:
    assert main(["schemas", "--out", "schemas"]) == 0
    names = sorted(p.name for p in (isolated / "schemas").glob("*.schema.json"))
    assert names == [
        "detection.schema.json",
        "manifest.schema.json",
        "metrics.schema.json",
        "plan.schema.json",
        "scenario.schema.json",
        "spans.schema.json",
    ]
    assert json.loads((isolated / "schemas/plan.schema.json").read_text())["title"] == "Plan"


def test_validate_accepts_good_and_rejects_bad_files(repo: Path, isolated: Path) -> None:
    assert main(["validate", str(repo / "examples/contracts/plan.example.yaml"), "--kind", "plan"]) == 0
    (isolated / "bad.json").write_text('{"dataset": "x"}', encoding="utf-8")
    assert main(["validate", "bad.json", "--kind", "plan"]) == 1


def test_doctor_without_env_file_or_key(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    out = _doctor(capsys)
    assert "env file       : none" in out
    assert "master key     : MISSING" in out
    assert "add it to .env" in out
    assert "local AI       : off (rules only)" in out


def test_env_file_is_loaded_automatically(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (isolated / ".env").write_text(f"PETS_MASTER_KEY={KEY}\n", encoding="utf-8")
    out = _doctor(capsys)
    assert f"env file       : {(isolated / '.env').resolve()}" in out
    assert "master key     : set" in out


def test_env_file_is_found_from_a_subfolder(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (isolated / ".env").write_text(f"PETS_MASTER_KEY={KEY}\n", encoding="utf-8")
    sub = isolated / "ui" / "src"
    sub.mkdir(parents=True)
    os.chdir(sub)
    assert "master key     : set" in _doctor(capsys)


def test_shell_variables_win_over_env_file(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (isolated / ".env").write_text("PETS_LLM_ENABLED=true\nPETS_OUT_DIR=from-file\n", encoding="utf-8")
    os.environ["PETS_LLM_ENABLED"] = "false"
    out = _doctor(capsys)
    assert "local AI       : off" in out
    assert os.environ["PETS_LLM_ENABLED"] == "false"
    assert os.environ["PETS_OUT_DIR"] == "from-file"  # unset variables are still filled in


def test_explicit_env_file_and_opt_out(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (isolated / "team.env").write_text(f"PETS_MASTER_KEY={KEY}\n", encoding="utf-8")
    (isolated / ".env").write_text(f"PETS_MASTER_KEY={KEY}\n", encoding="utf-8")
    assert "master key     : MISSING" in _doctor(capsys, "--no-env-file")
    assert "master key     : set" in _doctor(capsys, "--env-file", "team.env")


def test_missing_explicit_env_file_is_an_error(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--env-file", "nope.env", "doctor"]) == 1
    assert "env file not found" in capsys.readouterr().err


def _toy_release_inputs(folder: Path) -> Path:
    data = folder / "data"
    data.mkdir()
    rows = 6
    (data / "people.csv").write_text(
        "id,name,sex\n" + "".join(f"P{i},Person {i},{'F' if i % 2 else 'M'}\n" for i in range(rows)), encoding="utf-8"
    )
    plan = folder / "plan.yaml"
    plan.write_text(
        "dataset: toy\nscenario_id: TOY-S1\ncreated_at: '2026-11-07T00:00:00Z'\n"
        "record_keys: {people: id}\napproved: true\napproved_by: Tester\nactions:\n"
        "  - {table: people, column: id, technique: pseudonymise, reason: join key}\n"
        "  - {table: people, column: name, technique: drop, reason: not needed}\n"
        "  - {table: people, column: sex, technique: keep, reason: analysis}\n",
        encoding="utf-8",
    )
    return plan


def test_run_writes_a_release_and_says_what_to_do_next(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = _toy_release_inputs(isolated)
    os.environ["PETS_MASTER_KEY"] = KEY
    args = ["run", "--plan", str(plan), "--receiver", "uni", "--out", "out", "--source", f"csv:{isolated / 'data'}"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "people: 6 rows in, 6 out, 2 columns" in out
    assert "next: make validate RELEASE=out/release ROWMAPS=out/private" in out
    assert (isolated / "out/release/people.csv").exists()
    assert (isolated / "out/private/rowmap_people.csv").exists()


def test_run_without_a_key_writes_nothing(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    plan = _toy_release_inputs(isolated)
    args = ["run", "--plan", str(plan), "--receiver", "uni", "--out", "out", "--source", f"csv:{isolated / 'data'}"]
    assert main(args) == 1
    assert "PETS_MASTER_KEY is not set" in capsys.readouterr().err
    assert not (isolated / "out").exists()


def test_detect_writes_report_and_organiser_labels(isolated: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _toy_release_inputs(isolated)
    args = ["detect", "--dataset", "toy", "--source", f"csv:{isolated / 'data'}", "--out", "det.json",
            "--labels-csv", "labels.csv"]  # fmt: skip
    assert main(args) == 0
    assert "detected 3 columns in 1 tables" in capsys.readouterr().out
    labels = (isolated / "labels.csv").read_text().splitlines()
    assert labels[0] == "column,privacy_role,subtype"
    assert "id,record_key,RECORD_ID" in labels
    assert main(["validate", "det.json", "--kind", "detection"]) == 0
