"""Scoring view for published statistics: workload answers and a sample drawn from published tables only."""

import pandas as pd
import pytest

from evaluation.dashboard import PublishedTable, answer, sample_visits, workload_answers

WEEKLY = PublishedTable(
    "weekly", "count", ("week", "diagnosis_group"),
    pd.DataFrame({"week": ["2025-W02", "2025-W02", "2025-W03"], "diagnosis_group": ["ILI", "injury", "ILI"],
                  "value": [3, 1, 0]}),
)  # fmt: skip
MONTHLY = PublishedTable(
    "monthly", "count", ("month", "age_band"),
    pd.DataFrame({"month": ["2025-01", "2025-01"], "age_band": ["0-9", "80+"], "value": [10, 0]}),
)  # fmt: skip
HOURLY = PublishedTable("hourly", "count", ("hour",), pd.DataFrame({"hour": ["08:00", "20:00"], "value": [5, 0]}))
STAY = PublishedTable(
    "stay", "mean", ("triage",), pd.DataFrame({"triage": ["A", "A"], "value": [100.0, 400.0], "rows": [3, 1]})
)
TABLES = [WEEKLY, MONTHLY, HOURLY, STAY]


def test_counts_add_up_published_cells() -> None:
    q = {"id": "HQ-ILI-2025-W02", "type": "count", "filters": {"week": "2025-W02", "diagnosis_group": "ILI"}}
    assert answer(q, TABLES) == 3
    q = {"id": "w", "type": "count", "filters": {"week": "2025-W02"}}
    assert answer(q, TABLES) == 4  # marginal over diagnosis groups


def test_means_are_weighted_by_published_row_counts() -> None:
    q = {"id": "HQ-LOS-A", "type": "mean", "value": "los", "filters": {"triage": "A"}}
    assert answer(q, TABLES) == pytest.approx((300 + 400) / 4)


def test_unanswerable_queries_are_missing_not_zero() -> None:
    assert pd.isna(answer({"id": "x", "type": "count", "filters": {"municipality": "Salo"}}, TABLES))
    q = {"id": "x", "type": "count", "filters": {"week": "2025-W09", "diagnosis_group": "ILI"}}
    assert pd.isna(answer(q, TABLES))
    table = workload_answers(TABLES, {"queries": [{"id": "x", "type": "mean", "value": "admitted", "filters": {}}]})
    assert table["id"].tolist() == ["x"]


def test_sample_has_one_row_per_published_visit_and_only_published_values() -> None:
    rows = sample_visits(TABLES, seed=1)
    assert len(rows) == 4
    assert set(rows["arrival_ts"].str[-5:]) == {"08:00"}  # the only hour with visits
    assert set(rows["age"]) == {"0-9"}
    assert rows["diagnosis_group"].value_counts().to_dict() == {"ILI": 3, "injury": 1}
    assert rows["arrival_ts"].iloc[0].startswith("2025-01-06")  # Monday of ISO week 2


def test_sample_needs_the_dashboard_tables() -> None:
    with pytest.raises(ValueError, match="hour"):
        sample_visits([WEEKLY, MONTHLY])
