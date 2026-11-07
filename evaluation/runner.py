"""Score one release and record it: shared by `validate`, `baseline` and experiments (one path, one result)."""

import subprocess
from dataclasses import dataclass
from pathlib import Path

from evaluation.attack_cases import DEMO_CASES
from evaluation.attacks import ReplayResult, replay
from evaluation.history import append_history, ensure_new_run_id, history_row
from evaluation.scorecard import Run, rowmaps_in, run_pets_eval, to_metrics
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


def _record_ids(run: Run, table: str, rows: int) -> list[str] | None:
    """Original id per release row, from the private row map; None when there is no usable map."""
    maps = rowmaps_in(run.rowmap_dir)
    if table not in maps:
        return None
    rm = read_table(maps[table]).astype({"protected_row": int}).sort_values("protected_row")
    return rm["original_record_id"].tolist() if len(rm) == rows else None


def demo_replays(run: Run) -> list[tuple[ReplayResult, ReplayResult]]:
    """Replay each demo attack on the original table (before) and on the release (after)."""
    pairs: list[tuple[ReplayResult, ReplayResult]] = []
    for case in DEMO_CASES:
        orig_path, rel_path = run.original / f"{case.table}.csv", run.release / f"{case.table}.csv"
        if not (orig_path.exists() and rel_path.exists()):
            continue
        orig, rel = read_table(orig_path), read_table(rel_path)
        before = replay(case, orig, orig["visit_id"].tolist())
        after = replay(case, rel, _record_ids(run, case.table, len(rel)))
        pairs.append((before, after))
    return pairs


def scrap_sweep(run: Run) -> SweepResult | None:
    """All public posts and news clips replayed on the release (health ED visits only)."""
    rel_path = run.release / "ed_visits.csv"
    if run.dataset != "health" or not rel_path.exists():
        return None
    rel = read_table(rel_path)
    return sweep(run.package_root, rel, _record_ids(run, "ed_visits", len(rel)))


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
