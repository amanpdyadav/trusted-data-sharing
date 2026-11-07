"""results/history.csv: one row per scored run, so the 'after' numbers line up over time for the video."""

import csv
from collections.abc import Sequence
from pathlib import Path

from evaluation.targets import Gate
from pets_transformer.contracts import Metrics

FIELDS = [
    "run_id", "created_at", "git_commit", "dataset", "scenario_id",
    "privacy", "utility", "composite", "share_below_k", "k_min",
    "worst_reidentification", "fewest_demo_candidates", "gates_passed", "gates_total",
]  # fmt: skip


def history_row(metrics: Metrics, gates: Sequence[Gate], git_commit: str) -> dict[str, object]:
    share = [a.after for a in metrics.attacks if a.unit == "share_reidentified" and a.after is not None]
    cands = [a.after for a in metrics.attacks if a.unit == "candidates_left" and a.after is not None]
    measured = [g for g in gates if g.passed is not None]
    return {
        "run_id": metrics.run_id,
        "created_at": metrics.created_at.isoformat(timespec="seconds"),
        "git_commit": git_commit,
        "dataset": metrics.dataset,
        "scenario_id": metrics.scenario_id,
        "privacy": metrics.privacy,
        "utility": metrics.utility,
        "composite": metrics.composite,
        "share_below_k": metrics.share_below_k,
        "k_min": metrics.k_min,
        "worst_reidentification": max(share) if share else None,
        "fewest_demo_candidates": int(min(cands)) if cands else None,
        "gates_passed": sum(1 for g in measured if g.passed),
        "gates_total": len(measured),
    }


def ensure_new_run_id(path: Path, run_id: str) -> None:
    """The history is a ledger keyed by run id; a repeated id would make the before/after record ambiguous."""
    if path.exists():
        with path.open(newline="", encoding="utf-8") as f:
            if any(r.get("run_id") == run_id for r in csv.DictReader(f)):
                raise ValueError(f"run id {run_id!r} is already in {path}; pass a new --run-id")


def append_history(path: Path, row: dict[str, object]) -> Path:
    ensure_new_run_id(path, str(row["run_id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        if new:
            w.writeheader()
        w.writerow({k: ("" if v is None else v) for k, v in row.items()})
    return path
