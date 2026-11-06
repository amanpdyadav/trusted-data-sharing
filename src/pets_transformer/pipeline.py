"""Apply an approved plan to a data source and write a release (the Transform and Release steps).

    out/<name>/release/   protected tables + manifest.json   -> may be handed to the receiver
    out/<name>/private/   rowmap_<table>.csv                 -> never leaves the controller (scoring, audits)

Safety rules enforced here: the plan must be approved; every column needs an explicit decision (an unplanned
column is an error, never a silent release); row order is shuffled with the secret key so it cannot reveal
arrival order; row maps never go into the release folder.
"""

import hashlib
import hmac
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from pets_transformer import __version__
from pets_transformer.assess.kanon import KAnonymityResult
from pets_transformer.contracts import (
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


@dataclass(frozen=True)
class RunOutcome:
    layout: OutputLayout
    manifest: ReleaseManifest
    tables: list[ProtectedTable] = field(default_factory=list)


def _shuffle_seed(scope: KeyScope, table: str) -> int:
    digest = hmac.new(scope.key(), f"shuffle/{table}".encode(), hashlib.sha256).digest()
    return int.from_bytes(digest[:8], "big")


def protect_table(
    table: str, frame: pd.DataFrame, plan: Plan, scope: KeyScope, tables: Mapping[str, pd.DataFrame] | None = None
) -> ProtectedTable:
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
    protected = pd.DataFrame(out, index=frame.index)

    suppression = None
    if qis := plan.quasi_identifiers.get(table):
        missing = [q for q in qis if q not in protected.columns]
        if missing:
            raise PlanError(f"{table}: quasi-identifiers {missing} are not released columns")
        suppression = suppress_to_k(protected, qis, plan.k_target)
        protected = suppression.frame

    order = np.random.default_rng(_shuffle_seed(scope, table)).permutation(len(protected))
    protected = protected.iloc[order]
    key_col = plan.record_keys.get(table)
    record_ids = frame.loc[protected.index, key_col].astype(str).tolist() if key_col else None
    return ProtectedTable(table, protected.reset_index(drop=True), record_ids, len(frame), suppression)


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
    risks = ["Pseudonymised data is still personal data (GDPR Recital 26): share only under the scenario's agreement."]
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


def run_release(
    source: TableSource,
    plan: Plan,
    scope: KeyScope,
    layout: OutputLayout,
    clock: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> RunOutcome:
    if not plan.approved:
        raise PlanError("the plan is not approved; a person must approve it before anything is released")
    created = clock()
    available = source.table_names()
    lookups = sorted({t for a in plan.actions for t in known_from_tables(a.params)} - set(plan.tables))
    unknown = [t for t in [*plan.tables, *lookups] if t not in available]
    if unknown:
        raise PlanError(f"plan names tables the source does not have: {unknown}")

    inputs = {t: source.read(t) for t in [*plan.tables, *lookups]}  # lookups are read, never released
    protected = [protect_table(t, inputs[t], plan, scope, inputs) for t in plan.tables]

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

    run_id = f"{plan.scenario_id}-{created.strftime('%Y%m%dT%H%M%SZ')}"
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
        residual_risks=_residual_risks(plan, protected, withheld),
        limitations=["Quasi-identifiers are those named in the plan; detection of further ones is not automated yet."],
    )
    manifest.save(layout.release / "manifest.json")
    return RunOutcome(layout, manifest, protected)
