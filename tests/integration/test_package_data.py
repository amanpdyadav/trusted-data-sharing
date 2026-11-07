"""Checks against the real challenge data. Skipped when the package is not on disk."""

from pathlib import Path

import pytest

from pets_transformer.assess.kanon import k_anonymity
from pets_transformer.config import Settings
from pets_transformer.detect.base import match_rate
from pets_transformer.detect.rules import detect_source
from pets_transformer.detect.validators import HetuValidator, IbanValidator
from pets_transformer.sources import open_source

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def health() -> object:
    data = ROOT / Settings.from_env().package_root / "data" / "health"
    if not data.is_dir():
        pytest.skip("TrustED data package not found")
    return open_source(f"csv:{data}")


def test_hetu_validator_recognises_the_id_column(health: object) -> None:
    visits = health.read("ed_visits")  # type: ignore[attr-defined]
    assert match_rate(visits["patient_hetu"], HetuValidator()) > 0.99
    assert match_rate(visits["patient_name"], HetuValidator()) == 0.0


def test_iban_validator_on_bank_data() -> None:
    data = ROOT / Settings.from_env().package_root / "data" / "finance"
    if not data.is_dir():
        pytest.skip("TrustED data package not found")
    customers = open_source(f"csv:{data}").read("customers")
    assert match_rate(customers["iban"], IbanValidator()) > 0.99


def test_raw_ed_visits_reproduce_the_known_k_problem(health: object) -> None:
    """Our own k check agrees with what we measured: raw arrival time + sex + municipality is near-unique."""
    visits = health.read("ed_visits")  # type: ignore[attr-defined]
    r = k_anonymity(visits, ["sex", "municipality", "arrival_ts"], k_target=5)
    assert r.share_below_k > 0.95


def test_detector_on_the_hospital_tables(health: object) -> None:
    found = {(c.table, c.column): c.privacy_role.value for c in detect_source(health, "health").columns}  # type: ignore[arg-type]
    assert found[("ed_visits", "visit_id")] == "record_key"
    assert found[("ed_visits", "patient_hetu")] == "direct_identifier"
    assert found[("ed_visits", "patient_name")] == "direct_identifier"
    assert found[("ed_visits", "phone")] == "direct_identifier"
    assert found[("ed_visits", "date_of_birth")] == "quasi_identifier"
    assert found[("ed_visits", "icd10_primary")] == "sensitive_attribute"
    assert found[("ed_visits", "chief_complaint")] == "free_text"
    assert found[("lab_results", "visit_id")] == "technical_identifier"
