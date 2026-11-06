"""Column-name hints in English, Finnish and Swedish. Weaker than format checks; used when values are ambiguous.

A hint fires when one of its words is a token of the column name ("patient_name" -> {"patient", "name"}).
Hints are tried in order; the first match wins. Add a language by adding words, not code.
"""

import re
from dataclasses import dataclass

from pets_transformer.contracts import PrivacyRole, Subtype

R = PrivacyRole
S = Subtype


@dataclass(frozen=True)
class Hint:
    words: frozenset[str]
    role: PrivacyRole
    subtype: Subtype
    unless: frozenset[str] = frozenset()  # context words that cancel the hint, e.g. "test_name" is not a person

    def matches(self, tokens: set[str]) -> bool:
        return bool(tokens & self.words) and not tokens & self.unless


def _h(words: str, role: PrivacyRole, subtype: Subtype, unless: str = "") -> Hint:
    return Hint(frozenset(words.split()), role, subtype, frozenset(unless.split()))


def tokens(column: str) -> set[str]:
    spaced = re.sub(r"([a-z])([A-Z])", r"\1 \2", column)
    return {t for t in re.split(r"[^a-zA-ZåäöÅÄÖ0-9]+", spaced.lower()) if t}


_NOT_A_PERSON = (
    "test location station stop sensor merchant course subject product file campaign rule process client "
    "device host school company network sv to org organisation project street"
)

HINTS: tuple[Hint, ...] = (
    # sensitive facts first, so "diagnosis_name" is not taken for a person
    _h(
        "diagnosis icd icd10 diagnoosi triage disposition readmit los abnormal medical accessibility health terveys",
        R.SENSITIVE_ATTRIBUTE,
        S.HEALTH_DATA,
    ),
    _h("systolic diastolic bp heart pulse resp spo2 pain temp kwh", R.SENSITIVE_ATTRIBUTE, S.MEASUREMENT),
    _h("income salary palkka tulot lön kyc late default debt cost", R.SENSITIVE_ATTRIBUTE, S.FINANCIAL_DATA),
    _h("pep", R.SENSITIVE_ATTRIBUTE, S.OTHER),
    # direct identifiers
    _h("hetu ssn personnummer henkilötunnus henkilotunnus", R.DIRECT_IDENTIFIER, S.NATIONAL_ID),
    _h("iban tilinumero kontonummer", R.DIRECT_IDENTIFIER, S.IBAN),
    _h("phone puhelin tel telefon mobile gsm matkapuhelin", R.DIRECT_IDENTIFIER, S.PHONE),
    _h("email mail sähköposti epost upn sender recipient recipients", R.DIRECT_IDENTIFIER, S.EMAIL),
    _h("address osoite adress", R.DIRECT_IDENTIFIER, S.STREET_ADDRESS),
    _h("plate rekisteri regno rekisterinumero", R.DIRECT_IDENTIFIER, S.LICENSE_PLATE),
    _h("pan", R.DIRECT_IDENTIFIER, S.PAYMENT_CARD),
    _h("property kiinteistö kiinteisto", R.DIRECT_IDENTIFIER, S.PROPERTY_ID),
    _h(
        "name names nimi namn surname lastname firstname given officer display sukunimi etunimi",
        R.DIRECT_IDENTIFIER,
        S.PERSON_NAME,
        unless=_NOT_A_PERSON,
    ),
    # quasi-identifiers
    _h("birth dob born syntymä syntymaaika födelse fodelse", R.QUASI_IDENTIFIER, S.BIRTH_DATE),
    _h("sex gender sukupuoli kön kon", R.QUASI_IDENTIFIER, S.SEX),
    _h("postcode zip postinumero postnummer", R.QUASI_IDENTIFIER, S.POSTCODE),
    _h("municipality kunta kommun city kaupunki stad town", R.QUASI_IDENTIFIER, S.MUNICIPALITY),
    _h("language lang kieli språk sprak", R.QUASI_IDENTIFIER, S.LANGUAGE),
    _h("occupation job ammatti yrke profession", R.QUASI_IDENTIFIER, S.OCCUPATION),
    _h("employer department työnantaja tyonantaja arbetsgivare osasto", R.QUASI_IDENTIFIER, S.ORG_NAME),
    _h("lat lon latitude longitude lng", R.QUASI_IDENTIFIER, S.GPS_COORDINATE),
    _h("station office country", R.QUASI_IDENTIFIER, S.LOCATION_NAME),
    # technical identifiers
    _h("agent", R.TECHNICAL_IDENTIFIER, S.USER_AGENT, unless="name id note"),
    _h("device", R.TECHNICAL_IDENTIFIER, S.HOSTNAME, unless="id"),
    _h("hostname host", R.TECHNICAL_IDENTIFIER, S.HOSTNAME),
    _h("mac", R.TECHNICAL_IDENTIFIER, S.MAC_ADDRESS),
    _h("ip", R.TECHNICAL_IDENTIFIER, S.IP_ADDRESS),
    # free text
    _h(
        "note notes text description message comment complaint subject kuvaus viesti muistiinpano anteckning",
        R.FREE_TEXT,
        S.FREE_TEXT,
    ),
)

# Words that mark an identifier column ("visit_id", "customer_number"), and what kind of identifier it is.
ID_WORDS = frozenset(["id", "ids", "number", "no", "nro", "numero", "tunnus", "ref", "reference", "key"])
ID_KINDS: tuple[tuple[frozenset[str], Subtype], ...] = (
    (frozenset(["customer", "asiakas", "kund"]), S.CUSTOMER_ID),
    (frozenset(["account", "contract", "reference", "tili", "sopimus"]), S.ACCOUNT_ID),
    (frozenset(["card", "kortti"]), S.CARD_ID),
    (frozenset(["device", "laite"]), S.DEVICE_ID),
    (frozenset(["staff", "agent", "physician", "employee", "author", "officer", "handler", "worker"]), S.EMPLOYEE_ID),
    (frozenset(["meter", "metering", "mittari"]), S.METER_ID),
)


def hint_for(column: str) -> Hint | None:
    t = tokens(column)
    return next((h for h in HINTS if h.matches(t)), None)


def id_kind(column: str) -> Subtype | None:
    """RECORD_ID-like subtype if the name says it is an identifier, else None."""
    t = tokens(column)
    if not t & ID_WORDS:
        return None
    return next((sub for words, sub in ID_KINDS if t & words), S.RECORD_ID)
