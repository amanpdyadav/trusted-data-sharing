"""Names, secrets and the combined redactor."""

import pytest

from pets_transformer.contracts import SpanLabel
from pets_transformer.text.base import SPAN_DETECTORS
from pets_transformer.text.cues import CueNameDetector, SecretCueDetector
from pets_transformer.text.known import KnownNameDetector, KnownNames
from pets_transformer.text.redactor import build_redactor

L = SpanLabel
KNOWN = KnownNames.from_values(["Matti Jousikangas", "Hilkka Aalto", "Tarmo Mäki", "Maanantai Testi"])


class TestKnownNames:
    def test_tokens_are_lowercased_and_skip_short_words_and_weekdays(self) -> None:
        assert "matti" in KNOWN
        assert "Jousikangas" in KNOWN
        assert "maanantai" not in KNOWN
        assert KnownNames.from_values(["Li Ng"]).tokens == frozenset()

    def test_full_name_found_even_in_lowercase_speech(self) -> None:
        spans = KnownNameDetector(KNOWN).find("nimellä hilkka aalto, kiitos")
        assert [(s.label, s.text) for s in spans] == [(L.PERSON, "hilkka aalto")]

    def test_single_word_needs_a_capital_letter(self) -> None:
        detector = KnownNameDetector(KNOWN)
        assert [s.text for s in detector.find("Kiitos Matti!")] == ["Matti"]
        assert detector.find("talo on mäki ylhäällä") == []

    def test_punctuation_splits_two_names(self) -> None:
        assert [s.text for s in KnownNameDetector(KNOWN).find("Matti, Hilkka")] == ["Matti", "Hilkka"]


class TestCues:
    @pytest.mark.parametrize(
        ("text", "name"),
        [
            ("Hej, jag heter Matilda Backman.", "Matilda Backman"),
            ("hello this is tarmo speaking", "tarmo"),
            ("soita tyttärelleni Fredrik huomenna", "Fredrik"),
            ("My name is Ann Lee", "Ann Lee"),
        ],
    )
    def test_name_after_a_cue(self, text: str, name: str) -> None:
        assert {s.text for s in CueNameDetector(KNOWN).find(text)} == {name}

    @pytest.mark.parametrize(
        ("text", "name"),
        [
            ("asiakaspalvelu matti puhelimessa", "matti"),
            ("kundtjänst det alltså är matti hur kan jag", "matti"),
            ("Hyvitys tehty. /KLAI", "KLAI"),
            ("Soittakaa minulle, t. Kalle Haukkamaa", "Kalle Haukkamaa"),
        ],
    )
    def test_name_before_a_cue_fillers_and_signatures(self, text: str, name: str) -> None:
        assert {s.text for s in CueNameDetector(KNOWN).find(text)} == {name}

    def test_ordinary_words_after_a_cue_stay(self) -> None:
        assert CueNameDetector(KNOWN).find("kiitos paljon avusta") == []

    def test_after_a_greeting_a_new_capitalised_word_must_stand_alone(self) -> None:
        assert CueNameDetector(KNOWN).find("Kiitos Aallokolle hyvästä palvelusta") == []
        assert [s.text for s in CueNameDetector(KNOWN).find("Hei Liisa! Miten menee")] == ["Liisa"]

    def test_secret_and_username_values(self) -> None:
        spans = SecretCueDetector().find("salasanani on Kesä2024! ja käyttäjätunnus ainov85.")
        assert [(s.label, s.text) for s in spans] == [(L.SECRET, "Kesä2024"), (L.USERNAME, "ainov85")]

    def test_hedged_secret_and_dotted_login(self) -> None:
        found = SecretCueDetector().find("salasana on varmaan kruejcy2ve, tunnus joonas.ylaaho")
        assert [(s.label, s.text) for s in found] == [(L.SECRET, "kruejcy2ve"), (L.USERNAME, "joonas.ylaaho")]

    def test_a_plain_word_after_a_cue_is_no_login_or_password(self) -> None:
        assert SecretCueDetector().find("käyttäjä valitti hitaudesta") == []
        assert SecretCueDetector().find("lösenordet med siffror") == []


class TestRedactor:
    def test_stateless_detectors_are_registered_for_plug_ins(self) -> None:
        for name in ("patterns", "spoken_numbers", "spelled_email", "secret_cues"):
            assert name in SPAN_DETECTORS

    def test_redacts_identifiers_and_keeps_context(self) -> None:
        r = build_redactor(["Hilkka Aalto"])
        text = "Kiitos Hilkka, soitan numeroon 040 123 4567 maanantaina Turussa kuumeen takia."
        assert r.redact(text) == "Kiitos [PERSON], soitan numeroon [PHONE] maanantaina Turussa kuumeen takia."

    def test_labels_can_be_narrowed_by_the_plan(self) -> None:
        r = build_redactor(["Hilkka Aalto"], labels=[L.PHONE])
        assert r.redact("Hilkka 040 123 4567") == "Hilkka [PHONE]"

    def test_works_without_known_names(self) -> None:
        assert build_redactor().redact("jag heter Saga Lind") == "jag heter [PERSON]"

    def test_empty_text(self) -> None:
        assert build_redactor().spans("") == []
