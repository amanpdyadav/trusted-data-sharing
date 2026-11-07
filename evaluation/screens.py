"""Data for the web app's two presentation screens (ported from the main branch's mosaic attack and release audit).

    python -m evaluation screens --release out/health-s1/release --rowmaps out/health-s1/private

writes results/screens/mosaic.json and results/screens/audit.json; the web app shows them under "Mosaic attack" and
"Release audit". Built here, not in the runtime package, because they read the attacker files and the ground truth.

Mosaic attack, three modes per case:
  raw    every organisation shares raw files: the verified chain from demo/mosaic_trace.json
  names  names, ID codes, phones and addresses removed: the same clues replayed on the package quickstart release
  ours   the same clues replayed on our release
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evaluation import mosaic_chain
from evaluation.attacks import AttackCase, ReplayResult, replay
from evaluation.runner import Scored
from pets_transformer.io import read_table

TRACE = Path("demo/mosaic_trace.json")
OUT = Path("results/screens")


def _ids(rowmap_dir: Path, table: str, rows: int) -> list[str] | None:
    path = rowmap_dir / f"rowmap_{table}.csv"
    if not path.exists():
        return None
    rm = read_table(path).astype({"protected_row": int}).sort_values("protected_row")
    ids: list[str] = rm["original_record_id"].astype(str).tolist()
    return ids if len(ids) == rows else None


def _funnel(r: ReplayResult) -> dict[str, Any]:
    return {
        "funnel": [[s.label, s.candidates, s.applied] for s in r.funnel],
        "candidates": r.candidates_left,
        "target_in": r.target_among_candidates,
        "holds": r.candidates_left == 0 or r.target_among_candidates is False or r.candidates_left >= 5,
    }


def _replay_on(case: AttackCase, folder: Path, rowmaps: Path) -> dict[str, Any] | None:
    path = folder / f"{case.table}.csv"
    if not path.exists():
        return None
    frame = read_table(path)
    return _funnel(replay(case, frame, _ids(rowmaps, case.table, len(frame))))


def mosaic(package_root: Path, release: Path, rowmaps: Path) -> dict[str, Any]:
    """Every public post and news clip that leads to one verified person: raw and names-removed chains, plus a replay
    on our release (evaluation/mosaic_chain.py)."""
    frame = read_table(release / "ed_visits.csv")
    cases = mosaic_chain.build(package_root, frame, _ids(rowmaps, "ed_visits", len(frame)))
    return {"created_utc": datetime.now(UTC).isoformat(timespec="seconds"), "release": str(release), "cases": cases}


def audit(scored: Scored, plan_path: Path | None) -> dict[str, Any]:
    m = scored.metrics
    manifest_path = scored.run.release / "manifest.json"
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) if plan_path and plan_path.exists() else {}
    sw = scored.sweep
    return {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "run_id": m.run_id, "dataset": m.dataset, "scenario": m.scenario_id,
        "scores": {"privacy": m.privacy, "utility": m.utility, "composite": m.composite,
                   "share_below_k": m.share_below_k, "k_min": m.k_min},
        "gates": [{"name": g.name, "value": g.value, "target": g.target, "status": g.status} for g in scored.gates],
        "attacks": [a.model_dump(mode="json") for a in m.attacks],
        "sweep": None if sw is None else {
            "scraps": sw.scraps, "single": sw.single, "single_target": sw.single_target, "exposed": sw.exposed,
            "median_candidates": sw.median_candidates,
            "worst": [{"id": r.case_id, **_funnel(r)} for r in sw.worst],
        },
        "decisions": [{k: a.get(k) for k in ("table", "column", "technique", "params", "reason")}
                      for a in plan.get("actions", [])],
        "quasi_identifiers": plan.get("quasi_identifiers", {}), "k_target": plan.get("k_target"),
        "approved_by": plan.get("approved_by"),
        "manifest": json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None,
    }  # fmt: skip


def write(name: str, data: dict[str, Any], out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path
