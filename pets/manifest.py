"""Step 5, Release manifest: a verifiable record of what was released, for whom, why and how.

Lists recipient, purpose, the technique and parameters per column, before/after scores, residual
risks and a SHA-256 fingerprint of every released file. Row maps are excluded: they are never released.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(out_dir: Path, scenario: dict, decisions: list, scorecard: dict) -> dict:
    out_dir = Path(out_dir)
    files = sorted(p for p in out_dir.glob("*.csv") if not p.name.startswith("rowmap_"))
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scenario": {k: scenario.get(k) for k in ("id", "recipient", "purpose", "trust_level")},
        "decisions": [d.__dict__ if hasattr(d, "__dict__") else d for d in decisions],
        "scores": scorecard.get("summary", {}),
        "residual_risks": scorecard.get("risk_components", {}),
        "files": [{"name": p.name, "sha256": sha256_file(p)} for p in files],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    return manifest
