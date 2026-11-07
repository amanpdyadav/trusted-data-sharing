import pandas as pd
import pytest

from pets_transformer.contracts import EvidenceKind, PrivacyRole, Subtype
from pets_transformer.detect.names import hint_for, id_kind, tokens
from pets_transformer.detect.profile import profile_column
from pets_transformer.detect.rules import RuleBasedDetector, classify

R, S = PrivacyRole, Subtype
N = 60


def _classify(name: str, values: list[str], *, first: bool = False) -> tuple[PrivacyRole, Subtype]:
    role, sub, _, _ = classify(profile_column(name, pd.Series(values)), is_first=first)
    return role, sub


def _many(*values: str) -> list[str]:
    return [values[i % len(values)] for i in range(N)]


def test_tokens_split_snake_camel_and_punctuation() -> None:
    assert tokens("patientHetu_ID") == {"patient", "hetu", "id"}


def test_name_hints_respect_context_words() -> None:
    assert hint_for("patient_name").subtype is S.PERSON_NAME  # type: ignore[union-attr]
    assert hint_for("test_name") is None
    assert id_kind("customer_number") is S.CUSTOMER_ID
    assert id_kind("visit_id") is S.RECORD_ID
    assert id_kind("municipality") is None


@pytest.mark.parametrize(
    ("name", "values", "expected"),
    [
        ("c05", _many("131052-308T", "070889-9652", "251263-976J"), (R.DIRECT_IDENTIFIER, S.NATIONAL_ID)),
        ("x", _many("FI3890214253573875", "FI4797208992532468"), (R.DIRECT_IDENTIFIER, S.IBAN)),
        ("contact", _many("aino@mail.example", "040 123 4567", "bo@x.example"), (R.DIRECT_IDENTIFIER, S.EMAIL)),
        ("src", _many("10.0.5.60", "192.0.2.1"), (R.TECHNICAL_IDENTIFIER, S.IP_ADDRESS)),
        ("dx", _many("S52.5", "J10.1", "R51", "I21.4"), (R.SENSITIVE_ATTRIBUTE, S.DIAGNOSIS_CODE)),
    ],
)
def test_format_checks_decide_first(name: str, values: list[str], expected: tuple[PrivacyRole, Subtype]) -> None:
    assert _classify(name, values) == expected


def test_person_names_need_name_shaped_values() -> None:
    people = _many("Aino Virtanen", "Mika Ilmari Karppinen", "Oscar Lindberg")
    stations = _many("Kauppatori A", "Yliopistonmäki", "Kupittaan asema 2")
    assert _classify("holder_name", people) == (R.DIRECT_IDENTIFIER, S.PERSON_NAME)
    assert _classify("name", stations)[0] is not R.DIRECT_IDENTIFIER


def test_single_word_values_count_when_the_column_is_a_surname() -> None:
    assert _classify("last_name", _many("Kaskiaho", "Nylund", "Laakso")) == (R.DIRECT_IDENTIFIER, S.PERSON_NAME)


def test_school_codes_are_not_diagnoses() -> None:
    assert _classify("school_code", _many("S01", "S08", "S10"))[1] is not S.DIAGNOSIS_CODE


def test_date_column_with_a_text_word_in_its_name_is_not_free_text() -> None:
    assert _classify("note_date", _many("2022-08-15", "2023-01-02")) == (R.QUASI_IDENTIFIER, S.DATE)


def test_free_text_by_name_or_by_shape() -> None:
    notes = [f"Potilas kertoo kivusta kohdassa {i}, kotona yksin, soittaa tyttärelle illalla" for i in range(N)]
    assert _classify("note_text", notes) == (R.FREE_TEXT, S.FREE_TEXT)
    assert _classify("c22", notes) == (R.FREE_TEXT, S.FREE_TEXT)


def test_identifiers_by_name_and_uniqueness() -> None:
    unique = [f"ED25-{i:06d}" for i in range(N)]
    repeated = [f"ED25-{i % 30:06d}" for i in range(N)]
    assert _classify("visit_id", unique, first=True) == (R.RECORD_KEY, S.RECORD_ID)
    assert _classify("visit_id", repeated) == (R.TECHNICAL_IDENTIFIER, S.RECORD_ID)
    assert _classify("customer_number", [str(40000000 + i) for i in range(N)]) == (
        R.DIRECT_IDENTIFIER,
        S.CUSTOMER_ID,
    )


def test_a_few_valued_id_column_is_a_label() -> None:
    assert _classify("campaign_id", _many("C1", "C2", "")) == (R.NON_SENSITIVE, S.CATEGORY)


def test_value_shapes() -> None:
    assert _classify("c03", _many("2025-01-22 20:08:00", "2025-02-01 07:59:00")) == (R.QUASI_IDENTIFIER, S.TIMESTAMP)
    assert _classify("c09", _many("M", "F")) == (R.QUASI_IDENTIFIER, S.SEX)
    assert _classify("c10", _many("fi", "sv", "en")) == (R.QUASI_IDENTIFIER, S.LANGUAGE)
    assert _classify("c11", _many("3 987,96", "15,0", "120")) == (R.NON_SENSITIVE, S.MEASUREMENT)
    assert _classify("c12", _many("walk-in", "ambulance")) == (R.NON_SENSITIVE, S.CATEGORY)
    assert _classify("c13", [""] * N) == (R.NON_SENSITIVE, S.OTHER)


def test_reference_tables_have_no_quasi_identifiers() -> None:
    stops = pd.DataFrame(
        {
            "stop_id": [f"S{i:04d}" for i in range(N)],
            "lat": [f"60.45{i:02d}" for i in range(N)],
            "lon": [f"22.26{i:02d}" for i in range(N)],
        }
    )
    found = {c.column: c.privacy_role for c in RuleBasedDetector().detect("stops", stops)}
    assert found == {"stop_id": R.RECORD_KEY, "lat": R.NON_SENSITIVE, "lon": R.NON_SENSITIVE}


def test_every_decision_carries_evidence_and_art9_flag() -> None:
    frame = pd.DataFrame({"visit_id": [f"V{i}" for i in range(N)], "icd": _many("S52.5", "J10.1", "R51")})
    found = RuleBasedDetector().detect("visits", frame)
    assert all(c.evidence for c in found)
    icd = next(c for c in found if c.column == "icd")
    assert icd.special_category
    assert icd.evidence[0].kind is EvidenceKind.VALIDATOR


class TestExportsWithoutMeaningfulHeaders:
    """Production rule 1: company exports often arrive as c01..c26; values alone must do."""

    people = tuple(f"{s} {g}" for s in ("Virtanen", "Korhonen", "Nieminen", "Mäkinen", "Hämäläinen") for g in (
        "Aino", "Eetu", "Mika Matias", "Tiina Orvokki", "Oskari", "Sara", "Pekka", "Riitta", "Jari", "Laura",
        "Ville", "Anna", "Juha", "Emma", "Timo", "Elina", "Antti", "Noora", "Kalle", "Inka", "Olli", "Satu",
    ))  # fmt: skip

    def test_many_name_shaped_values_are_person_names(self) -> None:
        assert len(set(self.people)) >= 100
        assert _classify("c04", list(self.people)) == (R.DIRECT_IDENTIFIER, S.PERSON_NAME)

    def test_few_name_shaped_values_are_a_category(self) -> None:
        workplaces = _many("Kotihoito Runosmäki", "Kaarna Care toimisto", "Aallonhuippu palvelutalo") * 3
        assert _classify("c21", workplaces)[0] is R.NON_SENSITIVE

    def test_addresses_by_shape(self) -> None:
        addresses = [f"Mäntypolku {i}, 2{i:04d} Turku" for i in range(1, N + 1)]
        assert _classify("c07", addresses) == (R.DIRECT_IDENTIFIER, S.STREET_ADDRESS)

    def test_codes_repeated_per_person_are_still_identifiers(self) -> None:
        codes = [f"KC-{1000 + i % 150}" for i in range(600)]  # 150 people, 4 rows each
        assert _classify("c02", codes) == (R.TECHNICAL_IDENTIFIER, S.RECORD_ID)

    def test_hashes_are_treated_as_hashed_identifiers(self) -> None:
        hashes = [f"{i:064X}" for i in range(N)]
        assert _classify("c20", hashes) == (R.TECHNICAL_IDENTIFIER, S.RECORD_ID)

    def test_labelled_and_separator_less_id_codes(self) -> None:
        codes = _many("HETU 131052-308T", "200278907W", "070889-9652")
        assert _classify("c05", codes) == (R.DIRECT_IDENTIFIER, S.NATIONAL_ID)
