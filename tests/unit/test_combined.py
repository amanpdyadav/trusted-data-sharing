"""The combined detector keeps agreeing labels and resolves disagreements by evidence strength."""

import pandas as pd

from pets_transformer.contracts import ColumnDetection, PrivacyRole, Subtype
from pets_transformer.detect.combined import CombinedDetector, combine


def _det(role: PrivacyRole, sub: Subtype, conf: float, basis: list[str] | None = None) -> ColumnDetection:
    return ColumnDetection(table="t", column="c", privacy_role=role, subtype=sub, confidence=conf, basis=basis or [])


def test_stronger_evidence_wins_a_disagreement() -> None:
    rule = _det(PrivacyRole.NON_SENSITIVE, Subtype.CATEGORY, 0.5)
    layered = _det(PrivacyRole.SENSITIVE_ATTRIBUTE, Subtype.SOCIAL_DATA, 0.7, ["L-GDPR-9"])
    got = combine(rule, layered)
    assert got.privacy_role is PrivacyRole.SENSITIVE_ATTRIBUTE
    assert "disagreed" in got.evidence[-1].detail


def test_tie_keeps_the_rule_based_label_and_agreement_merges_basis() -> None:
    a = _det(PrivacyRole.QUASI_IDENTIFIER, Subtype.DATE, 0.6, ["L-GDPR-R26"])
    b = _det(PrivacyRole.QUASI_IDENTIFIER, Subtype.DATE, 0.6, ["S-TAX"])
    got = combine(a, b)
    assert got.basis == ["L-GDPR-R26", "S-TAX"]
    assert got.evidence[-1].detail == "both detectors agree on the role"
    tie = combine(
        _det(PrivacyRole.RECORD_KEY, Subtype.RECORD_ID, 0.6), _det(PrivacyRole.NON_SENSITIVE, Subtype.OTHER, 0.6)
    )
    assert tie.privacy_role is PrivacyRole.RECORD_KEY


def test_union_membership_found_from_values_alone() -> None:
    frame = pd.DataFrame({"c13": ["AY-TK", "AY-PS", "AY-HL", "", "AY-TK"] * 20})
    (got,) = CombinedDetector().detect("export", frame)
    assert got.privacy_role is PrivacyRole.SENSITIVE_ATTRIBUTE
    assert got.special_category
