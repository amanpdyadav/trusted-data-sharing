"""The shipped receivers: all 27 package scenarios load, and public ones never release rows."""

from pathlib import Path

from pets_transformer.contracts import TrustLevel
from pets_transformer.plan.scenario import load_scenarios

ROOT = Path(__file__).resolve().parents[2]


def test_all_27_package_scenarios_load() -> None:
    found = load_scenarios([ROOT / "scenarios"])
    assert len(found) == 27
    datasets = {"health", "mobility", "smart_city", "energy", "finance", "cyber", "education", "public_admin"}
    assert {s.dataset for s in found.values()} == datasets | {"customer_service"}


def test_public_receivers_get_statistics_only_and_others_a_data_request() -> None:
    for s in load_scenarios([ROOT / "scenarios"]).values():
        if s.trust_level is TrustLevel.PUBLIC:
            assert s.statistics, s.id
            assert not s.needs, s.id
            assert s.targets.epsilon, s.id
        else:
            assert s.needs, s.id
            assert s.targets.k, s.id
