"""Detect every table of a source: the entry point the CLI, the web app and the evaluation use."""

from datetime import UTC, datetime

from pets_transformer import __version__
from pets_transformer.contracts import DetectionReport
from pets_transformer.detect.base import ColumnDetector
from pets_transformer.detect.combined import CombinedDetector
from pets_transformer.sources import TableSource


def detect_source(source: TableSource, dataset: str, detector: ColumnDetector | None = None) -> DetectionReport:
    """Label every column of every table. Default: the combined detector (rule-based plus layered)."""
    detector = detector or CombinedDetector()
    columns = [c for t in source.table_names() for c in detector.detect(t, source.read(t))]
    return DetectionReport(dataset=dataset, generated_at=datetime.now(UTC), tool_version=__version__, columns=columns)
