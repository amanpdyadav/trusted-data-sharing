from pathlib import Path

import pytest

from evaluation.experiments import EXPERIMENTS, with_action
from pets_transformer.contracts import ColumnAction, Plan, Technique

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def base() -> Plan:
    return Plan.load(ROOT / "plans" / "health-s1.yaml")


def test_with_action_replaces_one_decision_and_keeps_everything_else(base: Plan) -> None:
    new = ColumnAction(table="ed_visits", column="sex", technique=Technique.DROP, reason="experiment")
    changed = with_action(base, new)
    assert changed.action_for("ed_visits", "sex") == new
    assert len(changed.actions) == len(base.actions)
    assert (changed.approved, changed.approved_by) == (base.approved, base.approved_by)
    assert base.action_for("ed_visits", "sex").technique is Technique.KEEP  # original untouched


def test_with_action_refuses_columns_not_in_the_plan(base: Plan) -> None:
    ghost = ColumnAction(table="ed_visits", column="ghost", technique=Technique.DROP, reason="experiment")
    with pytest.raises(KeyError, match="not in the plan"):
        with_action(base, ghost)


@pytest.mark.parametrize("variant", EXPERIMENTS["arrival-time"], ids=lambda v: v.name)
def test_arrival_variants_only_change_arrival_time(base: Plan, variant: object) -> None:
    changed = variant.change(base)  # type: ignore[attr-defined]
    action = changed.action_for("ed_visits", "arrival_ts")
    assert action.params == {"to": "time", "unit": variant.name}  # type: ignore[attr-defined]
    others = [a for a in changed.actions if a.column != "arrival_ts"]
    assert others == [a for a in base.actions if a.column != "arrival_ts"]


@pytest.mark.parametrize("variant", EXPERIMENTS["suppression-order"], ids=lambda v: v.name)
def test_suppression_order_variants_reorder_the_same_four_columns(base: Plan, variant: object) -> None:
    changed = variant.change(base)  # type: ignore[attr-defined]
    assert sorted(changed.quasi_identifiers["ed_visits"]) == sorted(base.quasi_identifiers["ed_visits"])
    assert changed.action_for("ed_visits", "arrival_ts").params["unit"] == "time_of_day"
    blanked_first = variant.name.removesuffix("-blanked-first")  # type: ignore[attr-defined]
    assert changed.quasi_identifiers["ed_visits"][-1] == {"hour": "arrival_ts"}.get(blanked_first, blanked_first)
