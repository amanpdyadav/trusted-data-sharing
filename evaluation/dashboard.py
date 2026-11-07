"""Score a published dashboard (noisy tables) with pets-eval. Evaluation only: never part of a release.

pets-eval reads the health DP workload from `dp_answers.csv` and its other public-dashboard tasks (weekly
influenza-like illness by age, hour-of-day curve) from a row table. This adapter builds both from the published
tables alone, so it is post-processing of differentially private output and costs no privacy:

    dp_answers.csv   each workload query answered by adding up published cells
    ed_visits.csv    a sample of rows drawn from the published weekly and hourly tables (scored as synthetic)
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pets_transformer.contracts import ReleaseManifest
from pets_transformer.io import read_table

QUERY_MEASURE = {"los": "mean", "admitted": "share"}  # workload value -> measure kind of the published table


@dataclass(frozen=True)
class PublishedTable:
    name: str
    kind: str  # count | mean | share
    dimensions: tuple[str, ...]
    frame: pd.DataFrame


def load_published(release: Path) -> list[PublishedTable]:
    manifest = ReleaseManifest.load(release / "manifest.json")
    tables = []
    for a in manifest.plan.aggregates:
        frame = read_table(release / f"{a.name}.csv")
        for col in ("value", "rows"):
            if col in frame.columns:
                frame[col] = pd.to_numeric(frame[col])
        dims = tuple(d.output_name for d in a.dimensions)
        tables.append(PublishedTable(a.name, a.measure.kind, dims, frame))
    return tables


def answer(query: dict[str, Any], tables: list[PublishedTable]) -> float:
    """Add up the cells of the smallest published table that covers the query (fewest noisy cells summed)."""
    filters: dict[str, str] = {k: str(v) for k, v in query["filters"].items()}
    kind = "count" if query["type"] == "count" else QUERY_MEASURE.get(str(query.get("value")), "")
    fits = [t for t in tables if t.kind == kind and set(filters) <= set(t.dimensions)]
    if not fits:
        return float("nan")
    t = min(fits, key=lambda t: len(t.frame))
    cells = t.frame
    for k, v in filters.items():
        cells = cells[cells[k] == v]
    if cells.empty:
        return float("nan")
    if kind == "count":
        return float(cells["value"].sum())
    weights = cells["rows"].clip(lower=1)
    return float((cells["value"] * weights).sum() / weights.sum())


def workload_answers(tables: list[PublishedTable], workload: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame([{"id": q["id"], "value": answer(q, tables)} for q in workload["queries"]])


def _count_table(tables: list[PublishedTable], dimensions: tuple[str, ...]) -> PublishedTable:
    found = next((t for t in tables if t.kind == "count" and t.dimensions == dimensions), None)
    if found is None:
        raise ValueError(f"the dashboard has no count table by {', '.join(dimensions)}")
    return found


def _draw(rng: np.random.Generator, cells: pd.DataFrame, column: str, size: int) -> np.ndarray:
    p = cells["value"].clip(lower=0).to_numpy(dtype=float)
    if p.sum() <= 0:
        p = np.ones(len(cells))
    drawn: np.ndarray = rng.choice(cells[column].to_numpy(), size=size, p=p / p.sum())
    return drawn


def sample_visits(tables: list[PublishedTable], seed: int = 0) -> pd.DataFrame:
    """One row per visit counted in the weekly table; hour and age band drawn from the hourly and monthly tables."""
    weekly = _count_table(tables, ("week", "diagnosis_group")).frame
    hourly = _count_table(tables, ("hour",)).frame
    monthly = _count_table(tables, ("month", "age_band")).frame
    rng = np.random.default_rng(seed)
    cells = weekly[weekly["value"] > 0]
    rows = cells.loc[cells.index.repeat(cells["value"].astype(int))].reset_index(drop=True)
    monday = pd.to_datetime(rows["week"] + "-1", format="%G-W%V-%u")
    hours = _draw(rng, hourly.assign(h=hourly["hour"].str[:2].astype(int)), "h", len(rows))
    ages = pd.Series("", index=rows.index)
    for month, idx in rows.groupby(monday.dt.strftime("%Y-%m")).groups.items():
        same = monthly[monthly["month"] == month]
        ages[idx] = _draw(rng, same if len(same) else monthly, "age_band", len(idx))
    return pd.DataFrame(
        {
            "arrival_ts": (monday + pd.to_timedelta(hours, unit="h")).dt.strftime("%Y-%m-%d %H:00"),
            "age": ages,
            "diagnosis_group": rows["diagnosis_group"],
        }
    )


def is_dashboard(release: Path) -> bool:
    """A release of published statistics only (no row tables): it needs the scoring view to be scored."""
    path = release / "manifest.json"
    if not path.exists():
        return False
    plan = ReleaseManifest.load(path).plan
    return bool(plan.aggregates) and not plan.tables


def scoring_view(release: Path, package_root: Path, out: Path) -> Path:
    """Write dp_answers.csv and ed_visits.csv for pets-eval; returns the folder."""
    tables = load_published(release)
    workload = json.loads((package_root / "metadata" / "dp_query_workload_health.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    workload_answers(tables, workload).to_csv(out / "dp_answers.csv", index=False)
    sample_visits(tables).to_csv(out / "ed_visits.csv", index=False)
    return out
