"""The organisers' reference baselines, per receiver, to set next to our benchmark (results/baselines.csv).

    python -m evaluation baselines

Read from the challenge pack's results/benchmark.json (written by its baselines/run_all.py with pets-eval):
  B0    drop the catalogued direct identifiers, keep everything else
  B2    classic protection: keyed pseudonyms, generalised quasi-identifiers, regex text redaction
  B2-k  B2 plus local suppression to k >= 5
Usefulness is per receiver (mean of its required tasks). Privacy is per dataset only: the organisers scored each
baseline once per dataset, so every receiver of a dataset shows the same baseline privacy. The baselines read the field
catalogue instead of detecting fields, and release rows even for public receivers (where only statistics may go).
"""

import csv
import json
from pathlib import Path
from typing import Any

from evaluation.runner import RESULTS

CSV = RESULTS / "baselines.csv"
LEVELS = {"b0": "B0", "b2": "B2", "b2k": "B2K"}
FIELDS = [
    "id", "dataset",
    *(f"{m}_{k}" for k in LEVELS for m in ("privacy", "utility")),
    "generated",
]  # fmt: skip


def rows(package_root: Path) -> list[dict[str, Any]]:
    """One row per receiver the baselines measured: dataset privacy and receiver usefulness for B0, B2 and B2-k."""
    data = json.loads((package_root / "results" / "benchmark.json").read_text(encoding="utf-8"))
    runs: dict[str, dict[str, Any]] = data["baselines"]
    out: dict[str, dict[str, Any]] = {}
    for key, run in runs.items():
        level, _, dataset = key.partition("_")
        short = next((k for k, v in LEVELS.items() if v == level), None)
        if short is None or "utility_by_scenario" not in run:
            continue  # B1 (detection), B3 and B4 (health only) are not per-receiver protections
        for scenario, utility in run["utility_by_scenario"].items():
            row = out.setdefault(scenario, {"id": scenario, "dataset": dataset, "generated": data.get("generated", "")})
            row[f"privacy_{short}"] = round(float(run["privacy"]), 4)
            row[f"utility_{short}"] = round(float(utility), 4)
    return sorted(out.values(), key=lambda r: (r["dataset"], r["id"]))


def write(found: list[dict[str, Any]], path: Path = CSV) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(found)
    return path
