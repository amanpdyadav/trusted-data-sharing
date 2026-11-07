"""Apply an approved plan to a data source and write a release (the Transform and Release steps).

    out/<name>/release/   protected tables + manifest.json   -> may be handed to the receiver
    out/<name>/private/   rowmap_<table>.csv                 -> never leaves the controller (scoring, audits)

Safety rules enforced here: the plan must be approved; every column needs an explicit decision (an unplanned
column is an error, never a silent release); row order is shuffled with the secret key so it cannot reveal
arrival order; row maps never go into the release folder.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from pets_transformer import __version__
from pets_transformer.aggregate import EpsilonLedger, bound_contributions, noisy_table
from pets_transformer.assess.kanon import KAnonymityResult
from pets_transformer.columns import NamedSource
from pets_transformer.contracts import (
    LlmUsage,
    Metrics,
    MetricSource,
    Plan,
    ReleasedFile,
    ReleaseManifest,
    RiskComponent,
    Technique,
)
from pets_transformer.keys import KeyScope
from pets_transformer.report.fingerprint import file_sha256, tables_fingerprint
from pets_transformer.sources import TableSource
from pets_transformer.transform import TRANSFORMS, TransformContext
from pets_transformer.transform.redact import known_from_tables
from pets_transformer.transform.suppress import SuppressionResult, suppress_to_k


class PlanError(ValueError):
    """The plan cannot be applied as written (not approved, undecided columns, unknown technique ...)."""


@dataclass(frozen=True)
class OutputLayout:
    root: Path

    @property
    def release(self) -> Path:
        return self.root / "release"

    @property
    def private(self) -> Path:
        return self.root / "private"


@dataclass(frozen=True)
class ProtectedTable:
    name: str
    frame: pd.DataFrame
    record_ids: list[str] | None
    rows_in: int
    suppression: SuppressionResult | None = None


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RunSettings:
    clock: Callable[[], datetime] = _utc_now  # injectable for reproducible tests
    ledger: EpsilonLedger | None = None  # where differential-privacy spending is recorded (and capped)


DEFAULT_SETTINGS = RunSettings()


def release_id(plan: Plan, created: datetime) -> str:
    """One id per release: the receiver's scenario and the second it was made."""
    return f"{plan.scenario_id}-{created.strftime('%Y%m%dT%H%M%SZ')}"


@dataclass(frozen=True)
class PublishedAggregate:
    name: str
    frame: pd.DataFrame


@dataclass(frozen=True)
class RunOutcome:
    layout: OutputLayout
    manifest: ReleaseManifest
    tables: list[ProtectedTable] = field(default_factory=list)
    aggregates: list[PublishedAggregate] = field(default_factory=list)
    epsilon_total: float | None = None  # running total for this receiver, from the ledger


def transform_rows(
    table: str, frame: pd.DataFrame, plan: Plan, scope: KeyScope, tables: Mapping[str, pd.DataFrame] | None = None
) -> pd.DataFrame:
    """Apply each column's decision (drop, keep or a technique) to these rows; no k check, no shuffle."""
    undecided = [c for c in frame.columns if plan.action_for(table, c) is None]
    if undecided:
        raise PlanError(f"{table}: no decision for columns {undecided}; every column needs keep, drop or a technique")
    ctx = TransformContext(keys=scope.keys, key_domain=scope.domain, source=frame, tables=tables or {})
    out: dict[str, pd.Series] = {}
    for column in frame.columns:
        action = plan.action_for(table, column)
        assert action is not None  # checked above
        if action.technique is Technique.DROP:
            continue
        name = str(action.params.get("rename_to", column))
        if name in out:
            raise PlanError(f"{table}: two released columns would be called {name!r}")
        if action.technique is Technique.KEEP:
            out[name] = frame[column]
        elif action.technique in TRANSFORMS:
            out[name] = TRANSFORMS.get(action.technique).apply(frame[column], action.params, ctx)
        else:
            raise PlanError(f"{table}.{column}: technique {action.technique.value!r} is not implemented yet")
    return pd.DataFrame(out, index=frame.index)


def protect_table(
    table: str, frame: pd.DataFrame, plan: Plan, scope: KeyScope, tables: Mapping[str, pd.DataFrame] | None = None
) -> ProtectedTable:
    protected = transform_rows(table, frame, plan, scope, tables)
    suppression = None
    if qis := plan.quasi_identifiers.get(table):
        missing = [q for q in qis if q not in protected.columns]
        if missing:
            raise PlanError(f"{table}: quasi-identifiers {missing} are not released columns")
        suppression = suppress_to_k(protected, qis, plan.k_target)
        protected = suppression.frame

    order = np.random.default_rng(scope.seed(f"shuffle/{table}")).permutation(len(protected))
    protected = protected.iloc[order]
    key_col = plan.record_keys.get(table)
    record_ids = frame.loc[protected.index, key_col].astype(str).tolist() if key_col else None
    return ProtectedTable(table, protected.reset_index(drop=True), record_ids, len(frame), suppression)


def publish_aggregates(plan: Plan, inputs: Mapping[str, pd.DataFrame], scope: KeyScope) -> list[PublishedAggregate]:
    """Noisy statistics tables. Rows are bounded per person once per table, then each table gets its own noise."""
    dp = plan.differential_privacy
    if not plan.aggregates or dp is None:
        return []
    bounded: dict[str, pd.DataFrame] = {}
    out = []
    for a in plan.aggregates:
        frame = inputs[a.table]
        measured = [a.measure.column] if a.measure.column else []
        needed = {dp.unit, *(d.column for d in a.dimensions), *measured, *a.exclude}
        missing = sorted(needed - set(frame.columns))
        if missing:
            raise PlanError(f"aggregate {a.name}: {a.table} has no columns {missing}")
        if a.table not in bounded:
            rng = np.random.default_rng(scope.seed(f"dp-bound/{a.table}"))
            bounded[a.table] = bound_contributions(frame, dp.unit, dp.max_rows_per_unit, rng)
        rows = bounded[a.table]
        ctx = TransformContext(keys=scope.keys, key_domain=scope.domain, source=rows, tables=inputs)
        noise = np.random.default_rng(scope.seed(f"dp/{a.name}"))
        out.append(PublishedAggregate(a.name, noisy_table(rows, a, dp, ctx, noise)))
    return out


def _dp_statement(plan: Plan, total: float | None) -> list[str]:
    dp = plan.differential_privacy
    if not plan.aggregates or dp is None:
        return []
    so_far = f"; {total:g} in total for this receiver so far (epsilon ledger)" if total is not None else ""
    observed = [f"{a.name}.{d.output_name}" for a in plan.aggregates for d in a.dimensions if d.domain is None]
    lines = [
        f"Differential privacy: discrete Laplace noise, epsilon {plan.epsilon_spent:g} for this release{so_far}, "
        f"delta 0, unit of privacy: one person ({dp.unit}), at most {dp.max_rows_per_unit} rows per person. "
        "Tables compose sequentially: " + ", ".join(f"{a.name} {a.epsilon:g}" for a in plan.aggregates) + ".",
        "Rows above the per-person bound are left out at random, so counts of frequent visitors are slightly low.",
        "Releases add up: each new release spends more budget for the people in it; differencing two releases "
        "reveals nothing beyond their combined epsilon.",
    ]
    if observed:
        lines.append(f"Categories taken from the data rather than declared in the plan: {', '.join(observed)}.")
    return lines


def _our_metrics(plan: Plan, tables: list[ProtectedTable], run_id: str, created: datetime) -> Metrics:
    checks: list[tuple[str, KAnonymityResult]] = [
        (t.name, t.suppression.check) for t in tables if t.suppression and t.suppression.check
    ]
    worst = max(checks, key=lambda c: c[1].share_below_k, default=None)
    return Metrics(
        run_id=run_id,
        dataset=plan.dataset,
        scenario_id=plan.scenario_id,
        created_at=created,
        k_min=worst[1].k_min if worst else None,
        share_below_k=worst[1].share_below_k if worst else None,
        risks=[
            RiskComponent(
                name=f"{name}: rows in groups below k={c.k_target}", value=c.share_below_k, source=MetricSource.OURS
            )
            for name, c in checks
        ],
        notes="Our own checks at release time. Run the evaluation harness for attack replay and usefulness.",
    )


def _residual_risks(plan: Plan, tables: list[ProtectedTable], withheld: list[str]) -> list[str]:
    risks = (
        ["Pseudonymised data is still personal data (GDPR Recital 26): share only under the scenario's agreement."]
        if tables
        else []
    )
    for t in tables:
        if t.suppression and t.suppression.check:
            c = t.suppression.check
            others = len(t.frame.columns) - len(c.quasi_identifiers)
            risks.append(
                f"{t.name}: every row shares {', '.join(c.quasi_identifiers)} with at least {c.k_target - 1} others; "
                f"the other {others} released columns were not part of this check and can still narrow candidates."
            )
            blanked = sum(t.suppression.cells_blanked.values())
            risks.append(
                f"{t.name}: {blanked} values blanked and {t.suppression.rows_removed} rows removed to reach k."
            )
    redacted = [f"{a.table}.{a.column}" for a in plan.actions if a.technique is Technique.REDACT_TEXT]
    if redacted:
        risks.append(
            f"Redacted free text ({', '.join(redacted)}): rule-based tags; unusual names, spellings or indirect "
            'descriptions ("my neighbour the mayor") can remain. Sample it before release.'
        )
    if withheld:
        risks.append(f"Withheld tables (not released): {', '.join(withheld)}.")
    return risks


def _llm_usage(plan: Plan) -> LlmUsage | None:
    """The local AI's only part in a release: names it suggested for unnamed columns, each confirmed by a person."""
    by_ai = [c for c in plan.column_names if c.suggested_by == "ai"]
    if not by_ai:
        return None
    model = next((c.model for c in by_ai if c.model), "local model")
    return LlmUsage(model=model, used_for=[f"suggested names for {len(by_ai)} unnamed columns, confirmed by a person"])


def run_release(
    source: TableSource,
    plan: Plan,
    scope: KeyScope,
    layout: OutputLayout,
    settings: RunSettings = DEFAULT_SETTINGS,
) -> RunOutcome:
    if not plan.approved:
        raise PlanError("the plan is not approved; a person must approve it before anything is released")
    created = settings.clock()
    ledger = settings.ledger
    if plan.column_names:  # columns that had no name are read under the names a person confirmed
        source = NamedSource(source, plan.column_names)
    available = source.table_names()
    lookups = {t for a in plan.actions for t in known_from_tables(a.params)} | {a.table for a in plan.aggregates}
    reads = [*plan.tables, *sorted(lookups - set(plan.tables))]  # lookups are read, never released as rows
    unknown = [t for t in reads if t not in available]
    if unknown:
        raise PlanError(f"plan names tables the source does not have: {unknown}")
    clash = {a.name for a in plan.aggregates} & set(plan.tables)
    if clash:
        raise PlanError(f"aggregates and released tables share names: {sorted(clash)}")

    inputs = {t: source.read(t) for t in reads}
    protected = [protect_table(t, inputs[t], plan, scope, inputs) for t in plan.tables]
    aggregates = publish_aggregates(plan, inputs, scope)
    run_id = release_id(plan, created)
    total = (
        ledger.record(run_id, scope.domain, plan.epsilon_spent, created)
        if ledger is not None and plan.aggregates
        else None
    )  # recorded before anything is written: a refused release leaves no files

    layout.release.mkdir(parents=True, exist_ok=True)
    layout.private.mkdir(parents=True, exist_ok=True)
    files: list[ReleasedFile] = []
    for t in protected:
        path = layout.release / f"{t.name}.csv"
        t.frame.to_csv(path, index=False)
        files.append(ReleasedFile(name=path.name, sha256=file_sha256(path), rows=len(t.frame)))
        if t.record_ids is not None:
            pd.DataFrame({"protected_row": range(len(t.frame)), "original_record_id": t.record_ids}).to_csv(
                layout.private / f"rowmap_{t.name}.csv", index=False
            )
    for agg in aggregates:
        path = layout.release / f"{agg.name}.csv"
        agg.frame.to_csv(path, index=False)
        files.append(ReleasedFile(name=path.name, sha256=file_sha256(path), rows=len(agg.frame)))

    withheld = [t for t in available if t not in plan.tables]
    manifest = ReleaseManifest(
        release_id=run_id,
        created_at=created,
        tool_version=__version__,
        input_fingerprint=tables_fingerprint(inputs),
        key_domain=scope.domain,
        plan=plan,
        metrics=_our_metrics(plan, protected, run_id, created),
        files=files,
        residual_risks=_dp_statement(plan, total) + _residual_risks(plan, protected, withheld),
        limitations=["Quasi-identifiers are those named in the plan; detection of further ones is not automated yet."],
        llm=_llm_usage(plan),
    )
    manifest.save(layout.release / "manifest.json")
    return RunOutcome(layout, manifest, protected, aggregates, total)
