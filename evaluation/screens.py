"""Data for the web app's Mosaic attack screen, and the organisers' scorecard shown in a release's audit record.

    python -m evaluation screens        # from the newest HEALTH-S1 release made in the web app
    python -m evaluation screens --release out/health-s1/release --rowmaps out/health-s1/private

writes results/screens/mosaic.json and results/screens/audit.json; the web app shows them under "Mosaic attack" and
"Release audit". Built here, not in the runtime package, because they read the attacker files and the ground truth.

Mosaic attack, three modes per case (built in mosaic_chain.py):
  raw    every organisation shares raw files: the chain from the scrap to a verified person and their other data
  names  names, ID codes, phones and addresses removed everywhere: the same clues still lead to the person
  ours   the same clues replayed on our release
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evaluation import mosaic_chain
from evaluation.attacks import replay_summary
from evaluation.runner import Scored
from evaluation.scorecard import record_ids
from pets_transformer.io import read_table

OUT = Path("results/screens")


def mosaic(package_root: Path, release: Path, rowmaps: Path) -> dict[str, Any]:
    """Every public post and news clip that leads to one verified person: raw and names-removed chains, plus a replay
    on our release (evaluation/mosaic_chain.py)."""
    frame = read_table(release / "ed_visits.csv")
    cases, summary = mosaic_chain.build(package_root, frame, record_ids(rowmaps, "ed_visits", len(frame)))
    return {
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"), "release": str(release),
        "summary": summary, "cases": cases,
    }  # fmt: skip


def latest_app_release(web: Path, scenario: str = "HEALTH-S1") -> tuple[Path, Path] | None:
    """The newest release of `scenario` made in the web app (release and row-map folders), or None.

    The app keeps the latest release of each dataset in <session>/release and its row maps in <session>/private."""
    found = []
    for manifest in web.glob("*/release/manifest.json"):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        if data.get("plan", {}).get("scenario_id") == scenario:
            found.append((str(data.get("created_at")), manifest.parent))
    if not found:
        return None
    release = max(found)[1]
    return release, release.parent / "private"


def audit(scored: Scored, plan_path: Path | None) -> dict[str, Any]:
    m = scored.metrics
    manifest_path = scored.run.release / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    plan = yaml.safe_load(plan_path.read_text(encoding="utf-8")) if plan_path and plan_path.exists() else {}
    plan = plan or (manifest or {}).get("plan", {})  # an app release carries its approved plan in the manifest
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
            "worst": [{"id": r.case_id, **replay_summary(r)} for r in sw.worst],
        },
        "decisions": [{k: a.get(k) for k in ("table", "column", "technique", "params", "reason")}
                      for a in plan.get("actions", [])],
        "quasi_identifiers": plan.get("quasi_identifiers", {}), "k_target": plan.get("k_target"),
        "approved_by": plan.get("approved_by"),
        "manifest": manifest,
    }  # fmt: skip


def write(name: str, data: dict[str, Any], out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    return path
