"""Regression guard on the real data: our HEALTH-S1 plan must keep defeating the demo attacks and reach k."""

import pytest

from evaluation.attack_cases import DEMO_CASES
from evaluation.attacks import replay
from evaluation.targets import attack_defeated, load_targets
from pets_transformer.contracts import Plan
from pets_transformer.keys import DerivedKeyProvider, KeyScope
from pets_transformer.pipeline import OutputLayout, run_release
from pets_transformer.sources import open_source
from tests.conftest import PACKAGE, REPO, TEST_MASTER_KEY

pytestmark = pytest.mark.integration

DATA = PACKAGE / "data" / "health"


@pytest.fixture(scope="module")
def outcome(tmp_path_factory: pytest.TempPathFactory) -> object:
    if not DATA.is_dir():
        pytest.skip("TrustED data package not found")
    plan = Plan.load(REPO / "plans" / "health-s1.yaml")
    plan = plan.model_copy(update={"approved": True, "approved_by": "regression test"})  # the plan file awaits sign-off
    scope = KeyScope(DerivedKeyProvider(TEST_MASTER_KEY), "HEALTH-S1/test/2026-11")
    return run_release(open_source(f"csv:{DATA}"), plan, scope, OutputLayout(tmp_path_factory.mktemp("rel")))


def test_k_is_met_without_dropping_rows(outcome: object) -> None:
    visits = next(t for t in outcome.tables if t.name == "ed_visits")  # type: ignore[attr-defined]
    assert visits.suppression.check.passes
    assert visits.suppression.rows_removed == 0


@pytest.mark.parametrize("case", DEMO_CASES, ids=lambda c: c.id)
def test_demo_attacks_are_defeated(outcome: object, case: object) -> None:
    visits = next(t for t in outcome.tables if t.name == case.table)  # type: ignore[attr-defined]
    result = replay(case, visits.frame, visits.record_ids)  # type: ignore[arg-type]
    assert attack_defeated(result, load_targets("HEALTH-S1").attack_candidates_min), result


def test_no_direct_identifier_column_is_released(outcome: object) -> None:
    released = {c for t in outcome.tables for c in t.frame.columns}  # type: ignore[attr-defined]
    assert not released & {"patient_name", "patient_hetu", "phone", "home_address", "postcode", "date_of_birth"}
