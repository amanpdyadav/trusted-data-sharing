import pandas as pd
import pytest

from pets_transformer.contracts import Technique
from pets_transformer.keys import DerivedKeyProvider
from pets_transformer.transform import TRANSFORMS, TransformContext
from tests.conftest import TEST_MASTER_KEY


@pytest.fixture
def ctx() -> TransformContext:
    return TransformContext(keys=DerivedKeyProvider(TEST_MASTER_KEY), key_domain="HEALTH-S1/test-receiver/2026-11")


T = TRANSFORMS.get(Technique.PSEUDONYMISE)
VALUES = pd.Series(["131052-308T", "131052-308T", "070889-9652", ""])


def test_same_value_same_code_so_joins_survive(ctx: TransformContext) -> None:
    out = T.apply(VALUES, {}, ctx)
    assert out[0] == out[1] != out[2]
    assert len(out[0]) == 16


def test_missing_stays_missing(ctx: TransformContext) -> None:
    assert T.apply(VALUES, {}, ctx)[3] == ""


def test_original_value_never_appears(ctx: TransformContext) -> None:
    assert not set(T.apply(VALUES, {}, ctx)) & set(VALUES[:3])


def test_input_is_not_modified(ctx: TransformContext) -> None:
    before = VALUES.copy()
    T.apply(VALUES, {}, ctx)
    pd.testing.assert_series_equal(VALUES, before)


def test_other_receiver_gets_unlinkable_codes(ctx: TransformContext) -> None:
    other = TransformContext(keys=ctx.keys, key_domain="HEALTH-S1/other-receiver/2026-11")
    assert T.apply(VALUES, {}, ctx)[0] != T.apply(VALUES, {}, other)[0]


@pytest.mark.parametrize("length", [4, 65])
def test_unsafe_lengths_are_refused(ctx: TransformContext, length: int) -> None:
    with pytest.raises(ValueError, match="length"):
        T.apply(VALUES, {"length": length}, ctx)


def test_case_insensitive_option(ctx: TransformContext) -> None:
    out = T.apply(pd.Series(["Aino@Mail.example", "aino@mail.example"]), {"case_insensitive": True}, ctx)
    assert out[0] == out[1]
