"""Command line. Each sub-command is one small function; the pipeline commands arrive as the steps land.

pets-transformer doctor                       # is everything configured? (AI on/off, key, data, scenarios)
pets-transformer schemas --out schemas        # JSON schemas for the shared files (the UI reads these)
pets-transformer validate plan.yaml --kind plan
"""

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import BaseModel

from pets_transformer import __version__
from pets_transformer.config import Settings
from pets_transformer.contracts import CONTRACTS, Contract, RecordSpans
from pets_transformer.keys import DerivedKeyProvider, MissingKeyError
from pets_transformer.llm import LlmUnavailableError, build_llm
from pets_transformer.plan.scenario import Scenario, load_scenarios
from pets_transformer.plugins import load_plugins

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


def cmd_doctor(_: argparse.Namespace) -> int:
    s = Settings.from_env()
    lines = [f"pets-transformer {__version__}"]
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pets-transformer", description=__doc__.splitlines()[0])
    p.add_argument("--version", action="version", version=__version__)
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
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.func(args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
