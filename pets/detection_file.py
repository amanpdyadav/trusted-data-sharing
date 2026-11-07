"""detection.json: the shared team file for step 1 (owners Hari and Chinedu, team plan page 10).

One file per dataset. For every column it records what the column is (role, subtype, how sure), why (evidence and
the legal or technical basis), and which analyses need it (`needed_by`, from the organisers' own task definitions),
so the plan step can protect a needed column instead of dropping it. The format is documented in
docs/detection/FORMAT.md.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pets_eval.utility import all_tasks

from . import DATA, OUTPUTS, ROOT
from . import detect

SCHEMA = "pets-transformer/detection/v1"
DETECTOR_VERSION = "v4"
REVIEW_BELOW = 0.6   # columns the rules are unsure about: shown for human review, and sent to the local model later
# Words the organisers use in task needs that stand for columns. "any" = any one of them is enough; "all" = all of them.
NEED_ALIASES = {
    "age": ("any", ["age", "date_of_birth", "birth_date", "holder_birth_date"]),
    "vitals": ("all", ["systolic_bp", "diastolic_bp", "heart_rate", "resp_rate", "temp_c", "spo2"]),
}
NOT_COLUMNS = {"record keys", "dp_answers", "ed_visits"}  # needs that are not column names


def load_sources() -> dict[str, str]:
    """Source ID → short title, read from docs/detection/SOURCES.md so there is one register."""
    out = {}
    for line in (ROOT / "docs" / "detection" / "SOURCES.md").read_text().splitlines():
        m = re.match(r"^\|\s*([A-Z][A-Z0-9-.]+)\s*\|\s*([^|]+?)\s*\|", line)
        if m and m.group(1) != "ID":
            out[m.group(1)] = m.group(2)
    return out


def _parse_needs(need: str) -> list[list[str]]:
    """Turn one need into options; any one option is enough, and every column in an option is needed.

    'los_minutes|arrival_ts+discharge_ts'        → [['los_minutes'], ['arrival_ts', 'discharge_ts']]
    'geo_lat/geo_lon or geo_city or src_ip'      → [['geo_lat', 'geo_lon'], ['geo_city'], ['src_ip']]
    'email_gateway.sender/recipients/ts_utc'     → [['sender', 'recipients', 'ts_utc']]
    'age'                                        → [['age'], ['date_of_birth'], ['birth_date'], ['holder_birth_date']]
    """
    need = re.sub(r"\s*\(.*?\)", "", need).strip()
    options: list[list[str]] = []
    for opt in re.split(r"\||\s+or\s+", need):
        opt = opt.strip()
        if not opt or opt in NOT_COLUMNS or opt.endswith(".*"):
            continue
        cols: list[str] = []
        for c in re.split(r"[+/]", opt):
            c = c.strip().split(".")[-1]
            if c in NOT_COLUMNS or not c:
                continue
            kind, names = NEED_ALIASES.get(c, ("all", [c]))
            if kind == "any" and len(re.split(r"[+/]", opt)) == 1:
                options += [[n] for n in names]
                cols = []
                break
            cols += names
        if cols:
            options.append(cols)
    return options


def task_index(dataset: str) -> tuple[dict, dict]:
    """Returns (tasks: id → description, scenarios, needs) and (column → list of needed_by entries)."""
    tasks, by_col = {}, {}
    for t in all_tasks([dataset]):
        tasks[t.id] = {"description": t.description, "table": t.table, "kind": t.kind, "scenarios": list(t.scenarios),
                       "needs": list(t.needs)}
        for need in t.needs:
            options = _parse_needs(need)
            for c in {c for cols in options for c in cols}:
                entry = {"task": t.id, "scenarios": list(t.scenarios), "alternative": len(options) > 1, "need": need}
                if entry not in by_col.setdefault(c, []):
                    by_col[c].append(entry)
    return tasks, by_col


def build(dataset: str, folder: Path | None = None, use_names: bool = True, nrows: int | None = 20000) -> dict:
    folder = folder or DATA / dataset
    sources = load_sources()
    tasks, by_col = task_index(dataset)
    used_sources, tables = set(), {}
    for f in sorted(folder.glob("*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False, nrows=nrows)
        rows = sum(1 for _ in f.open(encoding="utf-8", errors="ignore")) - 1
        dets = detect.detect_table(df, dataset, f.stem, use_names=use_names)
        cols = []
        for d in dets:
            used_sources.update(d.basis)
            needed = [n for n in by_col.get(d.column, []) if n["task"] in tasks]
            cols.append({
                "column": d.column, "role": d.privacy_role, "subtype": d.subtype, "sure": d.sure, "method": d.method,
                "evidence": d.evidence, "basis": d.basis,
                "art9": d.privacy_role == "sensitive_attribute" and "L-GDPR-9" in d.basis,
                "review": d.sure < REVIEW_BELOW,
                "needed_by": needed,
            })
        tables[f.stem] = {
            "rows": rows, "sampled_rows": len(df),
            "about_people": any(c["role"] in ("direct_identifier", "technical_identifier", "free_text") for c in cols),
            "columns": cols,
        }
    allc = [c for t in tables.values() for c in t["columns"]]
    return {
        "schema": SCHEMA,
        "dataset": dataset,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "detector": {"version": DETECTOR_VERSION, "column_names_used": use_names, "rows_sampled_per_table": nrows,
                     "values_checked_per_column": 400, "review_below": REVIEW_BELOW},
        "summary": {
            "tables": len(tables), "columns": len(allc),
            "by_role": {r: sum(c["role"] == r for c in allc) for r in detect.ROLES},
            "art9_columns": [f"{t}.{c['column']}" for t, tb in tables.items() for c in tb["columns"] if c["art9"]],
            "needs_review": [f"{t}.{c['column']}" for t, tb in tables.items() for c in tb["columns"] if c["review"]],
            "needed_by_any_task": sum(bool(c["needed_by"]) for c in allc),
        },
        "tables": tables,
        "tasks": tasks,
        "sources": {k: sources[k] for k in sorted(used_sources) if k in sources},
    }


def write(dataset: str, out_dir: Path | None = None, **kw) -> Path:
    out = Path(out_dir or OUTPUTS / "detection")
    out.mkdir(parents=True, exist_ok=True)
    p = out / f"{dataset}.detection.json"
    p.write_text(json.dumps(build(dataset, **kw), indent=1, ensure_ascii=False))
    return p
