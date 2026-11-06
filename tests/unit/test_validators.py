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


class TestMoreFormats:
    @staticmethod
    def check(name: str, good: list[str], bad: list[str]) -> None:
        v = VALIDATORS.get(name)
        assert [x for x in good if not v.is_valid(x)] == [], f"{name} rejected valid values"
        assert [x for x in bad if v.is_valid(x)] == [], f"{name} accepted invalid values"

    def test_phone(self) -> None:
        self.check(
            "phone",
            ["+358505144700", "+358 50 286 4544", "040 241 2639", "050-3256767", "0402972898", "044 3571 097"],
            ["47109723", "668608828", "00358401234567", "040", "abc 123", "2025-01-22"],
        )

    def test_payment_card(self) -> None:
        self.check(
            "payment_card",
            ["4111111111111111", "5555552690897127", "4242 4242 4242 4242", "424242******3347", "XXXX XXXX XXXX 6030"],
            ["4111111111111112", "123456", "643768879334210272"],
        )

    def test_ipv4(self) -> None:
        self.check(
            "ipv4", ["10.10.2.169", "192.0.2.1", "100.64.208.146"], ["256.1.1.1", "10.0.0", "100.64.0.0/12", "1.02.3.4"]
        )

    def test_pattern_formats(self) -> None:
        self.check("mac_address", ["BA:9C:76:05:D7:A4", "5a-e3-1b-44-64-a3"], ["BA:9C:76:05:D7", "hello"])
        self.check("fi_plate", ["ATM-98", "DNK-830", "GKK-4**", "ÄÖK-1"], ["ABCD-123", "AT-4590407", "atm-98"])
        self.check("uuid", ["f72248af-5a30-46df-a509-f9ef751a7898"], ["f72248af5a3046df", "LT-JARHAA-8651"])
        self.check("hex_digest", ["a" * 32, "0f" * 20, "84da9d5560fd4a97" * 4], ["a" * 16, "g" * 32])
        self.check("fi_property_id", ["853-067-0003-0021", "445-412-3-77"], ["2025-01-22", "AU-TKU-13"])
        self.check("icd10", ["S52.5", "J10", "R51", "O20.0"], ["U07.1x", "S5", "52.5", "AT-4590407"])
        self.check("url", ["https://a.example/x?y=1", "http://b.example"], ["ftp://x", "a.example"])
