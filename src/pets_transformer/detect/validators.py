"""Format validators. Each is small, pure and unit-tested. Add new ones with `VALIDATORS.register(...)`.

Starter set: Finnish personal identity code (HETU), IBAN, e-mail. Phone, card, plate, IP, MAC ... go here next.
"""

import re
from dataclasses import dataclass
from datetime import date

from pets_transformer.contracts import Subtype
from pets_transformer.detect.base import Validator
from pets_transformer.registry import Registry

VALIDATORS: Registry[str, Validator] = Registry("validator")


# ---------------------------------------------------------------- Finnish personal identity code (HETU)
_HETU_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})([-+A-FU-Y])(\d{3})([0-9A-Y])$")
_HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"
_HETU_CENTURY = {"+": 1800, **dict.fromkeys("-UVWXY", 1900), **dict.fromkeys("ABCDEF", 2000)}


@dataclass(frozen=True)
class HetuValidator:
    """DDMMYYCZZZQ: real birth date, century sign, individual number 002-999, mod-31 check character.

    The 900-999 range (temporary codes, used by the synthetic data) is accepted: it is still a valid format.
    """

    name: str = "fi_hetu"
    subtype: Subtype = Subtype.NATIONAL_ID

    def is_valid(self, value: str) -> bool:
        m = _HETU_RE.match(value.strip().upper())
        if not m:
            return False
        dd, mm, yy, sign, individual, check = m.groups()
        if int(individual) < 2:
            return False
        try:
            date(_HETU_CENTURY[sign] + int(yy), int(mm), int(dd))
        except ValueError:
            return False
        return _HETU_CHECK[int(dd + mm + yy + individual) % 31] == check


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


for _v in (HetuValidator(), IbanValidator(), EmailValidator()):
    VALIDATORS.register(_v.name, _v)
