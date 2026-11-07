"""Evaluation command line. Parses arguments and prints; the work happens in runner.py and experiments.py.

    python -m evaluation validate --release out/health/release --rowmaps out/health/private --scenario HEALTH-S1
    python -m evaluation baseline          # score the package's quickstart output: our measured 'before'
    python -m evaluation detect --detection out/health/detection.json
    python -m evaluation experiment arrival-time    # compare plan variants side by side
    python -m evaluation detect-all        # column detection on every dataset, held-out reported apart
    python -m evaluation text              # free-text redaction vs gold spans, quickstart regex as 'before'
    python -m evaluation redact-eval       # pets_submission/customer_service_eval_redacted.csv for the organisers
    python -m evaluation receivers         # plan, release and score every receiver: results/receivers.csv
    python -m evaluation baselines         # the organisers' B0/B2/B2-k per receiver: results/baselines.csv

Each run writes results/runs/<run_id>/ (scorecard + metrics.json, not committed) and appends results/history.csv.
`--gate` makes the command fail when a pass mark in evaluation/targets.yaml is missed (for CI or make).
"""

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from evaluation import dashboard, detection, text
from evaluation.experiments import EXPERIMENTS, run_experiment
from evaluation.runner import RESULTS, Scored, score_run
from evaluation.scorecard import Run, record_ids
from evaluation.targets import Gate, detection_gates, load_targets, text_gates
from pets_transformer.config import Settings
from pets_transformer.contracts import DetectionReport, Plan
from pets_transformer.envfile import load_env_file
from pets_transformer.io import read_table
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
    if s.sweep is not None:
        print(f"  post and news sweep: {s.sweep.summary()}")
    _print_gates(s.gates)
    print(f"  details: {s.run.out_dir}/scorecard.html · history: {RESULTS / 'history.csv'}")


def cmd_validate(args: argparse.Namespace) -> int:
    release = Path(args.release)
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    root = Settings.from_env().package_root
    out_dir = RESULTS / "runs" / run_id
    rowmaps: Path | None = Path(args.rowmaps) if args.rowmaps else release
    if dashboard.is_dashboard(release):
        release = dashboard.scoring_view(release, root, out_dir / "scoring")
        rowmaps = None
        print(f"published statistics: scored through {release} (built from the published tables only)")
    run = Run(
        run_id=run_id,
        dataset=args.dataset,
        scenario_id=args.scenario,
        package_root=root,
        release=release,
        rowmap_dir=rowmaps,
        out_dir=out_dir,
    )
    scored = score_run(run)
    _print_scored(scored)
    return 0 if scored.passed or not args.gate else 1


def cmd_sweep(args: argparse.Namespace) -> int:
    """Replay every public post and news clip on a release and list the scraps that still expose someone."""
    from evaluation.scrap_sweep import sweep  # noqa: PLC0415  (slow import of the package data, only when asked)

    release = Path(args.release)
    rel = read_table(release / "ed_visits.csv")
    ids = record_ids(Path(args.rowmaps or release), "ed_visits", len(rel))
    result = sweep(Settings.from_env().package_root, rel, ids, k=args.k)
    print(f"post and news sweep on {release}: {result.summary()}")
    for r in result.worst[: args.show]:
        print(f"  {r.case_id}: " + " -> ".join(f"{s.label} {s.candidates}" for s in r.funnel if s.applied))
    return 0 if result.exposed == 0 or not args.gate else 1


def cmd_screens(args: argparse.Namespace) -> int:
    """Score a release and write the data for the web app's Mosaic attack and Release audit screens."""
    from evaluation import screens  # noqa: PLC0415

    settings = Settings.from_env()
    root = settings.package_root
    if args.release:
        release, rowmaps = Path(args.release), Path(args.rowmaps or args.release)
    else:
        found = screens.latest_app_release(settings.out_dir / "web", args.scenario)
        if found is None:
            print(
                f"no {args.scenario} release in the web app yet: release one there, or pass --release", file=sys.stderr
            )
            return 1
        release, rowmaps = found
        print(f"using the newest {args.scenario} release made in the app: {release}")
    run_id = args.run_id or "screens-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run = Run(run_id=run_id, dataset="health", scenario_id=args.scenario, package_root=root, release=release,
              rowmap_dir=rowmaps, out_dir=RESULTS / "runs" / run_id)  # fmt: skip
    scored = score_run(run)
    _print_scored(scored)
    for name, data in (("audit", screens.audit(scored, Path(args.plan) if args.plan else None)),
                       ("mosaic", screens.mosaic(root, release, rowmaps))):  # fmt: skip
        print(f"  screen data: {screens.write(name, data)}")
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    """Write scenario files for the package's sharing scenarios (keeps hand-written HEALTH-S1/S2)."""
    from evaluation.scenarios_from_pack import write_all  # noqa: PLC0415

    written = write_all(Settings.from_env().package_root, Path(args.out), force=args.force)
    print(f"wrote {len(written)} scenario files to {args.out}" + ("" if written else " (all exist; --force rewrites)"))
    return 0


def cmd_receivers(args: argparse.Namespace) -> int:
    """Benchmark the automatic planner on every receiver (or --only some) and update results/receivers.csv."""
    from evaluation import receivers  # noqa: PLC0415
    from pets_transformer.plan.scenario import load_scenarios  # noqa: PLC0415

    settings = Settings.from_env()
    found = load_scenarios(settings.scenario_dirs)
    ids = args.only or sorted(found)
    unknown = [i for i in ids if i not in found]
    if unknown:
        print(f"unknown receivers: {unknown}", file=sys.stderr)
        return 1
    keys = DerivedKeyProvider.from_env()
    done = []
    for i in ids:
        r = receivers.benchmark(found[i], settings.package_root, lambda p: KeyScope(keys, f"benchmark/{p.scenario_id}"))
        scores = (
            f"privacy {r.privacy:.2f} · usefulness {r.utility:.2f} · combined {r.composite:.2f}"
            if r.composite is not None
            else ""
        )
        print(f"  {r.id:10} {r.status:13} {scores or r.why}", flush=True)
        done.append(r)
    print(f"wrote {receivers.write(done)}")
    return 0


def cmd_baselines(_: argparse.Namespace) -> int:
    """Write the organisers' reference baselines per receiver (from the pack's results/benchmark.json)."""
    from evaluation import baselines  # noqa: PLC0415

    found = baselines.rows(Settings.from_env().package_root)
    print(f"wrote {baselines.write(found)}: {len(found)} receivers with B0, B2 and B2-k")
    return 0


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


DEV_DATASETS = ["health", "mobility", "smart_city", "energy", "finance", "cyber", "public_admin", "customer_service"]
HELD_OUT = ["education"]  # never used to design rules; see the detector commit for its first-look score


def cmd_detect_all(_: argparse.Namespace) -> int:
    root = Settings.from_env().package_root
    for label, datasets in (("development", DEV_DATASETS), ("held out", HELD_OUT)):
        overall, per = detection.score_datasets(root, datasets)
        sens = overall["per_role"]["sensitive_attribute"]["recall"]
        print(
            f"{label}: macro-F1 {overall['macro_f1']:.3f} · accuracy {overall['accuracy']:.3f} · "
            f"sensitive-attribute recall {sens:.2f} · subtype accuracy {overall.get('subtype_accuracy')}"
        )
        for ds, f1 in per.items():
            print(f"  {ds:18s} {f1:.3f}")
    return 0


TEXT_SCORES = RESULTS / "text_redaction.csv"
EVAL_REDACTED = Path("pets_submission") / "customer_service_eval_redacted.csv"


def cmd_text(args: argparse.Namespace) -> int:
    scores = text.score_all(Settings.from_env().package_root)
    for s in scores:
        r = s.row()
        print(
            f"{r['split']:8s} {r['method']:10s} {r['column']:45s} values {r['gold_values']:6d}  "
            f"leakage {r['leakage']:.3f}  recall {r['recall']:.3f}  precision {r['precision']:.3f}"
        )
    summary = text.summary(scores)
    print(summary.to_string(index=False))
    text.write_scores(scores, TEXT_SCORES)
    print(f"written {TEXT_SCORES}")
    held = summary[(summary["split"] == "held-out") & (summary["method"] == "ours")].iloc[0]
    passed = _print_gates(text_gates(float(held["leakage"]), float(held["recall"]), load_targets()))
    return 0 if passed or not args.gate else 1


def cmd_redact_eval(_: argparse.Namespace) -> int:
    rows = text.redact_eval_split(Settings.from_env().package_root, EVAL_REDACTED)
    print(f"written {EVAL_REDACTED} ({rows} turns)")
    return 0


def _task(s: Scored, task_id: str) -> str:
    score = next((u.score for u in s.metrics.utility_tasks if u.task_id == task_id), None)
    return "n/a" if score is None else f"{score:.2f}"


def cmd_experiment(args: argparse.Namespace) -> int:
    base = Plan.load(args.plan)
    scope = KeyScope(DerivedKeyProvider.from_env(), f"{base.scenario_id}/experiment/{base.created_at:%Y-%m}")
    results = run_experiment(args.name, base, scope, Settings.from_env().package_root)
    print(f"experiment {args.name} · base plan {args.plan}")
    cols = f"{'combined':>8} {'utility':>7} {'H-U8':>5} {'k<5':>6} {'blanked':>8} {'demo attacks':>14}"
    width = max(len("variant"), *(len(r.variant.name) for r in results))
    print(f"  {'variant':<{width}} {cols}  passed")
    for r in results:
        m = r.scored.metrics
        blanked = sum(sum(t.suppression.cells_blanked.values()) for t in r.outcome.tables if t.suppression)
        attacks = "/".join(str(after.candidates_left) for _, after in r.scored.replays)
        passed = sum(1 for g in r.scored.gates if g.passed)
        print(
            f"  {r.variant.name:<{width}} {m.composite or 0:>8.3f} {m.utility or 0:>7.3f} {_task(r.scored, 'H-U8'):>5} "
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

    sc = sub.add_parser("screens", help="score a release and write the web app's mosaic and audit screen data")
    sc.add_argument("--release", help="release folder (default: the newest release of --scenario made in the web app)")
    sc.add_argument("--rowmaps")
    sc.add_argument("--plan", help="the plan YAML used for the release (shown as decisions)")
    sc.add_argument("--scenario", default="HEALTH-S1")
    sc.add_argument("--run-id")
    sc.set_defaults(func=cmd_screens)

    scn = sub.add_parser("scenarios", help="write scenario files for the package's 27 sharing scenarios")
    scn.add_argument("--out", default="scenarios")
    scn.add_argument("--force", action="store_true", help="rewrite generated files that already exist")
    scn.set_defaults(func=cmd_scenarios)

    rc = sub.add_parser("receivers", help="plan, release and score every receiver (results/receivers.csv)")
    rc.add_argument("--only", nargs="+", help="receiver IDs to measure (default: all)")
    rc.set_defaults(func=cmd_receivers)

    bl = sub.add_parser("baselines", help="the organisers' B0/B2/B2-k per receiver (results/baselines.csv)")
    bl.set_defaults(func=cmd_baselines)

    sw = sub.add_parser("sweep", help="replay every public post and news clip on a release (health)")
    sw.add_argument("--release", required=True)
    sw.add_argument("--rowmaps", help="folder with rowmap_ed_visits.csv (default: the release folder)")
    sw.add_argument("--k", type=int, default=5)
    sw.add_argument("--show", type=int, default=5, help="list this many exposing scraps")
    sw.add_argument("--gate", action="store_true", help="exit 1 if any scrap exposes someone")
    sw.set_defaults(func=cmd_sweep)

    d = sub.add_parser("detect", help="score a detection.json")
    d.add_argument("--detection", required=True)
    d.set_defaults(func=cmd_detect)

    da = sub.add_parser("detect-all", help="detect and score every dataset (development and held-out)")
    da.set_defaults(func=cmd_detect_all)

    t = sub.add_parser("text", help="score free-text redaction against the gold spans (dev and held-out)")
    t.set_defaults(func=cmd_text)

    r = sub.add_parser("redact-eval", help="redact the customer_service eval split for the organisers' check")
    r.set_defaults(func=cmd_redact_eval)

    e = sub.add_parser("experiment", help="release and score plan variants side by side")
    e.add_argument("name", choices=sorted(EXPERIMENTS))
    e.add_argument("--plan", default="plans/health-s1.yaml", help="base plan the variants change")
    e.set_defaults(func=cmd_experiment)

    for sp in (v, b, d, t):
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
