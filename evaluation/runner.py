"""Score one release and record it: shared by `validate`, `baseline` and experiments (one path, one result)."""

import csv
import subprocess
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evaluation.attack_cases import DEMO_CASES
from evaluation.attacks import ReplayResult, replay
from evaluation.history import append_history, ensure_new_run_id, history_row
from evaluation.scorecard import Run, record_ids, run_pets_eval, to_metrics
from evaluation.scrap_sweep import SweepResult, sweep
from evaluation.targets import Gate, load_targets, release_gates
from pets_transformer.contracts import Metrics
from pets_transformer.io import read_table

RESULTS = Path("results")


@dataclass(frozen=True)
class Scored:
    run: Run
    metrics: Metrics
    gates: list[Gate]
    replays: list[tuple[ReplayResult, ReplayResult]]
    sweep: SweepResult | None = None

    @property
    def passed(self) -> bool:
        return all(g.passed is not False for g in self.gates)


def git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def demo_replays(run: Run) -> list[tuple[ReplayResult, ReplayResult]]:
    """Replay each demo attack on the original table (before) and on the release (after)."""
    pairs: list[tuple[ReplayResult, ReplayResult]] = []
    for case in DEMO_CASES:
        orig_path, rel_path = run.original / f"{case.table}.csv", run.release / f"{case.table}.csv"
        if not (orig_path.exists() and rel_path.exists()):
            continue
        orig, rel = read_table(orig_path), read_table(rel_path)
        before = replay(case, orig, orig["visit_id"].tolist())
        after = replay(case, rel, record_ids(run.rowmap_dir, case.table, len(rel)))
        pairs.append((before, after))
    return pairs


def scrap_sweep(run: Run) -> SweepResult | None:
    """All public posts and news clips replayed on the release (health ED visits only)."""
    rel_path = run.release / "ed_visits.csv"
    if run.dataset != "health" or not rel_path.exists():
        return None
    rel = read_table(rel_path)
    return sweep(run.package_root, rel, record_ids(run.rowmap_dir, "ed_visits", len(rel)))


def score_run(run: Run, results: Path = RESULTS) -> Scored:
    history = results / "history.csv"
    ensure_new_run_id(history, run.run_id)  # fail before the slow scoring, not after
    pairs = demo_replays(run)
    metrics = to_metrics(run_pets_eval(run), run, pairs)
    metrics.save(run.out_dir / "metrics.json")
    swept = scrap_sweep(run)
    gates = release_gates(metrics, [after for _, after in pairs], load_targets(run.scenario_id), swept)
    append_history(history, history_row(metrics, gates, git_commit()))
    return Scored(run, metrics, gates, pairs, swept)


def write_csv(path: Path, fields: Sequence[str], rows: Iterable[Mapping[str, object]]) -> Path:
    """Write rows to a committed results file (LF line endings, header first)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    return path
