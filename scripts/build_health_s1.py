"""Build, score and document the HEALTH-S1 release: .venv/bin/python scripts/build_health_s1.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pets import OUTPUTS, evaluate, manifest  # noqa: E402
from pets import health_s1 as H  # noqa: E402

info = H.build()
card = evaluate.scorecard("health", OUTPUTS / "health", H.SCENARIO)
manifest.build_manifest(OUTPUTS / "health", H.scenario(),
                        [dict(column=c, technique=t, reason=r) for c, t, r in H.DECISIONS], card)
print(json.dumps({"build": info, "summary": card["summary"],
                  "utility": {u["id"]: u["score"] for u in card["utility"]}}, indent=2))
