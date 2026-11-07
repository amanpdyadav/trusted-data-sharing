"""Write scenario files for the package's 27 sharing scenarios (scenarios/<ID>.yaml).

    python -m evaluation scenarios            # writes the missing ones; HEALTH-S1/S2 (hand-written) are kept

Descriptive fields (recipient, purpose, trust level, threat model, legal context, suggested targets) come from
metadata/scenarios.json. The data request comes from the organisers' utility tasks for each scenario: the columns
each analysis uses, resolved to their tables, plus the ID columns that join those tables.

- Row-level receivers (contractual, controlled research, internal) get `needs` and k >= 5.
- Public receivers get `statistics` (differential privacy, like HEALTH-S2): the organisers say no row-level data may
  be published openly. Each analysis becomes one noisy table of counts, or of means for a numeric measure.

Evaluation only (reads the organisers' task definitions and the data headers). Review a generated file before use.
"""

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from pets_eval.utility import all_tasks

NOT_COLUMNS = {"record keys", "*", "dp_answers", "trip chaining"}
TIME_HINTS = ("hour", "peak", "daily", "time of day", "load profile")
TEXT_COLUMNS = {"text", "description", "agent_note", "note_text", "message"}
ID_LIKE = re.compile(r"(^|_)(id|upn|pan|iban|mac|plate|account|number)$|^card_id$|_id$")
# Identifiers of a person, card, device or account: they bound contributions and are never published.
PERSON_ID = re.compile(
    r"upn|card_id|card_pan|customer_id|student_id|^mac$|plate|iban|account|reporter|metering_point|"
    r"employee|patient|hetu|sender|recipient|device_id|session_id|correlation"
)
POINTS = re.compile(r"(^|_)(lat|lon|latitude|longitude)$")
CATEGORY_NAMES = re.compile(r"postcode|zip|code$|_code|station|stop_id|sensor_id|car_park|zone|line$")
HANDWRITTEN = {"HEALTH-S1", "HEALTH-S2"}
# Receivers whose analyses need hourly time, chosen by measurement (both settings released and scored with pets-eval,
# 7 Nov): hourly raised the combined score and kept privacy >= 0.9. Combined score with the planner's default -> hourly:
# CYBER-S1 0.20 -> 0.35, ENERGY-S2 0.00 -> 1.00, ENERGY-S3 0.63 -> 1.00, FIN-S1 0.00 -> 0.69, FIN-S2 0.28 -> 0.63.
# Not chosen: CITY-S2 and MOB-S2 (privacy fell to about 0.4), MOB-S3 and PUB-S3 (score fell), the rest (no change).
HOURLY = {"CYBER-S1", "ENERGY-S2", "ENERGY-S3", "FIN-S1", "FIN-S2"}


def _headers(data: Path, dataset: str) -> dict[str, list[str]]:
    return {f.stem: list(pd.read_csv(f, nrows=0).columns) for f in sorted((data / dataset).glob("*.csv"))}


def _columns_of(need: str) -> list[tuple[str | None, str]]:
    """'a|b' -> first option; 'x or y' -> first; 't.a/b/c' -> [(t, a), (t, b), (t, c)]; 'a+b' -> both."""
    need = re.sub(r"\s*\(.*?\)", "", need).strip()
    first = re.split(r"\||\s+or\s+", need)[0].strip()
    if not first or first in NOT_COLUMNS or first.endswith(".*"):
        return []
    table = None
    if "." in first.split("/")[0]:
        table, first = first.split(".", 1)
    out: list[tuple[str | None, str]] = []
    for part in re.split(r"[+/,]", first):
        col = part.strip()
        if "." in col:
            t, col = col.split(".", 1)
            out.append((t, col))
        elif col and col not in NOT_COLUMNS:
            out.append((table, col))
    return out


def _resolve(col: str, hint: str | None, task_table: str, headers: dict[str, list[str]]) -> str | None:
    for t in (hint, *task_table.split("+"), *headers):
        if t and t in headers and col in headers[t]:
            return t
    return None


def _hourly(needs: list[dict[str, str]], folder: Path) -> None:
    """Timestamps at the finest resolution the planner offers (hour); k >= 5 still applies to them."""
    for n in needs:
        sample = pd.read_csv(folder / f"{n['table']}.csv", nrows=200, dtype=str, usecols=[n["column"]],
                             keep_default_na=False)[n["column"]]  # fmt: skip
        if _is_time(sample) and sample.str.contains(r"\d{1,2}:\d{2}").mean() > 0.5:
            n["detail"] = "hour"


def request(scenario: dict[str, Any], headers: dict[str, list[str]], data_dir: Path) -> list[dict[str, str]]:
    """Columns the scenario's analyses use, in task order, plus shared ID columns that join the tables."""
    tasks = {t.id: t for t in all_tasks([scenario["dataset"]])}
    needs: list[dict[str, str]] = []
    for tid in scenario["utility_requirements"]:
        t = tasks.get(tid)
        if t is None:
            continue
        for raw in t.needs:
            for hint, col in _columns_of(raw):
                table = _resolve(col, hint, t.table, headers)
                if table and {"table": table, "column": col} not in needs:
                    needs.append({"table": table, "column": col})
    if scenario["id"] in HOURLY:
        _hourly(needs, data_dir / scenario["dataset"])
    tables = list(dict.fromkeys(n["table"] for n in needs))
    for i, a in enumerate(tables):  # join keys: ID-like columns two requested tables share
        for b in tables[i + 1 :]:
            for col in sorted(set(headers[a]) & set(headers[b])):
                if ID_LIKE.search(col):
                    for t in (a, b):
                        if {"table": t, "column": col} not in needs:
                            needs.append({"table": t, "column": col})
    return needs


def _is_time(v: pd.Series) -> bool:
    return bool(pd.to_datetime(v.head(200), errors="coerce", format="mixed").notna().mean() > 0.9)


def statistics(scenario: dict[str, Any], data: Path, headers: dict[str, list[str]]) -> list[dict[str, Any]]:
    """One published table per analysis: counts (or means) by the analysis' categorical and time columns."""
    tasks = {t.id: t for t in all_tasks([scenario["dataset"]])}
    stats: list[dict[str, Any]] = []
    for tid in scenario["utility_requirements"]:
        t = tasks.get(tid)
        if t is None:
            continue
        table = t.table.split("+")[0]
        if table == "*" or table not in headers:
            continue
        cols = [c for raw in t.needs for hint, c in _columns_of(raw) if (hint in (None, table)) and c in headers[table]]
        sample = pd.read_csv(data / scenario["dataset"] / f"{table}.csv", nrows=5000, dtype=str, keep_default_na=False)
        by: list[dict[str, str]] = []
        measure: dict[str, Any] | None = None
        hourly = any(h in t.description.lower() for h in TIME_HINTS)
        for c in dict.fromkeys(cols):
            v = sample[c]
            if PERSON_ID.search(c) or c in TEXT_COLUMNS or POINTS.search(c):
                continue  # person identifiers bound contributions and are never published; text and points are withheld
            nums = pd.to_numeric(v.str.replace(",", ".", regex=False), errors="coerce")
            if "birth" in c:
                by.append({"column": c, "detail": "age_band"})
            elif _is_time(v) and nums.notna().mean() < 0.5:
                by.append({"column": c, "detail": "time_of_day" if hourly else "week"})
            elif CATEGORY_NAMES.search(c) and v.nunique() <= 1000:
                by.append({"column": c})
            elif nums.notna().mean() > 0.9 and v.nunique() > 30 and measure is None:
                upper = float(nums.quantile(0.99))
                measure = {"kind": "mean", "column": c, "lower": 0, "upper": round(upper if upper > 0 else 1.0, 2)}
            elif v.nunique() <= 60:
                by.append({"column": c})
        if not by:
            continue
        name = re.sub(r"[^a-z0-9]+", "_", f"{tid}_{t.description}".lower()).strip("_")[:48].rstrip("_")
        entry: dict[str, Any] = {"name": name, "table": table, "by": by}
        if measure:
            entry["measure"] = measure
        stats.append(entry)
    # One dashboard bounds every person's contribution with one key, so keep the table most analyses use.
    main = max({st["table"] for st in stats}, key=[st["table"] for st in stats].count) if stats else None
    return [st for st in stats if st["table"] == main]


def scenario_file(s: dict[str, Any], data: Path) -> dict[str, Any]:
    headers = _headers(data, s["dataset"])
    public = s["trust_level"] == "public"
    out: dict[str, Any] = {
        "schema_version": "1", "id": s["id"], "dataset": s["dataset"], "title": s["title"], "recipient": s["recipient"],
        "purpose": s["purpose"], "trust_level": s["trust_level"], "threat_model": s["threat_model"],
        "legal_context": s.get("legal_context"), "utility_requirements": s["utility_requirements"],
    }  # fmt: skip
    targets: dict[str, Any] = {"notes": s.get("suggested_privacy_targets")}
    if public:
        targets |= {"epsilon": 1.0, "epsilon_cap": 4.0, "rows_per_person": 3}
        out["statistics"] = statistics(s, data, headers)
    else:
        targets["k"] = 5
        out["needs"] = request(s, headers, data)
        if any(n["column"] in TEXT_COLUMNS for n in out["needs"]):
            targets["text_recall"] = 0.95
    out["targets"] = targets
    generated = ("Generated from metadata/scenarios.json and the organisers' utility tasks by "
                 "`python -m evaluation scenarios`; review the data request before use.")  # fmt: skip
    out["notes"] = f"{s.get('notes') or ''} {generated}".strip()
    return out


def write_all(package_root: Path, out_dir: Path, force: bool = False) -> list[Path]:
    scenarios = json.loads((package_root / "metadata" / "scenarios.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for s in scenarios:
        path = out_dir / f"{s['id']}.yaml"
        if s["id"] in HANDWRITTEN or (path.exists() and not force):
            continue
        body = yaml.safe_dump(scenario_file(s, package_root / "data"), sort_keys=False, allow_unicode=True, width=110)
        header = f"# {s['id']}: generated from the package's metadata/scenarios.json (docs/SCENARIOS.md). Review it.\n"
        path.write_text(header + body, encoding="utf-8")
        written.append(path)
    return written
