"""Typed identifiers and spoken numbers inside free text (fi/sv/en)."""

import pytest

from pets_transformer.contracts import SpanLabel
from pets_transformer.text.patterns import PatternDetector
from pets_transformer.text.spoken import SpelledEmailDetector, SpokenNumberDetector, cue_label

L = SpanLabel


def labels(detector: object, text: str) -> list[tuple[str, str]]:
    return [(s.label.value, s.text) for s in detector.find(text)]  # type: ignore[attr-defined]


class TestPatternDetector:
    @pytest.mark.parametrize(
        ("text", "label", "value"),
        [
            ("mail me at liisa.virtanen@example.fi please", L.EMAIL, "liisa.virtanen@example.fi"),
            ("hetu 131052-308T kirjattu", L.NATIONAL_ID, "131052-308T"),
            ("soita 040 123 4567 iltaisin", L.PHONE, "040 123 4567"),
            ("tili FI21 1234 5600 0007 85 on oikea", L.IBAN, "FI21 1234 5600 0007 85"),
            ("kortti **** **** **** 4242 hylättiin", L.PAYMENT_CARD, "**** **** **** 4242"),
            ("login from 192.168.10.4 failed", L.IP_ADDRESS, "192.168.10.4"),
            ("auto ABC-123 pihalla", L.LICENSE_PLATE, "ABC-123"),
            ("sopimus AT-4590407 päättyy", L.ACCOUNT_NUMBER, "AT-4590407"),
            ("asun Kauppakatu 12 B 4, 20100 Turku", L.ADDRESS, "Kauppakatu 12 B 4, 20100 Turku"),
            ("see https://portal.example/case/77.", L.URL, "https://portal.example/case/77"),
        ],
    )
    def test_finds_typed_values(self, text: str, label: SpanLabel, value: str) -> None:
        assert (label.value, value) in labels(PatternDetector(), text)

    def test_rejects_values_that_fail_the_shared_format_check(self) -> None:
        assert not [s for s in PatternDetector().find("arvo 131052-308X") if s.label is L.NATIONAL_ID]

    def test_a_cue_word_overrides_a_failed_check_digit(self) -> None:
        assert [s.text for s in PatternDetector().find("hetu 131052-308x") if s.label is L.NATIONAL_ID] == [
            "131052-308x"
        ]

    @pytest.mark.parametrize(
        ("text", "label", "value"),
        [
            ("kortilla joka päättyy 9717", L.PAYMENT_CARD, "9717"),
            ("osoite pappilakuja 52 a 2, 20800 turku", L.ADDRESS, "pappilakuja 52 a 2, 20800 turku"),
            ("tilille fi4595645672272828", L.IBAN, "fi4595645672272828"),
            ("Kone LT-JESKUL-8415 ei käynnisty", L.DEVICE_ID, "LT-JESKUL-8415"),
            ("tavoittaa +358  4 4 4 10 3312.", L.PHONE, "+358  4 4 4 10 3312"),
            ("Katsoin laskun 2521929543. Siinä", L.ACCOUNT_NUMBER, "2521929543"),
        ],
    )
    def test_speech_style_and_lowercase_values(self, text: str, label: SpanLabel, value: str) -> None:
        assert (label.value, value) in labels(PatternDetector(), text)

    def test_street_name_without_house_number_is_not_an_address(self) -> None:
        assert not [s for s in PatternDetector().find("ajoin Kauppakatua pitkin") if s.label is L.ADDRESS]

    def test_long_number_is_relabelled_by_the_words_before_it(self) -> None:
        found = labels(PatternDetector(), "laitteen imei 356938035643809 ei toimi")
        assert ("DEVICE_ID", "356938035643809") in found

    def test_ordinary_numbers_are_left_alone(self) -> None:
        assert PatternDetector().find("Hinta 12,50 euroa, 3 kpl, vuonna 2024.") == []


class TestSpokenNumbers:
    def test_finnish_spoken_phone_number(self) -> None:
        found = labels(SpokenNumberDetector(), "numeroni on nolla neljä viisi, kuusi seitsemän kahdeksan yksi kaksi")
        assert found == [("PHONE", "nolla neljä viisi, kuusi seitsemän kahdeksan yksi kaksi")]

    def test_id_code_with_spoken_separator_and_check_letter(self) -> None:
        found = labels(SpokenNumberDetector(), "my id code is 140379 dash 910 6")
        assert found == [("NATIONAL_ID", "140379 dash 910 6")]

    def test_spelled_check_letter_ends_the_id_code(self) -> None:
        text = "hetu on yksi kuusi nolla viisi seitsemän kuusi viiva yhdeksän viisi kolme pee kiitos"
        assert labels(SpokenNumberDetector(), text)[0] == (
            "NATIONAL_ID",
            "yksi kuusi nolla viisi seitsemän kuusi viiva yhdeksän viisi kolme pee",
        )

    def test_pin_read_aloud_is_a_secret(self) -> None:
        assert labels(SpokenNumberDetector(), "PIN-koodi on yksi kaksi kolme neljä") == [
            ("SECRET", "yksi kaksi kolme neljä")
        ]

    def test_swedish_customer_number(self) -> None:
        found = labels(SpokenNumberDetector(), "mitt kundnummer är fyra två noll noll åtta sju")
        assert found == [("ACCOUNT_NUMBER", "fyra två noll noll åtta sju")]

    def test_short_or_typed_only_numbers_are_ignored(self) -> None:
        assert SpokenNumberDetector().find("kaksi kolme lasta") == []
        assert SpokenNumberDetector().find("tilaus 123456 saapui") == []  # typed digits belong to PatternDetector

    def test_cue_label_falls_back_to_default(self) -> None:
        assert cue_label("hello there ", 12, L.ACCOUNT_NUMBER) is L.ACCOUNT_NUMBER


class TestSpelledEmail:
    @pytest.mark.parametrize(
        "text",
        [
            "se on hilkka alaviiva aalto ät aurapost piste example",
            "it's nataliia dot boiko at mailbox dot example",
            "min adress är saga punkt lind snabel-a post punkt example",
        ],
    )
    def test_spelled_out_addresses(self, text: str) -> None:
        assert [s.label for s in SpelledEmailDetector().find(text)] == [L.EMAIL]

    def test_plain_sentence_with_at_is_not_an_email(self) -> None:
        assert SpelledEmailDetector().find("I'll be at home tonight") == []
