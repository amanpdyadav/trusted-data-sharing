"""Rule-based column detector. Works from column names and values only (production rule 1).

Per column, the first step that decides wins:
  1. format checks on the values (ID code, IBAN, card, e-mail, IP, ...): strongest evidence
  2. free text (a text-like name, or long and varied values with spaces)
  3. identifier columns by name ("..._id", "..._number") and uniqueness: row key, person identifier or link
  4. column-name hints (English, Finnish, Swedish), checked against the values
  5. value shape: dates and times, sex or language codes, row keys, numbers, categories, short codes
Then per table: in reference tables with no person-level columns (bus stops, sensors, weather) locations and
times are not quasi-identifiers. Every decision carries evidence a reviewer can check.
"""

from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from pets_transformer import __version__
from pets_transformer.contracts import ColumnDetection, DetectionReport, Evidence, EvidenceKind, PrivacyRole, Subtype
from pets_transformer.detect.names import hint_for, id_kind, tokens
from pets_transformer.detect.profile import ColumnProfile, profile_column
from pets_transformer.sources import TableSource

R, S, E = PrivacyRole, Subtype, EvidenceKind
Decision = tuple[PrivacyRole, Subtype, float, list[Evidence]]
Step = Callable[[ColumnProfile, bool], Decision | None]

# format -> (role, subtype, minimum share of matching values); dict order is the priority when several match.
# Contact details often come in mixed forms, so a majority match is enough to make the column identifying.
FORMATS: dict[str, tuple[PrivacyRole, Subtype, float]] = {
    "fi_hetu": (R.DIRECT_IDENTIFIER, S.NATIONAL_ID, 0.8),
    "iban": (R.DIRECT_IDENTIFIER, S.IBAN, 0.8),
    "payment_card": (R.DIRECT_IDENTIFIER, S.PAYMENT_CARD, 0.8),
    "email": (R.DIRECT_IDENTIFIER, S.EMAIL, 0.5),
    "mac_address": (R.TECHNICAL_IDENTIFIER, S.MAC_ADDRESS, 0.8),
    "ipv4": (R.TECHNICAL_IDENTIFIER, S.IP_ADDRESS, 0.8),
    "uuid": (R.TECHNICAL_IDENTIFIER, S.RECORD_ID, 0.8),
    "fi_plate": (R.DIRECT_IDENTIFIER, S.LICENSE_PLATE, 0.8),
    "fi_property_id": (R.DIRECT_IDENTIFIER, S.PROPERTY_ID, 0.8),
    "icd10": (R.SENSITIVE_ATTRIBUTE, S.DIAGNOSIS_CODE, 0.8),
    "url": (R.FREE_TEXT, S.URL, 0.8),
    "phone": (R.DIRECT_IDENTIFIER, S.PHONE, 0.6),
    "fi_street_address": (R.DIRECT_IDENTIFIER, S.STREET_ADDRESS, 0.8),
    # a column of hashes is treated as hashed identifiers: they reverse by hashing guesses (privacy-safe default)
    "hex_digest": (R.TECHNICAL_IDENTIFIER, S.RECORD_ID, 0.8),
}
SEX_VALUES = frozenset(("m", "f", "male", "female", "mies", "nainen", "man", "kvinna", "x", "u", "other", "muu"))
LANGUAGE_CODES = frozenset(("fi", "sv", "en", "ru", "et", "de", "fr", "es", "ar", "so", "fa", "zh", "se"))
SINGLE_NAME_WORDS = frozenset(("surname", "lastname", "firstname", "given", "first", "last", "sukunimi", "etunimi"))
ICD_MIN_CHAPTERS = 3  # real diagnosis columns use several ICD chapters; 'S01, S08' are school codes
LABEL_MAX_DISTINCT = 20  # an "id" column with this few values is a label (campaign, sensor), not a link
MANY_DISTINCT = 100  # this many different names or codes means people or records, not categories
PERSON_LEVEL = frozenset({R.DIRECT_IDENTIFIER, R.TECHNICAL_IDENTIFIER, R.FREE_TEXT})
REFERENCE_DEMOTE = frozenset({S.GPS_COORDINATE, S.LOCATION_NAME, S.MUNICIPALITY, S.POSTCODE, S.TIMESTAMP, S.DATE})


def _ev(kind: EvidenceKind, detail: str, score: float | None = None) -> Evidence:
    return Evidence(kind=kind, detail=detail, score=None if score is None else round(score, 3))


def _unique(p: ColumnProfile) -> bool:
    return p.unique_ratio > 0.99 and p.fill_ratio > 0.95


# ---------------------------------------------------------------- steps 1-4
def by_format(p: ColumnProfile, is_first: bool) -> Decision | None:
    for fmt, (role, sub, minimum) in FORMATS.items():
        rate = p.format_rates.get(fmt, 0.0)
        if rate < minimum:
            continue
        if fmt == "icd10" and len({v[:1] for v in p.sample}) < ICD_MIN_CHAPTERS:
            continue
        decided = R.RECORD_KEY if fmt == "uuid" and is_first and _unique(p) else role
        return decided, sub, rate, [_ev(E.VALIDATOR, f"{rate:.0%} of values pass the {fmt} format check", rate)]
    return None


def by_text(p: ColumnProfile, _: bool) -> Decision | None:
    if p.datetime_share >= 0.8:
        return None  # "note_date" holds dates, not text
    hint = hint_for(p.name)
    named = hint is not None and hint.role is R.FREE_TEXT and p.space_share >= 0.3
    long_varied = p.avg_len >= 30 and p.space_share >= 0.5 and p.unique_ratio >= 0.2
    if not (named or long_varied):
        return None
    evidence = [_ev(E.STATISTICS, f"text-like: average {p.avg_len:.0f} characters, {p.space_share:.0%} with spaces")]
    if named:
        evidence.append(_ev(E.NAME_HINT, f"name '{p.name}' suggests free text"))
    return R.FREE_TEXT, S.FREE_TEXT, 0.8 if named else 0.65, evidence


def by_identifier_name(p: ColumnProfile, is_first: bool) -> Decision | None:
    kind = id_kind(p.name)
    if kind is None or p.distinct <= LABEL_MAX_DISTINCT:
        return None
    stats = _ev(E.STATISTICS, f"{p.distinct} distinct values in {p.filled} filled rows")
    named = _ev(E.NAME_HINT, f"name '{p.name}' marks an identifier")
    if is_first and _unique(p):
        return R.RECORD_KEY, kind, 0.85, [named, stats, _ev(E.STATISTICS, "first column and unique: the row key")]
    if _unique(p) and kind in (S.CUSTOMER_ID, S.ACCOUNT_ID, S.EMPLOYEE_ID):
        why = "a second unique key per person (printed on documents): identifies on its own"
        return R.DIRECT_IDENTIFIER, kind, 0.7, [named, stats, _ev(E.STATISTICS, why)]
    return R.TECHNICAL_IDENTIFIER, kind, 0.75, [named, stats, _ev(E.STATISTICS, "links rows to a person or device")]


def by_name_hint(p: ColumnProfile, _: bool) -> Decision | None:
    hint = hint_for(p.name)
    if hint is None or hint.role is R.FREE_TEXT:
        return None  # free text is decided from the values in by_text, never from the name alone
    single_names = bool(tokens(p.name) & SINGLE_NAME_WORDS)  # "last_name": one word per value is normal
    contradicted = {
        S.PERSON_NAME: (p.name_word_share if single_names else p.person_name_share) < 0.6,
        S.BIRTH_DATE: p.datetime_share < 0.5,
        S.GPS_COORDINATE: p.numeric_share < 0.8,
    }
    if contradicted.get(hint.subtype, False):
        return None
    evidence = [_ev(E.NAME_HINT, f"name '{p.name}' suggests {hint.subtype.value.lower()}")]
    if hint.subtype is S.PERSON_NAME:
        evidence.append(_ev(E.STATISTICS, f"{p.person_name_share:.0%} of values are shaped like personal names"))
    return hint.role, hint.subtype, 0.7, evidence


def by_person_values(p: ColumnProfile, _: bool) -> Decision | None:
    """Exports without meaningful headers: many different values shaped like personal names."""
    if p.person_name_share < 0.8 or p.distinct < MANY_DISTINCT:
        return None
    why = f"{p.person_name_share:.0%} of {p.distinct} distinct values are shaped like personal names"
    return R.DIRECT_IDENTIFIER, S.PERSON_NAME, 0.6, [_ev(E.STATISTICS, why)]


# ---------------------------------------------------------------- step 5: value shape
def as_datetime(p: ColumnProfile, _: bool) -> Decision | None:
    if p.datetime_share < 0.8:
        return None
    sub = S.TIMESTAMP if p.time_share > 0.5 else S.DATE
    return R.QUASI_IDENTIFIER, sub, 0.6, [_ev(E.STATISTICS, f"{p.datetime_share:.0%} of values are dates or times")]


def as_code_set(p: ColumnProfile, _: bool) -> Decision | None:
    lowered = {v.lower() for v in p.sample}
    if p.distinct <= 4 and lowered <= SEX_VALUES:
        return R.QUASI_IDENTIFIER, S.SEX, 0.75, [_ev(E.STATISTICS, f"values look like sex codes: {sorted(lowered)}")]
    if p.distinct <= 12 and lowered <= LANGUAGE_CODES:
        why = f"values look like language codes: {sorted(lowered)}"
        return R.QUASI_IDENTIFIER, S.LANGUAGE, 0.7, [_ev(E.STATISTICS, why)]
    return None


def as_row_key(p: ColumnProfile, is_first: bool) -> Decision | None:
    if is_first and _unique(p):
        return R.RECORD_KEY, S.RECORD_ID, 0.6, [_ev(E.STATISTICS, "first column and unique: the row key")]
    return None


def as_number(p: ColumnProfile, _: bool) -> Decision | None:
    if p.numeric_share < 0.9:
        return None
    return R.NON_SENSITIVE, S.MEASUREMENT, 0.5, [_ev(E.STATISTICS, f"{p.numeric_share:.0%} numeric values")]


def as_category(p: ColumnProfile, _: bool) -> Decision | None:
    if p.distinct > 50 and p.unique_ratio >= 0.01:
        return None
    return R.NON_SENSITIVE, S.CATEGORY, 0.5, [_ev(E.STATISTICS, f"{p.distinct} distinct values: a category")]


def as_short_code(p: ColumnProfile, _: bool) -> Decision | None:
    if p.space_share >= 0.1 or p.avg_len >= 30 or p.numeric_share >= 0.9:
        return None
    if p.unique_ratio <= 0.3 and p.distinct < MANY_DISTINCT:
        return None  # few codes: a category; many codes repeated over rows: people with several records
    why = f"{p.distinct} distinct short codes without spaces: likely an identifier"
    return R.TECHNICAL_IDENTIFIER, S.RECORD_ID, 0.45, [_ev(E.STATISTICS, why)]


STEPS: tuple[Step, ...] = (
    by_format, by_text, by_identifier_name, by_name_hint, by_person_values,
    as_datetime, as_code_set, as_row_key, as_number, as_category, as_short_code,
)  # fmt: skip


def classify(p: ColumnProfile, is_first: bool) -> Decision:
    if p.filled == 0:
        return R.NON_SENSITIVE, S.OTHER, 0.3, [_ev(E.STATISTICS, "column is empty")]
    for step in STEPS:
        if (decision := step(p, is_first)) is not None:
            return decision
    return R.NON_SENSITIVE, S.OTHER, 0.3, [_ev(E.STATISTICS, "no stronger signal found")]


# ---------------------------------------------------------------- table context
def _demote_reference_table(found: list[ColumnDetection]) -> list[ColumnDetection]:
    """Bus stops, sensors, weather: no person-level column, so locations and times identify nobody."""
    if any(c.privacy_role in PERSON_LEVEL or c.subtype in (S.SEX, S.BIRTH_DATE) for c in found):
        return found
    why = _ev(E.STATISTICS, "reference table with no person-level columns: describes places or times only")
    return [
        c.model_copy(update={"privacy_role": R.NON_SENSITIVE, "evidence": [*c.evidence, why]})
        if c.privacy_role is R.QUASI_IDENTIFIER and c.subtype in REFERENCE_DEMOTE
        else c
        for c in found
    ]


class RuleBasedDetector:
    """Implements ColumnDetector."""

    def detect(self, table: str, frame: pd.DataFrame) -> list[ColumnDetection]:
        found = []
        for i, column in enumerate(frame.columns):
            role, sub, conf, evidence = classify(profile_column(str(column), frame[column]), is_first=i == 0)
            found.append(
                ColumnDetection(
                    table=table,
                    column=str(column),
                    privacy_role=role,
                    subtype=sub,
                    confidence=round(conf, 3),
                    special_category=role is R.SENSITIVE_ATTRIBUTE and sub in (S.HEALTH_DATA, S.DIAGNOSIS_CODE),
                    evidence=evidence,
                )
            )
        return _demote_reference_table(found)


def detect_source(source: TableSource, dataset: str, detector: RuleBasedDetector | None = None) -> DetectionReport:
    d = detector or RuleBasedDetector()
    columns = [c for t in source.table_names() for c in d.detect(t, source.read(t))]
    return DetectionReport(dataset=dataset, generated_at=datetime.now(UTC), tool_version=__version__, columns=columns)
