"""The attacker's view and the usefulness checks, on small tables with known answers."""

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from pets_transformer.aggregate.cubes import noisy_table
from pets_transformer.assess.lookalikes import attacker_views, lookalikes, source_columns
from pets_transformer.assess.usefulness import column_changes, dp_accuracy
from pets_transformer.contracts import (
    Aggregate,
    ColumnAction,
    DifferentialPrivacy,
    Dimension,
    Plan,
    Technique,
)
from pets_transformer.keys import DerivedKeyProvider, KeyScope
from pets_transformer.transform import TransformContext
from tests.conftest import TEST_MASTER_KEY

NOW = datetime(2026, 11, 7, tzinfo=UTC)
SCOPE = KeyScope(DerivedKeyProvider(TEST_MASTER_KEY), "T/r/1")


def _plan() -> Plan:
    A = ColumnAction  # noqa: N806
    return Plan(
        dataset="toy", scenario_id="T", created_at=NOW, quasi_identifiers={"v": ["age", "town"]},
        actions=[
            A(table="v", column="born", technique=Technique.GENERALISE, params={"rename_to": "age"}, reason="test"),
            A(table="v", column="town", technique=Technique.KEEP, reason="test"),
            A(table="v", column="name", technique=Technique.DROP, reason="test"),
        ],
    )  # fmt: skip


RAW = pd.DataFrame({"born": ["1960", "1961", "1962", "1963"], "town": ["A", "A", "A", "B"], "name": list("wxyz")})
RELEASED = pd.DataFrame({"age": ["60+", "60+", "60+", "60+"], "town": ["A", "A", "A", "B"]})


def test_lookalike_buckets_and_guess_chance() -> None:
    v = lookalikes(RELEASED, ["age", "town"])
    assert v.unique_share == 0.25
    assert v.buckets["alone"] == 0.25
    assert v.buckets["2-4"] == 0.75
    assert v.guess_chance == pytest.approx((3 * (1 / 3) + 1) / 4)


def test_attacker_view_maps_released_names_back_to_source_columns() -> None:
    assert source_columns(_plan(), "v", ["age", "town"]) == ["born", "town"]
    (view,) = attacker_views(_plan(), {"v": RAW}, {"v": RELEASED})
    assert view.before.unique_share == 1.0
    assert view.after.unique_share == 0.25


def test_column_changes_report_withheld_and_coarsened_columns() -> None:
    changes = {c.column: c for c in column_changes(_plan(), "v", RAW, RELEASED)}
    assert changes["name"].released_as is None
    assert (changes["born"].released_as, changes["born"].distinct_before, changes["born"].distinct_after) == (
        "age",
        4,
        1,
    )
    assert changes["born"].top_after == [("60+", 1.0)]


def test_exact_table_and_accuracy_of_published_counts() -> None:
    frame = pd.DataFrame({"person": [str(i) for i in range(40)], "town": ["A"] * 30 + ["B"] * 10})
    spec = Aggregate(name="t", table="v", epsilon=1.0, reason="test", dimensions=[Dimension(column="town")])
    dp = DifferentialPrivacy(unit="person", max_rows_per_unit=1)
    ctx = TransformContext(keys=SCOPE.keys, key_domain=SCOPE.domain, source=frame)
    exact = noisy_table(frame, spec, dp, ctx, None)
    assert exact["value"].tolist() == [30, 10]
    published = exact.assign(value=[33, 10])
    plan = Plan(dataset="d", scenario_id="S", created_at=NOW, aggregates=[spec], differential_privacy=dp)
    (acc,) = dp_accuracy(plan, {"v": frame}, {"t": published}, SCOPE)
    assert acc.compared_cells == 2
    assert acc.mean_relative_error == pytest.approx(0.05)
    assert acc.within_10pct == 1.0
    assert noisy_table(frame, spec, dp, ctx, np.random.default_rng(0))["value"].tolist() != []
