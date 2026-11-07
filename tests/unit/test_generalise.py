import pandas as pd
import pytest

from pets_transformer.contracts import Technique
from pets_transformer.keys import DerivedKeyProvider
from pets_transformer.transform import TRANSFORMS, TransformContext
from tests.conftest import TEST_MASTER_KEY

G = TRANSFORMS.get(Technique.GENERALISE)


def _ctx(source: pd.DataFrame | None = None) -> TransformContext:
    return TransformContext(
        DerivedKeyProvider(TEST_MASTER_KEY), "test", source if source is not None else pd.DataFrame()
    )


class TestAgeBand:
    born = pd.Series(["1964-05-20", "2020-01-01", "1930-02-02", "", "not a date"])
    arrived = pd.Series(["2025-01-22 20:08:00"] * 5)

    def test_age_at_arrival_in_ten_year_bands_with_top_code(self) -> None:
        ctx = _ctx(pd.DataFrame({"arrival_ts": self.arrived}))
        out = G.apply(self.born, {"to": "age_band", "reference_column": "arrival_ts"}, ctx)
        assert out.tolist() == ["60-69", "0-9", "80+", "", ""]

    def test_fixed_reference_date_and_custom_width(self) -> None:
        out = G.apply(self.born[:2], {"to": "age_band", "at": "2025-12-31", "width": 5, "top": 90}, _ctx())
        assert out.tolist() == ["60-64", "5-9"]

    def test_birthday_boundary(self) -> None:
        ctx = _ctx(pd.DataFrame({"t": ["2024-05-19", "2024-05-21"]}))
        out = G.apply(pd.Series(["1964-05-20", "1964-05-20"]), {"to": "age_band", "reference_column": "t"}, ctx)
        assert out.tolist() == ["50-59", "60-69"]  # turns 60 on 2024-05-20

    def test_missing_reference_column_is_a_clear_error(self) -> None:
        with pytest.raises(KeyError, match="arrival_ts"):
            G.apply(self.born, {"to": "age_band", "reference_column": "arrival_ts"}, _ctx())

    def test_top_must_be_multiple_of_width(self) -> None:
        with pytest.raises(ValueError, match="multiple"):
            G.apply(self.born, {"to": "age_band", "at": "2025-01-01", "width": 7, "top": 80}, _ctx())


class TestTime:
    ts = pd.Series(["2025-01-22 20:08:00", "2024-12-30 01:00:00", "", "2025-01-22T07:59"])

    @pytest.mark.parametrize(
        ("unit", "expected"),
        [
            ("week", ["2025-W04", "2025-W01", "", "2025-W04"]),  # 30 Dec 2024 is in ISO week 1 of 2025
            ("month", ["2025-01", "2024-12", "", "2025-01"]),
            ("day", ["2025-01-22", "2024-12-30", "", "2025-01-22"]),
            ("hour", ["2025-01-22 20:00", "2024-12-30 01:00", "", "2025-01-22 07:00"]),
            ("time_of_day", ["20:00", "01:00", "", "07:00"]),
        ],
    )
    def test_units(self, unit: str, expected: list[str]) -> None:
        assert G.apply(self.ts, {"to": "time", "unit": unit}, _ctx()).tolist() == expected

    def test_unknown_unit(self) -> None:
        with pytest.raises(ValueError, match="unknown time unit"):
            G.apply(self.ts, {"to": "time", "unit": "fortnight"}, _ctx())


def test_truncate_icd10_codes() -> None:
    out = G.apply(pd.Series(["S52.5", "J10.1", "R51", ""]), {"to": "truncate", "length": 3}, _ctx())
    assert out.tolist() == ["S52", "J10", "R51", ""]


def test_strategy_is_required_and_must_exist() -> None:
    with pytest.raises(ValueError, match=r"params\.to"):
        G.apply(pd.Series(["x"]), {}, _ctx())
    with pytest.raises(KeyError, match="no generalisation"):
        G.apply(pd.Series(["x"]), {"to": "blur"}, _ctx())


def test_input_is_never_modified() -> None:
    s = pd.Series(["S52.5"])
    G.apply(s, {"to": "truncate", "length": 3}, _ctx())
    assert s.tolist() == ["S52.5"]


def test_code_group_uses_the_longest_matching_prefix() -> None:
    params = {"to": "code_group", "groups": {"J10": "ILI", "J": "respiratory", "R07": "cardiovascular"}}
    codes = pd.Series(["J10.1", "j18.9", "R07.4", "Z03.9", ""])
    out = TRANSFORMS.get(Technique.GENERALISE).apply(codes, params, _ctx())
    assert out.tolist() == ["ILI", "respiratory", "cardiovascular", "other", ""]
