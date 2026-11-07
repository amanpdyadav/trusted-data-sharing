"""Combined detector: Aman's rule-based detector and the main branch's layered detector, side by side.

Both label every column. Where they agree, the label stands. Where they disagree, the label with the stronger
evidence (higher confidence) wins; on a tie the rule-based detector's label is kept. Measured on all nine
labelled datasets, this beats either detector alone (macro-F1 0.910 vs 0.875 and 0.907; sensitive attributes
found 88 % vs 62 % and 85 %), and with column names hidden (0.784 vs 0.669 and 0.779). See docs/detection/SCORES.md.
"""

import pandas as pd

from pets_transformer.contracts import ColumnDetection, Evidence, EvidenceKind
from pets_transformer.detect.layered import LayeredDetector
from pets_transformer.detect.rules import RuleBasedDetector


def _label(c: ColumnDetection) -> str:
    return f"{c.privacy_role.value}/{c.subtype.value}"


def combine(rule: ColumnDetection, layered: ColumnDetection) -> ColumnDetection:
    """Pick one label for a column and keep both opinions in the evidence."""
    if rule.privacy_role is layered.privacy_role:
        best = layered if rule.subtype is not layered.subtype and layered.confidence > rule.confidence else rule
        note = Evidence(kind=EvidenceKind.STATISTICS, detail="both detectors agree on the role")
        return best.model_copy(update={
            "confidence": round(max(rule.confidence, layered.confidence), 3),
            "evidence": [*best.evidence, note],
            "basis": sorted({*rule.basis, *layered.basis}),
            "special_category": rule.special_category or layered.special_category,
        })  # fmt: skip
    winner, loser = (layered, rule) if layered.confidence > rule.confidence else (rule, layered)
    note = Evidence(
        kind=EvidenceKind.STATISTICS,
        detail=f"the detectors disagreed: chose {_label(winner)} ({winner.confidence:.2f}) over "
        f"{_label(loser)} ({loser.confidence:.2f}) on stronger evidence",
    )
    return winner.model_copy(update={"evidence": [*winner.evidence, note]})


class CombinedDetector:
    """Implements ColumnDetector."""

    def __init__(self) -> None:
        self.rule = RuleBasedDetector()
        self.layered = LayeredDetector()

    def detect(self, table: str, frame: pd.DataFrame) -> list[ColumnDetection]:
        a = self.rule.detect(table, frame)
        b = {c.column: c for c in self.layered.detect(table, frame)}
        return [combine(c, b[c.column]) if c.column in b else c for c in a]
