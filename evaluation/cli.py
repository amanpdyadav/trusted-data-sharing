"""Evaluation command line. Parses arguments and prints; the work happens in runner.py and experiments.py.

    python -m evaluation validate --release out/health/release --rowmaps out/health/private --scenario HEALTH-S1
    python -m evaluation baseline          # score the package's quickstart output: our measured 'before'
    python -m evaluation detect --detection out/health/detection.json
    python -m evaluation experiment arrival-time    # compare plan variants side by side

Each run writes results/runs/<run_id>/ (scorecard + metrics.json, not committed) and appends results/history.csv.
`--gate` makes the command fail when a pass mark in evaluation/targets.yaml is missed (for CI or make).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from evaluation import detection
from evaluation.experiments import EXPERIMENTS, run_experiment
from evaluation.runner import RESULTS, Scored, score_run
from evaluation.scorecard import Run
from evaluation.targets import Gate, detection_gates, load_targets
from pets_transformer.config import Settings
from pets_transformer.contracts import DetectionReport, Plan
from pets_transformer.envfile import load_env_file
from pets_transformer.keys import DerivedKeyProvider, KeyScope


def _print_gates(gates: Sequence[Gate]) -> bool:
    width = max(len(g.name) for g in gates)
    for g in gates:
        print(f"  {g.status:4}  {g.name:<{width}}  {g.value:<34} target {g.target}")
    return all(g.passed is not False for g in gates)


def _print_scored(s: Scored) -> None:
    m = s.metrics
    print(f"run {m.run_id} · {m.dataset} · {m.scenario_id}")
    print(f"  privacy {m.privacy} · utility {m.utility} · combined {m.composite}")
    for before, after in s.replays:
        print(f"  demo attack {after.case_id}: {before.candidates_left} before -> {after.candidates_left} after")
    _print_gates(s.gates)
    print(f"  details: {s.run.out_dir}/scorecard.html · history: {RESULTS / 'history.csv'}")


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
    scored = score_run(run)
    _print_scored(scored)
    return 0 if scored.passed or not args.gate else 1


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


def _task(s: Scored, task_id: str) -> str:
    score = next((u.score for u in s.metrics.utility_tasks if u.task_id == task_id), None)
    return "n/a" if score is None else f"{score:.2f}"


def cmd_experiment(args: argparse.Namespace) -> int:
    base = Plan.load(args.plan)
    scope = KeyScope(DerivedKeyProvider.from_env(), f"{base.scenario_id}/experiment/{base.created_at:%Y-%m}")
    results = run_experiment(args.name, base, scope, Settings.from_env().package_root)
    print(f"experiment {args.name} · base plan {args.plan}")
    cols = f"{'combined':>8} {'utility':>7} {'H-U8':>5} {'k<5':>6} {'blanked':>8} {'demo attacks':>14}"
    print(f"  {'variant':<12} {cols}  passed")
    for r in results:
        m = r.scored.metrics
        blanked = sum(sum(t.suppression.cells_blanked.values()) for t in r.outcome.tables if t.suppression)
        attacks = "/".join(str(after.candidates_left) for _, after in r.scored.replays)
        passed = sum(1 for g in r.scored.gates if g.passed)
        print(
            f"  {r.variant.name:<12} {m.composite or 0:>8.3f} {m.utility or 0:>7.3f} {_task(r.scored, 'H-U8'):>5} "
            f"{m.share_below_k or 0:>6.3f} {blanked:>8} {attacks:>14}  {passed}/{len(r.scored.gates)}"
        )
    print("  (demo attacks = candidates left for POST00635/NEWS00100; >= 5 means defeated)")
    return 0


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

    e = sub.add_parser("experiment", help="release and score plan variants side by side")
    e.add_argument("name", choices=sorted(EXPERIMENTS))
    e.add_argument("--plan", default="plans/health-s1.yaml", help="base plan the variants change")
    e.set_defaults(func=cmd_experiment)

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
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return code
