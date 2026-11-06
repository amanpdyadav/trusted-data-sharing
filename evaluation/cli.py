"""Evaluation command line.

    python -m evaluation validate --release out/health/release --rowmaps out/health/private --scenario HEALTH-S1
    python -m evaluation baseline          # score the package's quickstart output: our measured 'before'
    python -m evaluation detect --detection out/health/detection.json

Each run writes results/runs/<run_id>/ (scorecard + metrics.json, not committed) and appends results/history.csv.
`--gate` makes the command fail when a pass mark in evaluation/targets.yaml is missed (for CI or make).
"""

import argparse
import subprocess
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from evaluation import detection
from evaluation.attack_cases import DEMO_CASES
from evaluation.attacks import ReplayResult, replay
from evaluation.history import append_history, history_row
from evaluation.scorecard import Run, rowmaps_in, run_pets_eval, to_metrics
from evaluation.targets import Gate, detection_gates, load_targets, release_gates
from pets_transformer.config import Settings
from pets_transformer.contracts import DetectionReport
from pets_transformer.envfile import load_env_file
from pets_transformer.io import read_table

RESULTS = Path("results")


def _git_commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return out.stdout.strip()


def _print_gates(gates: Sequence[Gate]) -> bool:
    width = max(len(g.name) for g in gates)
    for g in gates:
        print(f"  {g.status:4}  {g.name:<{width}}  {g.value:<34} target {g.target}")
    return all(g.passed is not False for g in gates)


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


def cmd_validate(args: argparse.Namespace) -> int:
    release = Path(args.release)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = Run(
        run_id=run_id,
        dataset=args.dataset,
        scenario_id=args.scenario,
        package_root=Settings.from_env().package_root,
        release=release,
        rowmap_dir=Path(args.rowmaps) if args.rowmaps else release,
        out_dir=RESULTS / "runs" / run_id,
    )
    pairs = demo_replays(run)
    metrics = to_metrics(run_pets_eval(run), run, pairs)
    metrics.save(run.out_dir / "metrics.json")
    gates = release_gates(metrics, [after for _, after in pairs], load_targets(run.scenario_id))
    append_history(RESULTS / "history.csv", history_row(metrics, gates, _git_commit()))

    print(f"run {run_id} · {run.dataset} · {run.scenario_id}")
    print(f"  privacy {metrics.privacy} · utility {metrics.utility} · combined {metrics.composite}")
    for before, after in pairs:
        print(f"  demo attack {after.case_id}: {before.candidates_left} before -> {after.candidates_left} after")
    ok = _print_gates(gates)
    print(f"  details: {run.out_dir}/scorecard.html · history: {RESULTS / 'history.csv'}")
    return 0 if ok or not args.gate else 1


def cmd_baseline(args: argparse.Namespace) -> int:
    quickstart = Settings.from_env().package_root / "results" / "quickstart" / "health"
    if not (quickstart / "ed_visits.csv").exists():
        print("quickstart output missing: run `python examples/quickstart.py` in the data package", file=sys.stderr)
        return 1
    args.release, args.rowmaps, args.dataset, args.scenario = str(quickstart), str(quickstart), "health", "HEALTH-S1"
    args.run_id = args.run_id or "quickstart-baseline"
    return cmd_validate(args)


def cmd_detect(args: argparse.Namespace) -> int:
    report = DetectionReport.load(args.detection)
    scores = detection.score(report, Settings.from_env().package_root)
    print(f"detection · {report.dataset} · {scores['n_predicted']}/{scores['n_fields']} columns labelled")
    ok = _print_gates(detection_gates(scores, load_targets()))
    return 0 if ok or not args.gate else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m evaluation", description="Measure a release against our targets.")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("validate", help="score a protected release")
    v.add_argument("--release", required=True, help="folder with the protected tables")
    v.add_argument("--rowmaps", help="private folder with rowmap_*.csv (default: the release folder)")
    v.add_argument("--dataset", default="health")
    v.add_argument("--scenario", default="HEALTH-S1")
    v.set_defaults(func=cmd_validate)

    b = sub.add_parser("baseline", help="score the package quickstart output as our 'before'")
    b.set_defaults(func=cmd_baseline)

    d = sub.add_parser("detect", help="score a detection.json")
    d.add_argument("--detection", required=True)
    d.set_defaults(func=cmd_detect)

    for sp in (v, b, d):
        sp.add_argument("--gate", action="store_true", help="exit 1 if a pass mark is missed")
    for sp in (v, b):
        sp.add_argument("--run-id")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_env_file()
    try:
        code: int = args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return code
