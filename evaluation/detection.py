"""Score a detection.json against the package's field catalogue with pets-eval."""

from pathlib import Path
from typing import Any

import pandas as pd
from pets_eval import io as pe_io
from pets_eval.detect import score_detection

from pets_transformer.contracts import DetectionReport


def score(report: DetectionReport, package_root: Path) -> dict[str, Any]:
    """Per-role precision/recall/F1, macro-F1 and sensitive recall for the report's dataset."""
    pred = pd.DataFrame(report.to_pets_eval_rows())
    result: dict[str, Any] = score_detection(pred, pe_io.load_catalog(package_root), datasets=[report.dataset])
    return result
