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


def _stay(width: int | None, top: int = 1440) -> Callable[[Plan], Plan]:
    if width is None:
        action = ColumnAction(table="ed_visits", column="los_minutes", technique=Technique.KEEP,
                              reason="Length of stay by triage (H-U2).")  # fmt: skip
    else:
        action = ColumnAction(
            table="ed_visits",
            column="los_minutes",
            technique=Technique.GENERALISE,
            params={"to": "number_band", "width": width, "top": top},
            reason=f"Length of stay in {width}-minute bands, {top // 60} hours or more as '{top}+': keeps the median "
            "by triage (H-U2); a post that states how long someone stayed no longer points at one visit.",
        )
    return lambda p: with_action(p, action)


def _drop_sex(p: Plan) -> Plan:
    action = ColumnAction(table="ed_visits", column="sex", technique=Technique.DROP,
                          reason="Not in the research data request; first names in posts reveal it.")  # fmt: skip
    qis = {t: [c for c in cols if c != "sex"] for t, cols in p.quasi_identifiers.items()}
    return with_quasi_identifiers(with_action(p, action), "ed_visits", qis.get("ed_visits", []))


TOP8 = ["Turku", "Salo", "Kaarina", "Raisio", "Lieto", "Naantali", "Uusikaupunki", "Loimaa"]


def _top_towns(p: Plan) -> Plan:
    action = ColumnAction(
        table="ed_visits",
        column="municipality",
        technique=Technique.GENERALISE,
        params={"to": "keep_values", "keep": TOP8, "other": "other"},
        reason="The diagnosis-mix analysis (H-U4) covers the eight largest municipalities; "
        "small towns single people out.",
    )
    return with_action(p, action)


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
    "stay-length": (
        Variant("exact", "length of stay in minutes, as released today", _stay(None)),
        Variant("band-30", "30-minute bands, e.g. 180-209, 1440+ for a day or more", _stay(30)),
        Variant("band-60", "60-minute bands, e.g. 180-239, 1440+", _stay(60)),
        Variant("band-60-top-12h", "60-minute bands, 12 hours or more as 720+", _stay(60, 720)),
        Variant("band-30-top-12h-no-sex", "30-minute bands, 720+, sex dropped", _then(_stay(30, 720), _drop_sex)),
        Variant("band-60-top-12h-no-sex", "60-minute bands, 720+, sex dropped", _then(_stay(60, 720), _drop_sex)),
        Variant(
            "band-30-top-12h-no-sex-top8",
            "30-minute bands, 720+, sex dropped, 8 largest towns kept",
            _then(_stay(30, 720), _drop_sex, _top_towns),
        ),
        Variant("top8-only", "exact stay and sex kept; 8 largest towns kept", _top_towns),
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
