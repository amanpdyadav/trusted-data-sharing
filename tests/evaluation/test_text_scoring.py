"""Text redaction scoring on a tiny fake package, plus its pass marks."""

import json
from pathlib import Path

import pytest

from evaluation.targets import load_targets, text_gates
from evaluation.text import TextColumn, score_column, summary


@pytest.fixture
def package(tmp_path: Path) -> Path:
    (tmp_path / "data" / "toy").mkdir(parents=True)
    (tmp_path / "metadata" / "pii_spans").mkdir(parents=True)
    notes = [
        ("N1", "Soita Hilkka Aalto numeroon 040 123 4567."),
        ("N2", "Hetu 131052-308T kirjattu."),
        ("N3", "Ei henkilötietoja."),
    ]
    lines = ["note_id,note"] + [f"{i},{t}" for i, t in notes]
    (tmp_path / "data" / "toy" / "notes.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")
    gold = [
        {"record_id": "N1", "spans": [
            {"start": 6, "end": 18, "label": "PERSON", "text": "Hilkka Aalto"},
            {"start": 28, "end": 40, "label": "PHONE", "text": "040 123 4567"},
        ]},
        {"record_id": "N2", "spans": [{"start": 5, "end": 16, "label": "NATIONAL_ID", "text": "131052-308T"}]},
    ]  # fmt: skip
    path = tmp_path / "metadata" / "pii_spans" / "toy__notes__note.jsonl"
    path.write_text("\n".join(json.dumps(g) for g in gold) + "\n", encoding="utf-8")
    return tmp_path


def test_ours_beats_the_quickstart_regex(package: Path) -> None:
    before, after = score_column(package, TextColumn("toy", "notes", "note"), "dev", ["Hilkka Aalto"])
    assert (before.method, after.method) == ("quickstart", "ours")
    assert before.gold_values == after.gold_values == 3
    assert before.leakage == pytest.approx(1 / 3, abs=1e-3)  # the regex finds the phone and the HETU, not the name
    assert (after.leakage, after.recall, after.precision) == (0.0, 1.0, 1.0)


def test_summary_weights_columns_by_gold_values(package: Path) -> None:
    scores = score_column(package, TextColumn("toy", "notes", "note"), "held-out", [])
    table = summary(scores)
    assert list(table["method"]) == ["quickstart", "ours"]
    assert set(table["gold_values"]) == {3}


def test_gold_records_must_exist_in_the_table(package: Path) -> None:
    (package / "data" / "toy" / "notes.csv").write_text("note_id,note\nN9,x\n", encoding="utf-8")
    with pytest.raises(ValueError, match="gold records are not in note_id"):
        score_column(package, TextColumn("toy", "notes", "note"), "dev", [])


def test_text_gates() -> None:
    t = load_targets()
    assert all(g.passed for g in text_gates(0.01, 0.98, t))
    assert [g.passed for g in text_gates(0.20, 0.50, t)] == [False, False]
