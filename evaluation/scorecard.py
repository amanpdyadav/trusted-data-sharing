"""Run the organisers' scorer on a release and turn its report into our metrics.json (one mapping, one place)."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pets_eval.scorecard import run_scorecard

from evaluation.attacks import ReplayResult
from pets_transformer.contracts import AttackResult, Metrics, MetricSource, RiskComponent, UtilityTaskScore

Report = dict[str, Any]


@dataclass(frozen=True)
class Run:
    """Everything that identifies one evaluation run."""

    run_id: str
    dataset: str
    scenario_id: str
    package_root: Path
    release: Path
    rowmap_dir: Path | None
    out_dir: Path

    @property
    def original(self) -> Path:
        return self.package_root / "data" / self.dataset


def rowmaps_in(folder: Path | None) -> dict[str, Path]:
    """Table -> row-map path. Row maps live in a private folder, never in the release (production rule 7)."""
    if folder is None or not folder.is_dir():
        return {}
    return {p.stem.removeprefix("rowmap_"): p for p in sorted(folder.glob("rowmap_*.csv"))}


def run_pets_eval(run: Run) -> Report:
    report: Report = run_scorecard(
        run.original,
        run.release,
        scenario=run.scenario_id,
        root=run.package_root,
        rowmaps=rowmaps_in(run.rowmap_dir),
        out_dir=run.out_dir,
    )
    return report


def _worst_k(tables: Mapping[str, Any]) -> tuple[int | None, float | None]:
    worst: tuple[int | None, float | None] = (None, None)
    for t in tables.values():
        k = t.get("k_anonymity") or {}
        share = (k.get("share_below") or {}).get("k<5")
        if share is not None and (worst[1] is None or share > worst[1]):
            worst = (k.get("min_k"), float(share))
    return worst


def _linkage_attacks(tables: Mapping[str, Any]) -> list[AttackResult]:
    out: list[AttackResult] = []
    for name, t in tables.items():
        for adversary, res in (t.get("linkage") or {}).items():
            if not isinstance(res, dict) or not res.get("evaluated"):
                continue
            before = res.get("baseline_reidentification_rate_original")
            if before is None:
                continue
            out.append(
                AttackResult(
                    name=f"{name}: {adversary}",
                    unit="share_reidentified",
                    before=float(before),
                    after=float(res["reidentification_rate"]),
                    source=MetricSource.PETS_EVAL,
                )
            )
    return out


def to_metrics(
    report: Report,
    run: Run,
    replays: Sequence[tuple[ReplayResult, ReplayResult]] = (),
    created_at: datetime | None = None,
) -> Metrics:
    """`replays` are (before, after) pairs of our own attack replay on the original and the release."""
    summary = report.get("summary") or {}
    tables = report.get("tables") or {}
    k_min, share_below = _worst_k(tables)
    ours = [
        AttackResult(
            name=f"demo chain {after.case_id}",
            unit="candidates_left",
            before=before.candidates_left,
            after=after.candidates_left,
            source=MetricSource.OURS,
        )
        for before, after in replays
    ]
    return Metrics(
        run_id=run.run_id,
        dataset=run.dataset,
        scenario_id=run.scenario_id,
        created_at=created_at or datetime.now(UTC),
        privacy=summary.get("privacy"),
        utility=summary.get("utility"),
        composite=summary.get("composite"),
        k_min=k_min,
        share_below_k=share_below,
        risks=[
            RiskComponent(name=n, value=float(v), source=MetricSource.PETS_EVAL)
            for n, v in (report.get("risk_components") or {}).items()
            if v is not None
        ],
        attacks=_linkage_attacks(tables) + ours,
        utility_tasks=[
            UtilityTaskScore(task_id=u["id"], description=u["description"], score=u.get("score"))
            for u in report.get("utility") or []
        ],
        notes="pets-eval scorecard (practice data) plus our demo-attack replay.",
    )
