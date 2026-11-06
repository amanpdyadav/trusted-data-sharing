"""The harness against the real challenge data. Checks it reproduces the numbers we measured by hand."""

import csv
from pathlib import Path

import pytest

from evaluation.attack_cases import DEMO_CASES
from evaluation.attacks import replay
from evaluation.cli import main
from pets_transformer.io import read_table

pytestmark = pytest.mark.integration

PKG = Path(__file__).resolve().parents[2] / "TRUSTED_PETS_PROVING_GROUND_2026"
QUICKSTART = PKG / "results" / "quickstart" / "health"


@pytest.fixture(scope="module")
def raw_visits() -> object:
    path = PKG / "data" / "health" / "ed_visits.csv"
    if not path.exists():
        pytest.skip("TrustED data package not found")
    return read_table(path)


@pytest.mark.parametrize("case", DEMO_CASES, ids=lambda c: c.id)
def test_demo_attacks_single_out_the_target_in_raw_data(raw_visits: object, case: object) -> None:
    r = replay(case, raw_visits, raw_visits["visit_id"].tolist())  # type: ignore[arg-type, index]
    assert (r.candidates_left, r.target_among_candidates) == (1, True)


def test_baseline_reproduces_the_measured_before(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    if not (QUICKSTART / "ed_visits.csv").exists():
        pytest.skip("quickstart output not found")
    monkeypatch.setenv("PETS_PACKAGE_ROOT", str(PKG))
    monkeypatch.chdir(tmp_path)  # results/ goes here, not into the repo
    assert main(["baseline", "--run-id", "test-baseline"]) == 0
    row = next(csv.DictReader((tmp_path / "results" / "history.csv").open()))
    assert (row["composite"], row["share_below_k"], row["fewest_demo_candidates"]) == ("0.4913", "0.9921", "1")
    assert row["gates_passed"] == "0"
    assert (tmp_path / "results" / "runs" / "test-baseline" / "metrics.json").exists()
    assert main(["baseline", "--run-id", "test-gated", "--gate"]) == 1  # 'before' must fail our pass marks
