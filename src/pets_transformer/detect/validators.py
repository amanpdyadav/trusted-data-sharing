"""Format validators. Each is small, pure and unit-tested. Add new ones with `VALIDATORS.register(...)`.

Finnish ID code (HETU), IBAN, e-mail, phone, payment card (Luhn, masked), IPv4, MAC, Finnish plate, UUID,
hex digest, Finnish property ID, ICD-10 code, URL.
"""

import re
from dataclasses import dataclass
from datetime import date

from pets_transformer.contracts import Subtype
from pets_transformer.detect.base import Validator
from pets_transformer.registry import Registry

VALIDATORS: Registry[str, Validator] = Registry("validator")


# ---------------------------------------------------------------- Finnish personal identity code (HETU)
_HETU_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})([-+A-FU-Y]?)(\d{3})([0-9A-Y])$")  # separator may be missing in exports
_HETU_LABEL = re.compile(r"^(hetu|henkilötunnus|henkilotunnus|htun|ssn)[\s:]+", re.IGNORECASE)  # "HETU 011180-941H"
_HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"
_HETU_CENTURY = {"+": 1800, **dict.fromkeys("-UVWXY", 1900), **dict.fromkeys("ABCDEF", 2000)}


@dataclass(frozen=True)
class HetuValidator:
    """DDMMYYCZZZQ: real birth date, century sign (may be missing in exports), number 002-999, mod-31 check.

    The 900-999 range (temporary codes, used by the synthetic data) is accepted: it is still a valid format.
    """

    name: str = "fi_hetu"
    subtype: Subtype = Subtype.NATIONAL_ID

    def is_valid(self, value: str) -> bool:
        m = _HETU_RE.match(_HETU_LABEL.sub("", value.strip()).upper())
        if not m:
            return False
        dd, mm, yy, sign, individual, check = m.groups()
        if int(individual) < 2:
            return False
        centuries = [_HETU_CENTURY[sign]] if sign else [1900, 2000]
        if not any(_valid_date(c + int(yy), int(mm), int(dd)) for c in centuries):
            return False
        return _HETU_CHECK[int(dd + mm + yy + individual) % 31] == check


def _valid_date(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------- IBAN (ISO 13616, mod-97)
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


@dataclass(frozen=True)
class IbanValidator:
    name: str = "iban"
    subtype: Subtype = Subtype.IBAN

    def is_valid(self, value: str) -> bool:
        s = value.replace(" ", "").upper()
        if not _IBAN_RE.match(s):
            return False
        digits = "".join(str(int(ch, 36)) for ch in s[4:] + s[:4])
        return int(digits) % 97 == 1


# ---------------------------------------------------------------- e-mail (typed form; spelled-out forms are text work)
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


@dataclass(frozen=True)
class EmailValidator:
    name: str = "email"
    subtype: Subtype = Subtype.EMAIL

    def is_valid(self, value: str) -> bool:
        return bool(_EMAIL_RE.match(value.strip()))


# ---------------------------------------------------------------- phone numbers (Finnish and international forms)
_PHONE_CHARS = re.compile(r"^\+?[\d\s\-()]+$")


@dataclass(frozen=True)
class PhoneValidator:
    """+358 50 123 4567, 040-1234567, 0401234567, 044 3571 097. Needs a country code or a trunk 0."""

    name: str = "phone"
    subtype: Subtype = Subtype.PHONE

    def is_valid(self, value: str) -> bool:
        v = value.strip()
        if not _PHONE_CHARS.match(v):
            return False
        digits = re.sub(r"\D", "", v)
        if v.startswith("+"):
            return 8 <= len(digits) <= 15
        return digits.startswith("0") and not digits.startswith("00") and 7 <= len(digits) <= 12


# ---------------------------------------------------------------- payment cards (Luhn), also masked first6+last4
_MASKED_CARD = re.compile(r"^\d{4,6}[*xX\s]{4,}\d{4}$|^[*xX]{4}[\s*xX]*\d{4}$")


@dataclass(frozen=True)
class PaymentCardValidator:
    name: str = "payment_card"
    subtype: Subtype = Subtype.PAYMENT_CARD

    def is_valid(self, value: str) -> bool:
        v = value.strip()
        if _MASKED_CARD.match(v):
            return True
        digits = re.sub(r"[\s-]", "", v)
        if not digits.isdigit() or not 13 <= len(digits) <= 19:
            return False
        total = 0
        for i, ch in enumerate(reversed(digits)):
            d = int(ch) * (2 if i % 2 else 1)
            total += d - 9 if d > 9 else d
        return total % 10 == 0


# ---------------------------------------------------------------- IPv4 addresses (CIDR ranges are reference data)
@dataclass(frozen=True)
class Ipv4Validator:
    name: str = "ipv4"
    subtype: Subtype = Subtype.IP_ADDRESS

    def is_valid(self, value: str) -> bool:
        parts = value.strip().split(".")
        return len(parts) == 4 and all(p.isdigit() and int(p) <= 255 and str(int(p)) == p for p in parts)


# ---------------------------------------------------------------- simple pattern checks (one class, many formats: DRY)
@dataclass(frozen=True)
class PatternValidator:
    name: str
    subtype: Subtype
    pattern: re.Pattern[str]

    def is_valid(self, value: str) -> bool:
        return bool(self.pattern.match(value.strip()))


PATTERNS = (
    PatternValidator("mac_address", Subtype.MAC_ADDRESS, re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")),
    PatternValidator("fi_plate", Subtype.LICENSE_PLATE, re.compile(r"^[A-ZÅÄÖ]{2,3}-[0-9*]{1,3}$")),
    PatternValidator(
        "uuid", Subtype.RECORD_ID, re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
    ),
    PatternValidator("hex_digest", Subtype.OTHER, re.compile(r"^([0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")),
    PatternValidator("fi_property_id", Subtype.PROPERTY_ID, re.compile(r"^\d{1,3}-\d{1,3}-\d{1,4}-\d{1,4}$")),
    PatternValidator(
        "fi_street_address",
        Subtype.STREET_ADDRESS,
        re.compile(r"^[^\W\d_][\w\-]+( [\w\-]+)* \d{1,4}( ?[A-Za-z])?( \d{1,3})?(, ?\d{5} [^\W\d_][\w\- ]*)?$"),
    ),
    PatternValidator("icd10", Subtype.DIAGNOSIS_CODE, re.compile(r"^[A-TV-Z]\d{2}(\.\d{1,2})?$")),
    PatternValidator("url", Subtype.URL, re.compile(r"^https?://\S+$")),
)

for _v in (
    HetuValidator(),
    IbanValidator(),
    EmailValidator(),
    PhoneValidator(),
    PaymentCardValidator(),
    Ipv4Validator(),
    *PATTERNS,
):
    VALIDATORS.register(_v.name, _v)
