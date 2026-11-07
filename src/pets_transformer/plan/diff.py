"""What changed between two plans, in plain words: per column, the protection level, statistics and approval.

Used to show the history of a plan and to compare any two versions before choosing one to release with.
"""

from dataclasses import dataclass

from pets_transformer.contracts import ColumnAction, Plan, Technique

PLAIN = {
    Technique.KEEP: "shared as is", Technique.DROP: "removed", Technique.PSEUDONYMISE: "replaced by a code",
    Technique.GENERALISE: "made less exact", Technique.REDACT_TEXT: "personal details hidden",
}  # fmt: skip


@dataclass(frozen=True)
class Change:
    what: str  # "ed_visits.date_of_birth", "protection level", "approval", ...
    before: str
    after: str


def describe(action: ColumnAction | None) -> str:
    """One column's protection in plain words, with its detail (for example the age band or time unit)."""
    if action is None:
        return "not in the plan"
    text = PLAIN.get(action.technique, action.technique.value)
    if action.technique is Technique.GENERALISE:
        to = action.params.get("to")
        detail = (
            action.params.get("unit")
            if to == "time"
            else f"first {action.params.get('length')} characters"
            if to == "truncate"
            else to
        )
        text += f" ({str(detail).replace('_', ' ')})"
    return text


def plan_changes(old: Plan, new: Plan) -> list[Change]:
    """Every difference that matters to a reviewer, oldest value first."""
    changes = []
    if old.scenario_id != new.scenario_id:
        changes.append(Change("receiver", old.scenario_id, new.scenario_id))
    columns = dict.fromkeys([(a.table, a.column) for a in old.actions] + [(a.table, a.column) for a in new.actions])
    for table, column in columns:
        a, b = old.action_for(table, column), new.action_for(table, column)
        if (a and (a.technique, a.params)) != (b and (b.technique, b.params)):
            changes.append(Change(f"{table}.{column}", describe(a), describe(b)))
    if old.quasi_identifiers and new.quasi_identifiers and old.k_target != new.k_target:
        changes.append(
            Change("protection level", f"each person among at least {old.k_target}", f"at least {new.k_target}")
        )
    stats_old, stats_new = {g.name: g for g in old.aggregates}, {g.name: g for g in new.aggregates}
    for name in dict.fromkeys([*stats_old, *stats_new]):
        x, y = stats_old.get(name), stats_new.get(name)
        if x is None or y is None:
            changes.append(
                Change(
                    f"statistics table {name}",
                    "published" if x else "not published",
                    "published" if y else "not published",
                )
            )
        elif x.epsilon != y.epsilon:
            changes.append(Change(f"statistics table {name}", f"budget ε {x.epsilon:g}", f"budget ε {y.epsilon:g}"))
    if (old.approved, old.approved_by) != (new.approved, new.approved_by):
        changes.append(Change("approval", f"approved by {old.approved_by}" if old.approved else "not approved",
                              f"approved by {new.approved_by}" if new.approved else "not approved"))  # fmt: skip
    return changes
