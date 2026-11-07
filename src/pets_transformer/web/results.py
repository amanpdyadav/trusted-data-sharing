"""What the evaluation commands wrote to results/ (outside the tool): the receivers benchmark, the organisers'
baselines, and the presentation screens' data. The app only reads these files; it never runs the evaluation."""

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCREENS = ("mosaic", "audit")


@dataclass(frozen=True)
class EvaluationResults:
    root: Path  # the results folder (Settings.results_dir)

    def receivers_benchmark(self) -> dict[str, Any]:
        """The automatic planner measured on every receiver (receivers.csv, `make receivers`), with the baselines."""
        path = self.root / "receivers.csv"
        if not path.exists():
            return {"rows": [], "measured_at": None, "baselines_generated": None}
        with path.open(encoding="utf-8", newline="") as f:
            rows: list[dict[str, Any]] = list(csv.DictReader(f))
        for r in rows:
            for k in ("privacy", "utility", "composite", "epsilon"):
                r[k] = float(r[k]) if r.get(k) else None
            r["released_tables"] = int(r["released_tables"] or 0)
        base = read_baselines(self.root / "baselines.csv")
        for r in rows:
            r["baselines"] = base.get(r["id"])
        return {
            "rows": rows,
            "measured_at": max((r["measured_at"] for r in rows), default=None),
            "baselines_generated": next((b["generated"] for b in base.values()), None),
        }

    def screens(self) -> list[str]:
        """The presentation screens whose data has been built (`make screens`)."""
        return [n for n in SCREENS if (self.root / "screens" / f"{n}.json").exists()]

    def screen(self, name: str) -> dict[str, Any] | None:
        """One presentation screen's data, or None when it is unknown or not built yet."""
        path = self.root / "screens" / f"{name}.json"
        if name not in SCREENS or not path.exists():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def scorecard_for(self, release_id: str) -> dict[str, Any] | None:
        """The organisers' scorecard of this release, when `make screens` scored it."""
        data = self.screen("audit")
        return data if data and (data.get("manifest") or {}).get("release_id") == release_id else None


def read_baselines(path: Path) -> dict[str, dict[str, Any]]:
    """The organisers' B0, B2 and B2-k per receiver (results/baselines.csv, `make baselines`): privacy per dataset,
    usefulness per receiver."""
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        found = list(csv.DictReader(f))
    return {
        r["id"]: {
            "generated": r["generated"],
            **{
                k: {"privacy": float(r[f"privacy_{k}"]), "utility": float(r[f"utility_{k}"])}
                for k in ("b0", "b2", "b2k")
            },
        }
        for r in found
    }
