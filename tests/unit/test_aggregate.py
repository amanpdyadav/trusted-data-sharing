"""Differential privacy: contribution bounding, discrete Laplace noise, noisy tables and the budget ledger."""

import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from pets_transformer.aggregate import BudgetExceededError, EpsilonLedger, bound_contributions, discrete_laplace
from pets_transformer.aggregate.cubes import noisy_table
from pets_transformer.contracts import Aggregate, DifferentialPrivacy, Dimension, Measure, Plan
from pets_transformer.keys import DerivedKeyProvider
from pets_transformer.transform import TransformContext
from tests.conftest import TEST_MASTER_KEY

NOW = datetime(2026, 11, 7, tzinfo=UTC)
DP = DifferentialPrivacy(unit="person", max_rows_per_unit=2)


def _ctx(frame: pd.DataFrame) -> TransformContext:
    return TransformContext(keys=DerivedKeyProvider(TEST_MASTER_KEY), key_domain="T/r/1", source=frame)


def _visits() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "person": ["a"] * 5 + ["b", "c", ""],
            "town": ["Turku"] * 6 + ["Salo", "Salo"],
            "los": ["100", "200", "300", "400", "500", "50", "9999", ""],
            "dispo": ["ward", "home", "home", "home", "home", "ward", "home", "ward"],
        }
    )


class TestBounding:
    def test_each_person_keeps_at_most_the_bound_and_missing_ids_are_separate_people(self) -> None:
        kept = bound_contributions(_visits(), "person", 2, np.random.default_rng(1))
        assert kept["person"].value_counts().to_dict() == {"a": 2, "b": 1, "c": 1, "": 1}

    def test_bound_must_be_positive(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            bound_contributions(_visits(), "person", 0, np.random.default_rng(1))


class TestNoise:
    def test_discrete_laplace_is_integer_centred_with_the_right_spread(self) -> None:
        noise = discrete_laplace(np.random.default_rng(7), sensitivity=2, epsilon=0.5, size=200_000)
        alpha = math.exp(-0.5 / 2)
        assert noise.dtype.kind == "i"
        assert abs(noise.mean()) < 0.1
        assert noise.var() == pytest.approx(2 * alpha / (1 - alpha) ** 2, rel=0.05)

    def test_rejects_meaningless_parameters(self) -> None:
        with pytest.raises(ValueError, match="epsilon"):
            discrete_laplace(np.random.default_rng(), 1, 0, 3)


class TestNoisyTable:
    def test_counts_cover_the_declared_domain_including_empty_cells(self) -> None:
        spec = Aggregate(
            name="by_town", table="v", epsilon=1000.0, reason="test",
            dimensions=[Dimension(column="town", domain=["Turku", "Salo", "Aura"])],
        )  # fmt: skip
        frame = _visits()
        table = noisy_table(frame, spec, DP, _ctx(frame), np.random.default_rng(0))
        assert dict(zip(table["town"], table["value"], strict=True)) == {"Turku": 6, "Salo": 2, "Aura": 0}

    def test_values_outside_the_domain_are_not_published(self) -> None:
        spec = Aggregate(
            name="t", table="v", epsilon=1000.0, reason="test", dimensions=[Dimension(column="town", domain=["Salo"])]
        )
        frame = _visits()
        assert noisy_table(frame, spec, DP, _ctx(frame), np.random.default_rng(0))["town"].tolist() == ["Salo"]

    def test_mean_is_clipped_to_public_bounds(self) -> None:
        spec = Aggregate(
            name="los", table="v", epsilon=1000.0, reason="test", dimensions=[Dimension(column="town")],
            measure=Measure(kind="mean", column="los", upper=1000),
        )  # fmt: skip
        frame = _visits()
        table = noisy_table(frame, spec, DP, _ctx(frame), np.random.default_rng(0)).set_index("town")
        assert table.loc["Turku", "value"] == pytest.approx(
            1550 / 6, abs=3
        )  # the sum still carries noise of a few units
        assert table.loc["Salo", "value"] == 1000  # 9999 clipped; the empty value is left out
        assert table.loc["Salo", "rows"] == 1

    def test_share_counts_the_listed_values(self) -> None:
        spec = Aggregate(
            name="admitted", table="v", epsilon=1000.0, reason="test", dimensions=[Dimension(column="town")],
            measure=Measure(kind="share", column="dispo", values=["ward"]),
        )  # fmt: skip
        frame = _visits()
        table = noisy_table(frame, spec, DP, _ctx(frame), np.random.default_rng(0)).set_index("town")
        assert table.loc["Turku", "value"] == pytest.approx(2 / 6, abs=0.01)

    def test_dimensions_reuse_generalisation(self) -> None:
        frame = pd.DataFrame({"person": ["a", "b"], "ts": ["2025-01-01 08:10", "2025-01-01 08:50"]})
        spec = Aggregate(
            name="hours", table="v", epsilon=1000.0, reason="test",
            dimensions=[Dimension(column="ts", name="hour", params={"to": "time", "unit": "time_of_day"})],
        )  # fmt: skip
        table = noisy_table(frame, spec, DP, _ctx(frame), np.random.default_rng(0))
        assert table.to_dict("records") == [{"hour": "08:00", "value": 2}]


class TestPlanContract:
    def test_aggregates_need_a_privacy_statement_and_fit_the_budget(self) -> None:
        agg = Aggregate(name="a", table="v", epsilon=0.6, reason="test", dimensions=[Dimension(column="town")])
        base = {"dataset": "d", "scenario_id": "S", "created_at": NOW, "aggregates": [agg]}
        with pytest.raises(ValidationError, match="differential_privacy"):
            Plan.model_validate(base)
        with pytest.raises(ValidationError, match="more than"):
            Plan.model_validate(base | {"differential_privacy": DP, "epsilon": 0.5})
        plan = Plan.model_validate(base | {"differential_privacy": DP, "epsilon": 1.0})
        assert plan.epsilon_spent == 0.6

    def test_measures_check_their_parameters(self) -> None:
        with pytest.raises(ValidationError, match="bounds"):
            Measure(kind="mean", column="los")
        with pytest.raises(ValidationError, match="values"):
            Measure(kind="share", column="dispo")


class TestLedger:
    def test_running_total_per_receiver_and_cap(self, tmp_path: Path) -> None:
        ledger = EpsilonLedger(tmp_path / "ledger.jsonl", cap=2.0)
        assert ledger.record("r1", "S2/public/w1", 1.0, NOW) == 1.0
        assert ledger.record("r2", "S2/public2/w1", 1.0, NOW) == 1.0  # another receiver
        assert ledger.record("r3", "S2/public/w2", 1.0, NOW) == 2.0
        with pytest.raises(BudgetExceededError, match="above the cap 2"):
            ledger.record("r4", "S2/public/w3", 0.5, NOW)
        assert [e.release_id for e in ledger.entries()] == ["r1", "r2", "r3"]
