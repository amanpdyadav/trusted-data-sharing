"""Columns without a real name: which count, what the AI is sent, the name rules, and the names in the release."""

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from pets_transformer.columns import (
    BATCH,
    PROMPT_TOKENS,
    SAMPLE_CHARS,
    SAMPLES,
    NamedSource,
    NamingError,
    check_names,
    is_unnamed,
    looks_headerless,
    suggest,
)
from pets_transformer.config import Settings
from pets_transformer.contracts import ColumnAction, ColumnName, Plan, Technique
from pets_transformer.keys import DerivedKeyProvider, KeyScope
from pets_transformer.llm import DisabledLlm, LlmUnavailableError
from pets_transformer.pipeline import OutputLayout, RunSettings, run_release
from pets_transformer.sources import CsvFolderSource
from pets_transformer.web.service import App, NewName
from pets_transformer.web.workspace import Workspace, WorkspaceError
from tests.conftest import TEST_MASTER_KEY

HETUS = ["131052-308T", "010101A123N", "020202-1110", "290492-903T"]  # check digits valid


class FakeLlm:
    """Answers every prompt by naming each asked column `thing_<column>`; records what it was sent."""

    def __init__(self, fail: bool = False) -> None:
        self.prompts: list[str] = []
        self.fail = fail

    @property
    def available(self) -> bool:
        return True

    @property
    def model(self) -> str | None:
        return "fake:1b"

    def ask_json(self, prompt: str, schema: dict[str, Any]) -> dict[str, Any]:
        self.prompts.append(prompt)
        if self.fail:
            raise LlmUnavailableError("timed out")
        asked = json.loads(prompt.split("Columns to name: ", 1)[1].split("\n", 1)[0])
        return {
            "columns": [
                {"column": c["column"], "name": f"Thing {c['column']}", "meaning": "a thing", "confidence": 0.8}
                for c in asked
            ]
        }


def _frame(rows: int = 40) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "c01": [HETUS[i % 4] for i in range(rows)],
            "age": [str(20 + i % 50) for i in range(rows)],
            "c03": [f"note number {i} " + "x" * 200 for i in range(rows)],
            "Unnamed: 3": [f"A{i % 3}" for i in range(rows)],
            "c05": [""] * rows,
        }
    )


@pytest.mark.parametrize("header", ["c01", "C7", "col_12", "column3", "field-7", "V12", "x", "X", "Unnamed: 3", " "])
def test_generic_and_blank_headers_are_unnamed(header: str) -> None:
    assert is_unnamed(header)


@pytest.mark.parametrize("header", ["age", "sex", "id", "v2x_score", "icd10_primary", "email.1", "c01_total"])
def test_real_names_are_left_alone(header: str) -> None:
    assert not is_unnamed(header)


def test_a_first_row_of_data_is_spotted() -> None:
    assert looks_headerless(["R001996", "KC-4450", "2025-11/1", "Mäkinen Mika", "200278907W"])
    assert not looks_headerless(["visit_id", "icd10_primary", "age", "municipality"])


def test_rules_name_what_they_are_sure_of_and_the_ai_gets_only_the_rest() -> None:
    llm = FakeLlm()
    result = suggest(_frame(), "people", ["c01", "c03", "Unnamed: 3", "c05"], llm)
    by = {s.column: s for s in result.suggestions}
    assert (by["c01"].name, by["c01"].source) == ("national_id", "rules")
    assert (by["c05"].source, by["c05"].name) == ("rules", "empty_c05")
    assert (by["c03"].name, by["c03"].source) == ("thing_c03", "ai")  # snake_case enforced
    assert by["Unnamed: 3"].source == "ai"
    asked = json.loads(llm.prompts[0].split("Columns to name: ", 1)[1].split("\n", 1)[0])
    assert [c["column"] for c in asked] == ["c03", "Unnamed: 3"]  # not the rules' column, not the named one
    assert asked[0]["column_before"] == "age"  # named neighbours are context only
    assert result.ai_calls == 1


def test_the_ai_never_sees_the_table() -> None:
    llm = FakeLlm()
    frame = _frame(rows=20_000)
    suggest(frame, "people", ["c03"], llm)
    sent = json.loads(llm.prompts[0].split("Columns to name: ", 1)[1].split("\n", 1)[0])[0]
    assert len(sent["examples"]) <= SAMPLES
    assert all(len(v) <= SAMPLE_CHARS for v in sent["examples"])
    assert len(llm.prompts[0]) / 4 <= PROMPT_TOKENS


def test_many_columns_go_in_small_batches() -> None:
    llm = FakeLlm()
    cols = {f"c{i:02d}": [f"value {i} {j}" for j in range(30)] for i in range(1, 21)}
    suggest(pd.DataFrame(cols), "wide", list(cols), llm)
    assert len(llm.prompts) == -(-20 // BATCH)
    assert all(len(p) / 4 <= PROMPT_TOKENS for p in llm.prompts)


def test_no_ai_or_a_failing_ai_still_gives_the_rules_names() -> None:
    for llm in (DisabledLlm(), FakeLlm(fail=True)):
        result = suggest(_frame(), "people", ["c01", "c03"], llm)
        by = {s.column: s for s in result.suggestions}
        assert by["c01"].name == "national_id"
        assert by["c03"].source == "none"
        assert by["c03"].name == ""
        assert result.ai_error


def test_suggestions_are_never_for_a_named_column() -> None:
    with pytest.raises(NamingError, match="not an unnamed column"):
        suggest(_frame(), "people", ["age"], FakeLlm())


def test_duplicate_suggestions_get_a_number() -> None:
    frame = pd.DataFrame({"c01": HETUS * 5, "c02": HETUS[::-1] * 5, "national_id": ["x"] * 20})
    names = {s.column: s.name for s in suggest(frame, "t", ["c01", "c02"], DisabledLlm()).suggestions}
    assert names == {"c01": "national_id_2", "c02": "national_id_3"}


def _n(original: str, name: str) -> ColumnName:
    return ColumnName(table="t", original=original, name=name)


@pytest.mark.parametrize(
    ("names", "message"),
    [
        ([_n("age", "years")], "already has a name"),
        ([_n("c01", "age")], "already has a column"),
        ([_n("c01", "thing"), _n("c03", "thing")], "two columns"),
        ([_n("c01", "c9")], "not a descriptive name"),
        ([_n("c99", "thing")], "no column"),
    ],
)
def test_name_rules(names: list[ColumnName], message: str) -> None:
    with pytest.raises(NamingError, match=message):
        check_names(["c01", "age", "c03"], names)


def test_names_may_swap_between_unnamed_columns() -> None:
    check_names(["c01", "age", "c03"], [_n("c01", "national_id"), _n("c03", "notes")])


def test_named_source_renames_once(tmp_path: Path) -> None:
    _frame(5).to_csv(tmp_path / "t.csv", index=False)
    src = NamedSource(NamedSource(CsvFolderSource(tmp_path), [_n("c01", "national_id")]), [_n("c01", "national_id")])
    assert list(src.read("t").columns) == ["national_id", "age", "c03", "Unnamed: 3", "c05"]


def test_a_file_without_header_row_reads_as_col_01(tmp_path: Path) -> None:
    (tmp_path / "t.csv").write_text("R1,131052-308T,5\nR2,010101A123N,7\n", encoding="utf-8")
    frame = CsvFolderSource(tmp_path, frozenset({"t"})).read("t")
    assert list(frame.columns) == ["col_01", "col_02", "col_03"]
    assert len(frame) == 2


def test_the_release_uses_the_new_names_and_says_the_ai_helped(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    pd.DataFrame({"c01": [f"R{i}" for i in range(6)], "c02": ["F", "M"] * 3}).to_csv(data / "t.csv", index=False)
    plan = Plan(
        dataset="d", scenario_id="S", created_at=datetime(2026, 11, 7, tzinfo=UTC), approved=True, approved_by="Tester",
        column_names=[ColumnName(table="t", original="c02", name="sex", suggested_by="ai", model="fake:1b")],
        actions=[
            ColumnAction(table="t", column="c01", technique=Technique.DROP, reason="not needed"),
            ColumnAction(table="t", column="sex", technique=Technique.KEEP, reason="analysis"),
        ],
    )  # fmt: skip
    out = run_release(
        CsvFolderSource(data), plan, KeyScope(DerivedKeyProvider(TEST_MASTER_KEY), "S/r/2026-11"),
        OutputLayout(tmp_path / "out"), RunSettings(clock=lambda: datetime(2026, 11, 7, tzinfo=UTC)),
    )  # fmt: skip
    assert list(pd.read_csv(tmp_path / "out" / "release" / "t.csv").columns) == ["sex"]
    assert out.manifest.plan.column_names[0].original == "c02"
    assert out.manifest.llm is not None
    assert out.manifest.llm.model == "fake:1b"


# ---------------------------------------------------------------- the web app's steps
@pytest.fixture
def app(tmp_path: Path) -> tuple[App, Any]:
    folder = tmp_path / "upload"
    folder.mkdir()
    _frame().to_csv(folder / "people.csv", index=False)
    settings = replace(Settings.from_env({}), out_dir=tmp_path / "out")
    svc = App(settings, Workspace(tmp_path / "out" / "web"))
    return svc, svc.workspace.from_folder("people", folder)


def test_overview_lists_only_unnamed_columns(app: tuple[App, Any]) -> None:
    svc, s = app
    naming = svc.overview(s)["tables"][0]["naming"]
    assert [u["original"] for u in naming["unnamed"]] == ["c01", "c03", "Unnamed: 3", "c05"]
    assert svc.overview(s)["ai"] == {"on": False, "model": None}


def test_confirmed_names_flow_into_scan_and_plan(app: tuple[App, Any]) -> None:
    svc, s = app
    svc.scan(s)
    svc.set_names(s, "people", [NewName("c01", "national_id", "rules"), NewName("c03", "notes", "person")])
    assert s.detections is None  # the scan starts over with the new names
    assert svc.overview(s)["tables"][0]["columns"][:3] == ["national_id", "age", "notes"]
    svc.scan(s)
    assert s.detections is not None
    det = {c.column: c for c in s.detections.columns}
    assert det["national_id"].source_column == "c01"
    assert det["age"].source_column is None
    again = Workspace(s.root.parent).get(s.id)  # names survive a restart
    assert [c.name for c in again.column_names] == ["national_id", "notes"]


def test_a_named_column_cannot_be_renamed(app: tuple[App, Any]) -> None:
    svc, s = app
    with pytest.raises(WorkspaceError, match="already has a name"):
        svc.set_names(s, "people", [NewName("age", "years")])


def test_ai_off_is_reported_not_raised(app: tuple[App, Any]) -> None:
    svc, s = app
    result = svc.suggest_names(s, "people", None, None)
    assert result["ai_error"]
    assert {x["column"] for x in result["suggestions"]} == {"c01", "c03", "Unnamed: 3", "c05"}
