from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from pets_transformer.contracts import ColumnAction, Plan, ReleaseManifest, Technique
from pets_transformer.keys import DerivedKeyProvider, KeyScope
from pets_transformer.pipeline import OutputLayout, PlanError, run_release
from pets_transformer.sources import open_source
from tests.conftest import TEST_MASTER_KEY

KEYS = DerivedKeyProvider(TEST_MASTER_KEY)
NOW = datetime(2026, 11, 7, 9, 0, tzinfo=UTC)
N = 12


@pytest.fixture
def source(tmp_path: Path) -> object:
    folder = tmp_path / "data"
    folder.mkdir()
    pd.DataFrame(
        {
            "visit_id": [f"V{i:03d}" for i in range(N)],
            "hetu": [f"0101{i:02d}-900A" for i in range(N)],
            "name": [f"Person {i}" for i in range(N)],
            "born": ["1964-05-20"] * 6 + ["1990-01-01"] * 5 + ["1930-01-01"],
            "sex": ["F"] * 6 + ["M"] * 6,
            "arrived": ["2025-01-22 20:08:00"] * N,
            "icd": ["S52.5"] * N,
        }
    ).to_csv(folder / "visits.csv", index=False)
    pd.DataFrame({"note": ["secret"]}).to_csv(folder / "notes.csv", index=False)
    return open_source(f"csv:{folder}")


def _plan(**kw: object) -> Plan:
    A = ColumnAction  # noqa: N806
    actions = [
        A(table="visits", column="visit_id", technique=Technique.PSEUDONYMISE, reason="join key"),
        A(
            table="visits",
            column="hetu",
            technique=Technique.PSEUDONYMISE,
            params={"rename_to": "patient"},
            reason="revisits",
        ),
        A(table="visits", column="name", technique=Technique.DROP, reason="not needed"),
        A(
            table="visits",
            column="born",
            technique=Technique.GENERALISE,
            params={"to": "age_band", "reference_column": "arrived", "rename_to": "age"},
            reason="age groups suffice",
        ),
        A(table="visits", column="sex", technique=Technique.KEEP, reason="analysis by sex"),
        A(
            table="visits",
            column="arrived",
            technique=Technique.GENERALISE,
            params={"to": "time", "unit": "week"},
            reason="weekly load",
        ),
        A(
            table="visits",
            column="icd",
            technique=Technique.GENERALISE,
            params={"to": "truncate", "length": 3},
            reason="3-char codes",
        ),
    ]
    base: dict[str, object] = {
        "dataset": "toy",
        "scenario_id": "TOY-S1",
        "created_at": NOW,
        "quasi_identifiers": {"visits": ["sex", "age", "arrived"]},
        "record_keys": {"visits": "visit_id"},
        "actions": actions,
        "approved": True,
        "approved_by": "Aman Yadav",
    }
    return Plan.model_validate(base | kw)


def _run(source: object, tmp_path: Path, plan: Plan | None = None, domain: str = "TOY-S1/uni/2026-11") -> object:
    return run_release(
        source, plan or _plan(), KeyScope(KEYS, domain), OutputLayout(tmp_path / "out"), clock=lambda: NOW
    )  # type: ignore[arg-type]


def test_release_and_private_folders_are_separate(source: object, tmp_path: Path) -> None:
    _run(source, tmp_path)
    release = sorted(p.name for p in (tmp_path / "out/release").iterdir())
    private = sorted(p.name for p in (tmp_path / "out/private").iterdir())
    assert release == ["manifest.json", "visits.csv"]  # notes table withheld, no row maps here
    assert private == ["rowmap_visits.csv"]


def test_released_table_contains_only_protected_values(source: object, tmp_path: Path) -> None:
    _run(source, tmp_path)
    out = pd.read_csv(tmp_path / "out/release/visits.csv", dtype=str, keep_default_na=False)
    assert list(out.columns) == ["visit_id", "patient", "age", "sex", "arrived", "icd"]
    text = out.to_csv()
    assert "Person" not in text
    assert "900A" not in text
    assert "V000" not in text
    assert set(out["arrived"]) <= {"2025-W04", ""}
    assert set(out["icd"]) == {"S52"}


def test_k_is_reached_and_reported(source: object, tmp_path: Path) -> None:
    outcome = _run(source, tmp_path)
    t = outcome.tables[0]  # type: ignore[attr-defined]
    assert t.suppression.check.passes
    assert t.suppression.rows_removed == 1  # the one 90+ man can never join a group of 5
    assert len(t.frame) == N - 1


def test_row_map_points_each_released_row_at_its_original(source: object, tmp_path: Path) -> None:
    _run(source, tmp_path)
    original = source.read("visits").set_index("visit_id")  # type: ignore[attr-defined]
    out = pd.read_csv(tmp_path / "out/release/visits.csv", dtype=str, keep_default_na=False)
    rm = pd.read_csv(tmp_path / "out/private/rowmap_visits.csv", dtype=str)
    assert rm["protected_row"].tolist() == [str(i) for i in range(len(out))]
    for row, orig_id in zip(out.itertuples(), rm["original_record_id"], strict=True):
        assert row.sex == original.loc[orig_id, "sex"]


def test_manifest_is_valid_and_fingerprints_the_files(source: object, tmp_path: Path) -> None:
    _run(source, tmp_path)
    m = ReleaseManifest.load(tmp_path / "out/release/manifest.json")
    assert [f.name for f in m.files] == ["visits.csv"]
    assert m.metrics.share_below_k == 0.0
    assert any("Withheld tables" in r and "notes" in r for r in m.residual_risks)
    assert m.key_domain == "TOY-S1/uni/2026-11"


def test_same_key_same_output_other_receiver_other_order(source: object, tmp_path: Path) -> None:
    _run(source, tmp_path / "a")
    _run(source, tmp_path / "b")
    _run(source, tmp_path / "c", domain="TOY-S1/other-receiver/2026-11")
    a, b, c = ((tmp_path / x / "out/release/visits.csv").read_text() for x in "abc")
    assert a == b
    assert a != c


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"approved": False, "approved_by": None}, "not approved"),
        ({"quasi_identifiers": {"visits": ["postcode"]}}, "not released columns"),
    ],
)
def test_plan_problems_are_refused(source: object, tmp_path: Path, change: dict[str, object], message: str) -> None:
    with pytest.raises(PlanError, match=message):
        _run(source, tmp_path, _plan(**change))
    assert not (tmp_path / "out/release/visits.csv").exists()


def test_undecided_column_is_never_released(source: object, tmp_path: Path) -> None:
    plan = _plan()
    plan = plan.model_copy(update={"actions": [a for a in plan.actions if a.column != "name"]})
    with pytest.raises(PlanError, match=r"no decision for columns \['name'\]"):
        _run(source, tmp_path, plan)


def test_unimplemented_technique_and_unknown_table(source: object, tmp_path: Path) -> None:
    plan = _plan()
    synth = [
        a if a.column != "name" else a.model_copy(update={"technique": Technique.SYNTHESISE}) for a in plan.actions
    ]
    with pytest.raises(PlanError, match="not implemented"):
        _run(source, tmp_path, plan.model_copy(update={"actions": synth}))
    ghost = [*plan.actions, ColumnAction(table="ghost", column="x", technique=Technique.KEEP, reason="test")]
    with pytest.raises(PlanError, match="does not have"):
        _run(source, tmp_path, plan.model_copy(update={"actions": ghost}))


def test_free_text_is_redacted_with_names_from_a_table_that_is_not_released(tmp_path: Path) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    pd.DataFrame({"full_name": ["Hilkka Aalto"]}).to_csv(folder / "customers.csv", index=False)
    notes = ["Hilkka soitti numerosta 040 123 4567, kiitos.", "Lasku maksettu."]
    pd.DataFrame({"note": notes}).to_csv(folder / "notes.csv", index=False)
    action = ColumnAction(
        table="notes",
        column="note",
        technique=Technique.REDACT_TEXT,
        params={"known_from": ["customers.full_name"]},
        reason="meaning kept, people removed",
    )
    plan = Plan(dataset="toy", scenario_id="TOY-S1", created_at=NOW, actions=[action], approved=True, approved_by="t")
    outcome = _run(open_source(f"csv:{folder}"), tmp_path, plan)
    released = sorted(pd.read_csv(outcome.layout.release / "notes.csv", dtype=str)["note"])  # type: ignore[attr-defined]
    assert released == ["Lasku maksettu.", "[PERSON] soitti numerosta [PHONE], kiitos."]
    assert not (outcome.layout.release / "customers.csv").exists()  # type: ignore[attr-defined]
