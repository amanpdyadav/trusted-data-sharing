"""Command line. Each sub-command is one small function; the pipeline commands arrive as the steps land.

pets-transformer doctor                       # is everything configured? (AI on/off, key, data, scenarios)
pets-transformer schemas --out schemas        # JSON schemas for the shared files (the UI reads these)
pets-transformer validate plan.yaml --kind plan
pets-transformer run --plan plans/health-s1.yaml --receiver uni-research --out out/health-s1
pets-transformer detect --dataset health --out out/health/detection.json
pets-transformer plan --detection out/health/detection.json --scenario HEALTH-S1 --out out/health/plan.yaml
pets-transformer approve out/health/plan.yaml --by "Your Name"
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from pets_transformer import __version__
from pets_transformer.aggregate import EpsilonLedger
from pets_transformer.config import Settings
from pets_transformer.contracts import CONTRACTS, Contract, DetectionReport, Plan, RecordSpans, Technique
from pets_transformer.detect.rules import detect_source
from pets_transformer.envfile import load_env_file
from pets_transformer.keys import DerivedKeyProvider, KeyScope, MissingKeyError
from pets_transformer.llm import LlmUnavailableError, build_llm
from pets_transformer.pipeline import OutputLayout, RunSettings, run_release
from pets_transformer.plan.policy import REVIEW, RulePolicy
from pets_transformer.plan.scenario import Scenario, load_scenarios
from pets_transformer.plan.statistics import load_codelists
from pets_transformer.plugins import load_plugins
from pets_transformer.sources import open_source

KINDS: dict[str, type[Contract]] = {**CONTRACTS, "scenario": Scenario}


def cmd_schemas(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {**KINDS, "spans": RecordSpans}
    for name, model in models.items():
        (out / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8"
        )
    print(f"wrote {len(models)} schemas to {out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    KINDS[args.kind].load(args.file)
    print(f"ok: {args.file} is a valid {args.kind} file")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    s = Settings.from_env()
    lines = [f"pets-transformer {__version__}"]
    env_file: Path | None = args.env_file_loaded
    lines.append(f"env file       : {env_file} (loaded; shell variables win)" if env_file else "env file       : none")
    lines.append(f"data package   : {s.package_root} ({'found' if s.package_root.is_dir() else 'NOT FOUND'})")
    try:
        DerivedKeyProvider.from_env()
        lines.append("master key     : set")
    except MissingKeyError as exc:
        lines.append(f"master key     : MISSING ({exc})")
    lines.append(f"scenarios      : {len(load_scenarios(s.scenario_dirs))} in {[str(d) for d in s.scenario_dirs]}")
    lines.append(f"plug-ins       : {load_plugins() or 'none'}")
    llm = build_llm(s.llm)
    if not llm.available:
        lines.append("local AI       : off (rules only)")
    else:
        try:
            llm.ask_json('Reply {"ok": true}', {"type": "object", "properties": {"ok": {"type": "boolean"}}})
            lines.append(f"local AI       : on, {llm.model} answering")
        except LlmUnavailableError as exc:
            lines.append(f"local AI       : on but not answering ({exc}); steps fall back to rules")
    print("\n".join(lines))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    plan = Plan.load(args.plan)
    settings = Settings.from_env()
    source = open_source(args.source or f"csv:{settings.package_root / 'data' / plan.dataset}")
    month = plan.created_at.strftime("%Y-%m")
    scope = KeyScope(DerivedKeyProvider.from_env(), f"{plan.scenario_id}/{args.receiver}/{month}")
    dp = plan.differential_privacy
    ledger = EpsilonLedger(settings.epsilon_ledger, dp.budget_cap if dp else None)
    outcome = run_release(source, plan, scope, OutputLayout(Path(args.out)), RunSettings(ledger=ledger))
    print(f"release {outcome.manifest.release_id} for receiver '{args.receiver}'")
    for t in outcome.tables:
        line = f"  {t.name}: {t.rows_in} rows in, {len(t.frame)} out, {len(t.frame.columns)} columns"
        if t.suppression and t.suppression.check:
            c = t.suppression.check
            line += f"; k>={c.k_target} {'met' if c.passes else 'NOT met'}, {t.suppression.rows_removed} rows removed"
        print(line)
    for agg in outcome.aggregates:
        print(f"  {agg.name}: {len(agg.frame)} cells (noisy statistics)")
    if outcome.epsilon_total is not None:
        print(f"  epsilon {plan.epsilon_spent:g} spent; {outcome.epsilon_total:g} in total for this receiver")
    print(f"  release: {outcome.layout.release}   private (never share): {outcome.layout.private}")
    print(f"  next: make validate RELEASE={outcome.layout.release} ROWMAPS={outcome.layout.private}")
    return 0


def cmd_detect(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    source = open_source(args.source or f"csv:{settings.package_root / 'data' / args.dataset}")
    report = detect_source(source, args.dataset)
    report.save(args.out)
    counts: dict[str, int] = {}
    for c in report.columns:
        counts[c.privacy_role.value] = counts.get(c.privacy_role.value, 0) + 1
    print(f"detected {len(report.columns)} columns in {len(source.table_names())} tables -> {args.out}")
    for role, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {role:22s} {n}")
    if args.labels_csv:
        rows = report.to_pets_eval_rows()
        Path(args.labels_csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows)[["column", "privacy_role", "subtype"]].to_csv(args.labels_csv, index=False)
        print(f"  labels (column,privacy_role,subtype): {args.labels_csv}")
    return 0


def _scenario(ref: str, settings: Settings) -> Scenario:
    """A scenario id from the configured folders, or a path to a YAML file."""
    if Path(ref).is_file():
        return Scenario.load(ref)
    found = load_scenarios(settings.scenario_dirs)
    if ref not in found:
        raise ValueError(f"unknown scenario {ref!r}; known: {sorted(found)}")
    return found[ref]


def cmd_plan(args: argparse.Namespace) -> int:
    detections = DetectionReport.load(args.detection)
    settings = Settings.from_env()
    policy = RulePolicy(load_codelists(settings.codelist_dir))
    plan = policy.plan(detections, _scenario(args.scenario, settings))
    plan.save(args.out)
    kept = sum(1 for a in plan.actions if a.technique is not Technique.DROP)
    print(f"draft plan for {plan.scenario_id}: {len(plan.tables)} tables, {kept} columns released -> {args.out}")
    for agg in plan.aggregates:
        print(f"  statistic {agg.name}: epsilon {agg.epsilon:g}")
    for item in _open_reviews(plan):
        print(f"  {REVIEW}: {item}")
    print(f'  next: read the reasons, edit if needed, then: pets-transformer approve {args.out} --by "Your Name"')
    return 0


def _open_reviews(plan: Plan) -> list[str]:
    columns = [f"{a.table}.{a.column}" for a in plan.actions if a.reason.startswith(REVIEW)]
    return columns + [f"statistic {a.name}" for a in plan.aggregates if a.reason.startswith(REVIEW)]


def cmd_approve(args: argparse.Namespace) -> int:
    plan = Plan.load(args.plan)
    open_reviews = _open_reviews(plan)
    if open_reviews and not args.confirm_review:
        raise ValueError(f"plan has open REVIEW items {open_reviews}; resolve them or pass --confirm-review")
    plan.model_copy(update={"approved": True, "approved_by": args.by}).save(args.plan)
    print(f"approved by {args.by}: {args.plan}")
    return 0


def cmd_web(args: argparse.Namespace) -> int:
    try:
        from pets_transformer.web.app import serve  # noqa: PLC0415 (optional extra)
    except ImportError:
        print('the web app needs the web extra: pip install -e ".[web]"', file=sys.stderr)
        return 1
    print(f"PETs Transformer: http://127.0.0.1:{args.port}  (Ctrl+C to stop)")
    serve(port=args.port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pets-transformer", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=__version__)
    env = p.add_mutually_exclusive_group()
    env.add_argument("--env-file", help="load this .env instead of the nearest one from the current folder up")
    env.add_argument("--no-env-file", action="store_true", help="do not load any .env file")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, func: Callable[[argparse.Namespace], int], help_: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_)
        sp.set_defaults(func=func)
        return sp

    add("doctor", cmd_doctor, "check configuration")
    add("schemas", cmd_schemas, "write JSON schemas").add_argument("--out", default="schemas")
    v = add("validate", cmd_validate, "validate a shared file")
    v.add_argument("file")
    v.add_argument("--kind", required=True, choices=sorted(KINDS))
    d = add("detect", cmd_detect, "label every column of a dataset, with evidence")
    d.add_argument("--dataset", required=True)
    d.add_argument("--out", required=True, help="detection.json to write")
    d.add_argument("--source", help="e.g. csv:path/to/folder (default: the package data for the dataset)")
    d.add_argument("--labels-csv", help="also write column,privacy_role,subtype (organisers' format)")
    pl = add("plan", cmd_plan, "draft a plan from detections and a scenario (never approved)")
    pl.add_argument("--detection", required=True)
    pl.add_argument("--scenario", required=True, help="scenario id (e.g. HEALTH-S1) or a YAML path")
    pl.add_argument("--out", required=True)
    ap = add("approve", cmd_approve, "record a person's approval of a plan")
    ap.add_argument("plan")
    ap.add_argument("--by", required=True, help="name of the person approving")
    ap.add_argument("--confirm-review", action="store_true", help="approve even with open REVIEW items")
    r = add("run", cmd_run, "apply an approved plan and write a release")
    r.add_argument("--plan", required=True)
    r.add_argument("--receiver", required=True, help="who gets the data; selects their own pseudonym key")
    r.add_argument("--out", required=True, help="output folder; release/ and private/ are created inside")
    r.add_argument("--source", help="e.g. csv:path/to/folder (default: the package data for the plan's dataset)")
    w = add("web", cmd_web, "open the local web app (this machine only)")
    w.add_argument("--port", type=int, default=8765)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.env_file_loaded = None if args.no_env_file else load_env_file(args.env_file)
        code: int = args.func(args)
    except (OSError, ValueError, KeyError, MissingKeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
