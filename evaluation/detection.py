"""Score detection against the package's field catalogue with pets-eval (evaluation only: uses the answer key)."""

from pathlib import Path
from typing import Any

import pandas as pd
from pets_eval import io as pe_io
from pets_eval.detect import score_detection

from pets_transformer.contracts import DetectionReport
from pets_transformer.detect.source import detect_source
from pets_transformer.sources import open_source


def score(report: DetectionReport, package_root: Path) -> dict[str, Any]:
    """Per-role precision/recall/F1, macro-F1 and sensitive recall for the report's dataset."""
    pred = pd.DataFrame(report.to_pets_eval_rows())
    result: dict[str, Any] = score_detection(pred, pe_io.load_catalog(package_root), datasets=[report.dataset])
    return result


def score_datasets(package_root: Path, datasets: list[str]) -> tuple[dict[str, Any], dict[str, float]]:
    """Detect and score several datasets: overall scores plus macro-F1 per dataset."""
    catalog = pe_io.load_catalog(package_root)
    rows: list[dict[str, str]] = []
    per: dict[str, float] = {}
    for ds in datasets:
        report = detect_source(open_source(f"csv:{package_root / 'data' / ds}"), ds)
        ds_rows = report.to_pets_eval_rows()
        rows += ds_rows
        per[ds] = float(score_detection(pd.DataFrame(ds_rows), catalog, datasets=[ds])["macro_f1"])
    overall: dict[str, Any] = score_detection(pd.DataFrame(rows), catalog, datasets=datasets)
    return overall, per
