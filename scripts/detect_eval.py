"""Run the column detector and score it with the organisers' `pets-eval detect`.

  .venv/bin/python scripts/detect_eval.py                 # dev datasets, column names visible
  .venv/bin/python scripts/detect_eval.py --hidden        # dev datasets, names hidden (simulates the unseen file)
  .venv/bin/python scripts/detect_eval.py --set heldout   # held-out datasets: report only, never tune on these
  .venv/bin/python scripts/detect_eval.py --set unseen    # write labels for the unseen HR file (no score: no labels)

Predictions go to outputs/detection/. See docs/detection/DECISIONS.md D2 for why the sets are split.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pets import DATA, OUTPUTS, PG_ROOT  # noqa: E402
from pets import detect  # noqa: E402

SETS = {
    "dev": ["health", "finance", "cyber", "customer_service", "education"],
    "heldout": ["mobility", "smart_city", "energy", "public_admin"],
}
SETS["all"] = SETS["dev"] + SETS["heldout"]


def run(names: list[str], use_names: bool) -> list:
    dets = []
    for ds in names:
        dets += detect.detect_dataset(DATA / ds, ds, use_names=use_names)
    return dets


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="dev", choices=["dev", "heldout", "all", "unseen"])
    ap.add_argument("--hidden", action="store_true", help="hide column names")
    ap.add_argument("--errors", type=int, default=0, help="print this many misclassified columns")
    a = ap.parse_args()
    out = OUTPUTS / "detection"
    out.mkdir(parents=True, exist_ok=True)

    if a.set == "unseen":
        dets = detect.detect_dataset(DATA / "unseen", "unseen", use_names=False)
        df = detect.to_frame(dets)
        df[["column", "privacy_role", "subtype"]].to_csv(out / "unseen_labels.csv", index=False)
        print(df[["column", "privacy_role", "subtype", "sure", "evidence"]].to_string(index=False))
        return

    tag = f"{a.set}_{'hidden' if a.hidden else 'names'}"
    dets = run(SETS[a.set], use_names=not a.hidden)
    df = detect.to_frame(dets)
    pred = out / f"pred_{tag}.csv"
    df[["dataset", "table", "column", "privacy_role", "subtype"]].to_csv(pred, index=False)
    df.to_json(out / f"detections_{tag}.json", orient="records", indent=1, force_ascii=False)
    res = subprocess.run([str(ROOT / ".venv/bin/pets-eval"), "detect", "--pred", str(pred), "--root", str(PG_ROOT),
                          "--datasets", ",".join(SETS[a.set])], capture_output=True, text=True, cwd=PG_ROOT)
    report = json.loads(res.stdout[res.stdout.find("{"):])
    roles = report["per_role"]
    print(f"{tag}: fields {report['n_fields']} · macro-F1 {report['macro_f1']:.3f} · accuracy {report['accuracy']:.3f} · "
          f"sensitive found {roles['sensitive_attribute']['recall']:.2f} · subtype acc {report['subtype_accuracy']:.2f}")
    for r, v in roles.items():
        print(f"  {r:22s} P {v['precision']:.2f} R {v['recall']:.2f} F1 {v['f1']:.2f} (n={v['support']})")
    if a.errors:
        import pandas as pd
        cat = pd.read_csv(PG_ROOT / "metadata/field_catalog.csv", dtype=str)
        m = df.merge(cat[["dataset", "table", "column", "privacy_role", "subtype"]], on=["dataset", "table", "column"],
                     suffixes=("", "_true"))
        wrong = m[m.privacy_role != m.privacy_role_true]
        print(f"\n{len(wrong)} wrong roles:")
        for r in wrong.head(a.errors).itertuples():
            print(f"  {r.dataset}.{r.table}.{r.column}: got {r.privacy_role}/{r.subtype}, true {r.privacy_role_true}/{r.subtype_true} · {r.evidence[:70]}")


if __name__ == "__main__":
    main()
