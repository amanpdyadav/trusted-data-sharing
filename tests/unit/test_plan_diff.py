"""Plan versions compared in plain words."""

from pets_transformer.contracts import Plan
from pets_transformer.plan.diff import plan_changes


def _plan(dob: dict[str, object], k: int = 5, approved_by: str | None = None) -> Plan:
    return Plan.model_validate({
        "scenario_id": "T", "dataset": "toy", "created_at": "2026-11-07T00:00:00Z", "k_target": k,
        "quasi_identifiers": {"visits": ["age"]}, "approved": approved_by is not None, "approved_by": approved_by,
        "actions": [
            {"table": "visits", "column": "name", "technique": "drop", "params": {}, "reason": "identifies a person"},
            {"table": "visits", "column": "date_of_birth", "reason": "test", **dob},
        ],
    })  # fmt: skip


def test_changes_are_described_in_plain_words() -> None:
    old = _plan({"technique": "keep", "params": {}})
    new = _plan(
        {"technique": "generalise", "params": {"to": "age_band", "rename_to": "age"}}, k=10, approved_by="Maria"
    )
    changes = {c.what: (c.before, c.after) for c in plan_changes(old, new)}
    assert changes == {
        "visits.date_of_birth": ("shared as is", "made less exact (age band)"),
        "protection level": ("each person among at least 5", "at least 10"),
        "approval": ("not approved", "approved by Maria"),
    }


def test_identical_plans_have_no_changes() -> None:
    assert plan_changes(_plan({"technique": "keep", "params": {}}), _plan({"technique": "keep", "params": {}})) == []
