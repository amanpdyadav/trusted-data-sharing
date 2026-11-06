"""Compare plan variants on the same data, the same key and the same scoring.

A variant is a named change to the base plan, applied in code (no copied plan files). Every variant is released,
scored and recorded in results/history.csv like any other run, so the comparison is reproducible.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from evaluation.runner import RESULTS, Scored, score_run
from evaluation.scorecard import Run
from pets_transformer.contracts import ColumnAction, Plan, Technique
from pets_transformer.keys import KeyScope
from pets_transformer.pipeline import OutputLayout, RunOutcome, run_release
from pets_transformer.sources import open_source


@dataclass(frozen=True)
class Variant:
    name: str
    description: str
    change: Callable[[Plan], Plan]


def with_action(plan: Plan, action: ColumnAction) -> Plan:
    """A copy of the plan with one column's decision replaced. The column must already be in the plan."""
    if plan.action_for(action.table, action.column) is None:
        raise KeyError(f"{action.table}.{action.column} is not in the plan")
    actions = [action if (a.table, a.column) == (action.table, action.column) else a for a in plan.actions]
    return plan.model_copy(update={"actions": actions})


def with_quasi_identifiers(plan: Plan, table: str, columns: list[str]) -> Plan:
    """A copy of the plan with a new k check for one table (most important first; blanking starts at the end)."""
    return plan.model_copy(update={"quasi_identifiers": {**plan.quasi_identifiers, table: columns}})


def _then(*changes: Callable[[Plan], Plan]) -> Callable[[Plan], Plan]:
    def apply(plan: Plan) -> Plan:
        for change in changes:
            plan = change(plan)
        return plan

    return apply


def _arrival(unit: str, reason: str) -> Callable[[Plan], Plan]:
    action = ColumnAction(
        table="ed_visits",
        column="arrival_ts",
        technique=Technique.GENERALISE,
        params={"to": "time", "unit": unit},
        reason=reason,
    )
    return lambda p: with_action(p, action)


EXPERIMENTS: dict[str, tuple[Variant, ...]] = {
    "arrival-time": (
        Variant("week", "ISO week, e.g. 2025-W04", _arrival("week", "Weekly crowding patterns.")),
        Variant("hour", "Date and hour, e.g. 2025-01-22 20:00", _arrival("hour", "Hour-of-arrival with date.")),
        Variant(
            "time_of_day",
            "Hour of day only, e.g. 20:00 (no date)",
            _arrival("time_of_day", "Hour-of-arrival curve (H-U8) without the date that links to news and posts."),
        ),
    ),
    "suppression-order": tuple(
        Variant(
            name,
            f"time of day; k check order {order} (blanking starts at the end)",
            _then(
                _arrival("time_of_day", "Hour-of-arrival curve (H-U8) without the date."),
                lambda p, o=order: with_quasi_identifiers(p, "ed_visits", o),  # type: ignore[misc]
            ),
        )
        for name, order in (
            ("hour-blanked-first", ["municipality", "age", "sex", "arrival_ts"]),
            ("sex-blanked-first", ["arrival_ts", "municipality", "age", "sex"]),
            ("age-blanked-first", ["arrival_ts", "municipality", "sex", "age"]),
        )
    ),
}


@dataclass(frozen=True)
class VariantResult:
    variant: Variant
    outcome: RunOutcome
    scored: Scored


def run_experiment(  # noqa: PLR0913  (output paths are keyword-only, injectable for tests)
    name: str,
    base: Plan,
    scope: KeyScope,
    package_root: Path,
    *,
    results: Path = RESULTS,
    out_root: Path = Path("out"),
) -> list[VariantResult]:
    """Releases go under out/ (git-ignored: they contain private row maps); scores go to results/."""
    variants = EXPERIMENTS[name]
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    source = open_source(f"csv:{package_root / 'data' / base.dataset}")
    out: list[VariantResult] = []
    for v in variants:
        layout = OutputLayout(out_root / "experiments" / name / v.name)
        outcome = run_release(source, v.change(base), scope, layout)
        run_id = f"exp-{name}-{v.name}-{stamp}"
        run = Run(run_id, base.dataset, base.scenario_id, package_root, layout.release, layout.private,
                  results / "runs" / run_id)  # fmt: skip
        out.append(VariantResult(v, outcome, score_run(run, results)))
    return out
