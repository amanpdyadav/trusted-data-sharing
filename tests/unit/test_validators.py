import pytest

from pets_transformer.detect.base import match_rate
from pets_transformer.detect.validators import VALIDATORS, EmailValidator, HetuValidator, IbanValidator


class TestHetu:
    v = HetuValidator()

    @pytest.mark.parametrize(
        "value",
        [
            "131052-308T",  # official example format from the Finnish population register
            "070889-9652",  # synthetic package values (temporary 900-999 range)
            "251263-976J",
            "271206A922C",  # 2000s century sign
            "200564-966L",
            " 220468-9631 ",  # surrounding spaces are tolerated
        ],
    )
    def test_accepts_valid_codes(self, value: str) -> None:
        assert self.v.is_valid(value)

    @pytest.mark.parametrize(
        ("value", "why"),
        [
            ("131052-308U", "wrong check character"),
            ("310252-308T", "31 February does not exist"),
            ("131052-001T", "individual number below 002"),
            ("131052Z308T", "unknown century sign"),
            ("131052-308", "too short"),
            ("", "empty"),
        ],
    )
    def test_rejects_invalid_codes(self, value: str, why: str) -> None:
        assert not self.v.is_valid(value), why


class TestIban:
    v = IbanValidator()

    @pytest.mark.parametrize(
        "value",
        ["FI3890214253573875", "FI45 9342 5809 1251 95", "fi4797208992532468", "GB82WEST12345698765432"],
    )
    def test_accepts_valid(self, value: str) -> None:
        assert self.v.is_valid(value)

    @pytest.mark.parametrize("value", ["FI3890214253573876", "FI38", "1234567890123456", ""])
    def test_rejects_invalid(self, value: str) -> None:
        assert not self.v.is_valid(value)


@pytest.mark.parametrize(
    ("value", "ok"),
    [("aino.v@kotiposti.example", True), ("a@b.co", True), ("aino at kotiposti", False), ("@x.fi", False)],
)
def test_email(value: str, ok: bool) -> None:
    assert EmailValidator().is_valid(value) is ok


def test_match_rate_ignores_empty_values() -> None:
    assert match_rate(["131052-308T", "", "nope"], HetuValidator()) == 0.5
    assert match_rate(["", ""], HetuValidator()) == 0.0


def test_builtins_are_registered_once() -> None:
    assert {"fi_hetu", "iban", "email"} <= {v.name for v in VALIDATORS}
    with pytest.raises(ValueError, match="already registered"):
        VALIDATORS.register("fi_hetu", HetuValidator())
