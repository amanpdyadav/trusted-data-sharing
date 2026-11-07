"""Unit tests for the format checkers: real-looking positives and near-miss negatives (synthetic values only)."""
import pytest

from pets import checkers as C


@pytest.mark.parametrize("v,ok", [
    ("131052-308T", True),    # valid check character
    ("131052-308U", False),   # wrong check character
    ("130702A989E", None),    # from the synthetic data: format valid, check decided by the algorithm
    ("010101Y0012", None),    # new 2023 century sign
    ("320152-308T", False),   # impossible date
    ("1310523-08T", False),
])
def test_hetu(v, ok):
    if ok is None:
        assert C.HETU_RE.match(v)
    else:
        assert C.is_hetu(v) is ok


def test_hetu_samples_from_data_pass():
    # real rows from the synthetic hospital data
    for v in ["280598-9800", "040386-945N", "100673-936A", "011239-964F", "170992-958V", "130702A989E"]:
        assert C.is_hetu(v), v


def test_iban():
    assert C.is_iban("FI2112345600000785")
    assert C.is_iban("FI21 1234 5600 0007 85")
    assert not C.is_iban("FI2112345600000786")
    assert not C.is_iban("FI21")


def test_payment_card():
    assert C.is_payment_card("4111111111111111")
    assert not C.is_payment_card("4111111111111112")
    assert not C.is_payment_card("0000000000000000")


def test_business_id():
    assert C.is_business_id("1572860-0")
    assert not C.is_business_id("1572860-1")


def test_phone():
    for v in ["050 238 8212", "050-2381979", "+358464120579", "+358 50 714 9637", "045-7902975", "+46701234567"]:
        assert C.is_phone(v), v
    for v in ["20100", "2025-01-01", "abc"]:
        assert not C.is_phone(v), v


def test_network():
    assert C.is_ipv4("100.78.105.158") and not C.is_ipv4("300.1.1.1") and not C.is_ipv4("1.2.3")
    assert C.is_mac("3C:45:93:FF:50:9B") and not C.is_mac("3C:45:93")
    assert C.is_ipv6("2001:db8::1")
    assert C.is_uuid("3c4593ff-509b-9a66-0792-1b8c3760ab53")
    assert C.is_hex_hash("6B77FF8C931B579DC693A9A9A482A4E49AA1D809")
    assert C.is_hostname("LT-MIKKAL-4465")
    assert C.is_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")


def test_health_and_places():
    assert C.is_icd10("S52.5") and C.is_icd10("J06") and not C.is_icd10("U2")
    assert C.is_postcode_fi("20100") and not C.is_postcode_fi("2010")
    assert C.is_street_address("Rinnetie 45 A 1, 20700 Turku")
    assert C.is_plate_fi("TZS-537")
    assert C.is_coordinate("60.45123")


def test_dates_names_numbers():
    assert C.is_date("15.7.1975") and C.is_date("15/02/90") and C.is_date("2025-01-01")
    assert C.is_timestamp("2025-01-01 08:03:00") and not C.is_timestamp("2025-01-01")
    assert C.is_person_name("Heino Arja Maria") and C.is_person_name("KIVISUO WILMA ELISABET")
    assert not C.is_person_name("Kaarna Care Oy")
    assert C.is_number("3 519,16") and C.is_number("14,5") and C.is_number("-2.5")
    assert C.is_coded_id("KC-5078") and C.is_coded_id("ED25-000002")


def test_hetu_messy_exports():
    # prefix and missing century sign, as in the unseen HR export (check character still verified)
    assert C.is_hetu("HETU 131052-308T")
    assert C.is_hetu("131052308T")
    assert not C.is_hetu("131052308U")
