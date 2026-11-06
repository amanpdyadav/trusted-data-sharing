import pandas as pd
import pytest

from pets_transformer.transform.suppress import suppress_to_k


def _frame() -> pd.DataFrame:
    # 5 women in Turku aged 30-39 (already safe), 3 men in Turku, 1 man in Salo, 1 woman in Salo aged 70-79
    return pd.DataFrame(
        {
            "sex": ["F"] * 5 + ["M"] * 3 + ["M", "F"],
            "municipality": ["Turku"] * 8 + ["Salo", "Salo"],
            "age": ["30-39"] * 5 + ["40-49"] * 3 + ["40-49", "70-79"],
            "diagnosis": list("ABCDEFGHIJ"),
        }
    )


def test_safe_rows_are_untouched_and_small_groups_blanked_least_important_first() -> None:
    r = suppress_to_k(_frame(), ["sex", "municipality", "age"], k=2)
    assert (
        r.frame.iloc[:5][["sex", "municipality", "age"]]
        .eq(_frame().iloc[:5][["sex", "municipality", "age"]])
        .all()
        .all()
    )
    assert r.cells_blanked["age"] == 2  # the two Salo rows lose their age first
    assert r.check is not None
    assert r.check.passes
    assert r.frame["diagnosis"].tolist()[:5] == list("ABCDE")  # non-QI columns are never changed


def test_leftover_rows_merge_into_one_blank_group_when_there_are_enough() -> None:
    r = suppress_to_k(_frame(), ["sex", "municipality", "age"], k=5)
    assert (r.rows_removed, len(r.frame)) == (0, 10)  # the 5 odd rows, fully blanked, form a group of 5
    assert r.check is not None
    assert r.check.passes


def test_rows_that_cannot_be_hidden_are_removed_and_counted() -> None:
    f = pd.DataFrame({"sex": ["F"] * 6 + ["M", "M"], "age": ["30-39"] * 6 + ["40-49", "90+"]})
    r = suppress_to_k(f, ["sex", "age"], k=5)
    assert (r.rows_removed, len(r.frame)) == (2, 6)  # two leftovers can never form a group of 5
    assert r.check is not None
    assert r.check.passes


def test_already_anonymous_table_is_returned_unchanged() -> None:
    f = _frame().iloc[:5]
    r = suppress_to_k(f, ["sex", "municipality", "age"], k=5)
    pd.testing.assert_frame_equal(r.frame, f)
    assert (r.cells_blanked, r.rows_removed) == ({}, 0)


def test_input_frame_is_not_modified() -> None:
    f = _frame()
    before = f.copy()
    suppress_to_k(f, ["sex", "age"], k=3)
    pd.testing.assert_frame_equal(f, before)


def test_no_quasi_identifiers_and_bad_k() -> None:
    assert suppress_to_k(_frame(), [], k=5).rows_removed == 0
    with pytest.raises(ValueError, match="at least 2"):
        suppress_to_k(_frame(), ["sex"], k=1)
