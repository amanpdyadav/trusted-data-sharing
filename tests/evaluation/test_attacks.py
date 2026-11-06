import pandas as pd
import pytest

from evaluation.attacks import (
    AgedBetween,
    ArrivedBetween,
    AttackCase,
    Equals,
    Injured,
    StayedBetween,
    number_intervals,
    replay,
    time_intervals,
)

T0 = pd.Timestamp("2025-01-22 20:08")


class TestTimeIntervals:
    def test_exact_times_are_points(self) -> None:
        s, e = time_intervals(pd.Series(["2025-01-22 20:08:00", "2025-01-22 21:15:00"]))
        assert (s == e).all()

    def test_times_all_on_the_hour_mean_an_hour_bucket(self) -> None:
        s, e = time_intervals(pd.Series(["2025-01-22 20:00", "2025-01-22 21:00"]))
        assert (e - s == pd.Timedelta(hours=1)).all()

    @pytest.mark.parametrize(("value", "days"), [("2025-01-22", 1), ("2025-W04", 7), ("2025-01", 31), ("2025", 366)])
    def test_dates_weeks_months_years(self, value: str, days: int) -> None:
        s, e = time_intervals(pd.Series([value]))
        assert (e - s).iloc[0] == pd.Timedelta(days=days)


@pytest.mark.parametrize(
    ("value", "lo", "hi"),
    [("37", 37, 37), ("30-39", 30, 40), ("30\u201339", 30, 40), ("90+", 90, 130), ("120,5", 120.5, 120.5)],
)
def test_number_intervals(value: str, lo: float, hi: float) -> None:
    a, b = number_intervals(pd.Series([value]))
    assert (a.iloc[0], b.iloc[0]) == (lo, hi)


def test_unparseable_numbers_are_unknown() -> None:
    a, _ = number_intervals(pd.Series(["", "n/a"]))
    assert a.isna().all()


class TestClues:
    frame = pd.DataFrame(
        {
            "arrival_ts": ["2025-01-22 20:00", "2025-01-21 08:00", ""],
            "sex": ["F", "M", ""],
            "age": ["60-69", "50-59", "60-69"],
            "los_minutes": ["190", "30", "180-239"],
            "icd10_primary": ["S52", "J10", "T23"],
        }
    )

    def test_each_clue_keeps_rows_that_could_match(self) -> None:
        f = self.frame
        assert ArrivedBetween(T0 - pd.Timedelta(hours=1), T0, "t").matches(f).tolist() == [True, False, True]
        assert Equals("sex", "F", "f").matches(f).tolist() == [True, False, True]  # unknown sex stays in
        assert AgedBetween(60, 61, T0, "a").matches(f).tolist() == [True, False, True]
        assert StayedBetween(150, 210, "s").matches(f).tolist() == [True, False, True]
        assert Injured().matches(f).tolist() == [True, False, True]

    def test_age_from_birth_date(self) -> None:
        f = pd.DataFrame({"date_of_birth": ["1964-05-20", "1990-01-01"]})
        assert AgedBetween(60, 61, T0, "a").matches(f).tolist() == [True, False]

    def test_removed_column_means_clue_not_applicable(self) -> None:
        f = self.frame.drop(columns=["sex", "age", "los_minutes"])
        assert Equals("sex", "F", "f").matches(f) is None
        assert AgedBetween(60, 61, T0, "a").matches(f) is None
        assert StayedBetween(1, 2, "s").matches(f) is None
        assert Injured().matches(f.drop(columns=["icd10_primary"])) is None

    def test_injury_from_diagnosis_group(self) -> None:
        f = pd.DataFrame({"diagnosis_group": ["injury", "respiratory"]})
        assert Injured().matches(f).tolist() == [True, False]


def test_replay_reports_funnel_and_target() -> None:
    frame = TestClues.frame
    case = AttackCase("X", "scrap", "demo", "r1", (Equals("sex", "F", "female"), Equals("age", "60-69", "sixties")))
    r = replay(case, frame, ["r1", "r2", "r3"])
    assert [s.candidates for s in r.funnel] == [3, 2, 2]
    assert (r.candidates_left, r.target_among_candidates) == (2, True)
    skipped = replay(AttackCase("Y", "s", "d", "r1", (Equals("postcode", "20100", "pc"),)), frame)
    assert not skipped.funnel[1].applied
    assert skipped.target_among_candidates is None
