"""Format checkers: does a single value look like a known kind of identifier or data?

Each checker takes one string and returns True or False. Each one names its standard; the IDs (F-HETU etc.) refer
to docs/detection/SOURCES.md. Checkers that have a check digit verify it, so random digits rarely pass.
`profile()` runs every checker over a column sample and returns the share of values that pass.
"""
from __future__ import annotations

import re
from datetime import date

import pandas as pd

# ---------------------------------------------------------------- identifiers with check digits
HETU_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})([-+A-FU-Y])(\d{3})([0-9A-Y])$")
HETU_CHECK = "0123456789ABCDEFHJKLMNPRSTUVWXY"
HETU_CENTURY = {"+": 1800, **{c: 1900 for c in "-YXWVU"}, **{c: 2000 for c in "ABCDEF"}}


HETU_LOOSE_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})(\d{3})([0-9A-Y])$")


def is_hetu(v: str) -> bool:
    """Finnish personal identity code, check character verified (F-HETU, DVV).

    Real exports are messy, so this also accepts a 'HETU ' prefix and codes with the century sign left out
    (e.g. '130473926A'). The check character covers only the date and individual number, so it still verifies.
    """
    s = re.sub(r"^(HETU|HTUNNUS|HENKILÖTUNNUS|SSN)[\s:]*", "", v.strip().upper())
    m = HETU_RE.match(s)
    if m:
        dd, mm, yy, sign, num, check = m.groups()
        centuries = [HETU_CENTURY[sign]]
    else:
        m = HETU_LOOSE_RE.match(s)
        if not m:
            return False
        dd, mm, yy, num, check = m.groups()
        centuries = [1900, 2000]
    if not any(_valid_date(c + int(yy), int(mm), int(dd)) for c in centuries):
        return False
    return HETU_CHECK[int(dd + mm + yy + num) % 31] == check


def _valid_date(y: int, m: int, d: int) -> bool:
    try:
        date(y, m, d)
        return True
    except ValueError:
        return False


def is_business_id(v: str) -> bool:
    """Finnish Business ID (Y-tunnus): 7 digits, '-', check digit (F-YTUNNUS)."""
    m = re.match(r"^(\d{7})-(\d)$", v.strip())
    if not m:
        return False
    r = sum(int(d) * w for d, w in zip(m.group(1), (7, 9, 10, 5, 8, 4, 2))) % 11
    return r != 1 and (0 if r == 0 else 11 - r) == int(m.group(2))


def is_iban(v: str) -> bool:
    """IBAN with mod-97 check, spaces allowed (F-IBAN, ISO 13616)."""
    s = re.sub(r"\s", "", v).upper()
    if not re.match(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$", s):
        return False
    n = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(n) % 97 == 1


def luhn(digits: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digits)):
        x = int(d) * (2 if i % 2 else 1)
        total += x - 9 if x > 9 else x
    return total % 10 == 0


CARD_IIN = re.compile(r"^(4|5[1-5]|2(2[2-9]|[3-6]\d|7[01]|720)|3[47]|35|6(011|5|4[4-9]|2))")


def is_payment_card(v: str) -> bool:
    """Payment card number: 13–19 digits, a card-network issuer prefix (Visa 4, Mastercard 51–55/2221–2720, Amex 34/37,
    JCB 35, Discover 6011/65, UnionPay 62) and the Luhn check (F-CARD, ISO/IEC 7812). Travel or loyalty card numbers
    that only pass Luhn are not payment cards."""
    s = re.sub(r"[\s-]", "", v)
    return s.isdigit() and 13 <= len(s) <= 19 and len(set(s)) > 1 and bool(CARD_IIN.match(s)) and luhn(s)


def is_gsrn(v: str) -> bool:
    """GS1 Global Service Relation Number, e.g. electricity metering points: 18 digits, GS1 mod-10 (F-GSRN)."""
    s = v.strip()
    if not (s.isdigit() and len(s) == 18):
        return False
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(s[:-1])))
    return (10 - total % 10) % 10 == int(s[-1])


# ---------------------------------------------------------------- contact and location
def is_phone(v: str) -> bool:
    """Finnish or international phone number (F-PHONE: Traficom numbering plan, ITU-T E.164)."""
    s = re.sub(r"[\s\-()/]", "", v.strip())
    if re.match(r"^\+\d{8,15}$", s):
        return True
    return bool(re.match(r"^0[1-9]\d{5,10}$", s)) and not re.match(r"^0\d{4}$", s)


def is_email(v: str) -> bool:
    """E-mail address (F-EMAIL, RFC 5322 simplified)."""
    return bool(re.match(r"^[\w.+%-]+@[\w-]+(\.[\w-]+)+$", v.strip()))


def is_postcode_fi(v: str) -> bool:
    """Finnish postal code: 5 digits (F-POST)."""
    return bool(re.match(r"^\d{5}$", v.strip()))


STREET_WORDS = ("katu", "tie", "kuja", "polku", "rinne", "väylä", "kaari", "raitti", "puistikko", "mäki", "ranta",
                "tori", "aukio", "katu", "gatan", "vägen", "gränd", "street", "road", "piha", "linja", "kulma", "niitty")


def is_street_address(v: str) -> bool:
    """Street address: a street name (Finnish/Swedish street word) followed by a house number."""
    s = v.strip().lower()
    return bool(re.match(r"^[a-zåäö .\-]+ \d+", s)) and any(w in s.split(",")[0] for w in STREET_WORDS)


def is_plate_fi(v: str) -> bool:
    """Finnish vehicle registration plate, e.g. ABC-123 (F-PLATE, Traficom vehicle register)."""
    return bool(re.match(r"^[A-ZÅÄÖ]{2,3}-\d{1,3}$", v.strip()))


def is_coordinate(v: str) -> bool:
    """Decimal GPS coordinate with at least 3 decimals (latitude or longitude)."""
    m = re.match(r"^-?(\d{1,3})\.(\d{3,})$", v.strip())
    return bool(m) and float(v) <= 180


# ---------------------------------------------------------------- network and devices
def is_ipv4(v: str) -> bool:
    """IPv4 address (F-IP, RFC 791)."""
    p = v.strip().split(".")
    return len(p) == 4 and all(x.isdigit() and 0 <= int(x) <= 255 and (x == "0" or not x.startswith("0")) for x in p)


def is_ipv6(v: str) -> bool:
    """IPv6 address (F-IP, RFC 4291)."""
    s = v.strip()
    return ":" in s and bool(re.match(r"^[0-9a-fA-F:]+$", s)) and 2 <= s.count(":") <= 7 and not is_mac(s)


def is_mac(v: str) -> bool:
    """MAC address, six hex octets (F-MAC, IEEE 802)."""
    return bool(re.match(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$", v.strip()))


def is_uuid(v: str) -> bool:
    return bool(re.match(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$", v.strip()))


def is_hex_hash(v: str) -> bool:
    """A hash or token: 32, 40 or 64 hex characters (MD5, SHA-1, SHA-256)."""
    return bool(re.match(r"^([0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$", v.strip()))


def is_url(v: str) -> bool:
    return bool(re.match(r"^(https?|ftp)://\S+$", v.strip(), re.I))


def is_user_agent(v: str) -> bool:
    s = v.strip()
    return bool(re.match(r"^[A-Za-z][\w.\-]*/\d[\w.]*( |$)", s)) and ("(" in s or "/" in s[s.find("/") + 1:] or len(s) < 60)


def is_hostname(v: str) -> bool:
    """Device hostname, e.g. LT-MIKKAL-4465, ws-0042.corp.example."""
    s = v.strip()
    return bool(re.match(r"^[A-Za-z]{2,4}-[A-Za-z0-9]{2,}(-[A-Za-z0-9]+)*$", s) and re.search(r"[A-Za-z]{4,}", s)) or \
        bool(re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.(local|corp|lan|internal)$", s.lower()))


def is_domain(v: str) -> bool:
    """Internet domain name, e.g. news.example.fi (visited sites reveal interests)."""
    s = v.strip().lower()
    if re.search(r"\.(exe|dll|ps1|bat|cmd|sh|py|msi|sys|bin|tmp|log|docx?|xlsx?|pdf|zip)$", s):
        return False  # file names, not domains
    return bool(re.match(r"^([a-z0-9-]+\.)+[a-z]{2,}$", s)) and not is_hostname(v) and not is_email(v)


# ---------------------------------------------------------------- health
def is_icd10(v: str) -> bool:
    """ICD-10 diagnosis code, e.g. S52.5, J06 (F-ICD10, WHO). Health data under GDPR Art. 9."""
    return bool(re.match(r"^[A-TV-Z]\d{2}(\.\d{1,2})?$", v.strip().upper()))


# ---------------------------------------------------------------- dates and times
DATE_PATTERNS = [r"^(0[1-9]|1[0-2])/\d{2}$", r"^\d{4}-\d{2}-\d{2}$", r"^\d{1,2}\.\d{1,2}\.\d{4}$", r"^\d{1,2}/\d{1,2}/\d{2,4}$", r"^\d{4}/\d{2}/\d{2}$",
                 r"^\d{1,2}\.\d{1,2}\.\d{2}$"]


def is_date(v: str) -> bool:
    s = v.strip()
    return any(re.match(p, s) for p in DATE_PATTERNS)


def is_timestamp(v: str) -> bool:
    """Date with a time of day, e.g. 2025-01-01 08:03:00 or 2025-01-01T08:03Z."""
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$", v.strip()))


def is_year_month(v: str) -> bool:
    return bool(re.match(r"^\d{4}-(0[1-9]|1[0-2])(/\d)?$|^\d{4}-W\d{2}$", v.strip()))


# ---------------------------------------------------------------- names and text
# Common Finnish and Finland-Swedish first names. Stand-in for the DVV first-name statistics, which are public.
FIRST_NAMES = {n.lower() for n in """Aada Aino Aleksi Anna Anne Anni Antti Ari Arja Arto Eemeli Eetu Eija Eino Elias Elina Ella
Emilia Emma Erkki Esa Essi Hanna Hannu Harri Heikki Heini Helena Helmi Henna Henri Iida Ilkka Ilona Inka Jaakko Janne Jari
Jarkko Jarmo Jenni Jesse Joel Johanna Jonna Jouko Juha Juho Jukka Julia Jussi Jyrki Kaarlo Kaisa Kalle Kari Katja Kati Kimmo
Kirsi Kristiina Lasse Laura Leena Leo Liisa Linnea Lotta Maija Marja Marjatta Marko Markku Martti Matias Matti Mervi Mika
Mikael Mikko Minna Mira Nea Niko Niina Noora Olli Onni Oona Oskari Outi Paavo Pasi Pauliina Pekka Petri Petteri Pia Pirjo
Raili Reijo Riikka Riitta Risto Ronja Saara Sami Sanna Sari Satu Seppo Siiri Silja Simo Sini Sirpa Sofia Suvi Taina Tapani
Tapio Tarja Teemu Terhi Tero Timo Tiina Toni Tuomas Tuula Tuomo Ulla Valtteri Veera Veikko Venla Ville Vilma Wilma Väinö
Aleksanteri Alexander Anders Axel Christer Elsa Emil Erik Fredrik Hugo Isak Johan Karl Lars Maria Mats Nils Oscar Per Stefan
Sven Viktor Amanda Elisabet Josefiina Kristian Antero Eemil Inkeri Orvokki Sakari Tapani Tuulikki Annikki Kaarina Hellevi""".split()}
SURNAME_ENDINGS = ("nen", "la", "lä", "nen", "sto", "mäki", "koski", "niemi", "salo", "aho", "oja", "vaara", "lahti",
                   "järvi", "kangas", "suo", "ranta", "linna", "virta", "lehto", "puro", "harju", "kallio", "luoto",
                   "berg", "ström", "holm", "lund", "qvist", "gren", "maa", "pää", "mo", "sola", "nummi", "vuori")


def is_first_name(v: str) -> bool:
    return v.strip().split(" ")[0].lower() in FIRST_NAMES


def is_surname(v: str) -> bool:
    s = v.strip()
    return bool(re.match(r"^[A-ZÅÄÖ][a-zåäö\-]{2,}$", s)) and s.lower().endswith(SURNAME_ENDINGS)


def has_known_name(v: str) -> bool:
    """At least one word is a known first name (separates 'Heino Arja Maria' from 'Warehouse Clerk')."""
    return any(t.lower() in FIRST_NAMES for t in v.replace(",", " ").split())


def is_person_name(v: str) -> bool:
    """Two to five alphabetic words, each capitalised or all upper case: 'Heino Arja Maria', 'KIVISUO WILMA'."""
    toks = v.strip().split()
    if not 2 <= len(toks) <= 5:
        return False
    return all(re.match(r"^[A-ZÅÄÖÉÜ][a-zåäöéüA-ZÅÄÖÉÜ'\-]+$", t) for t in toks) and not any(
        t.lower() in ("oy", "ab", "ky", "oyj", "ry", "ltd", "inc", "the", "and") for t in toks)


def is_free_text(v: str) -> bool:
    """Sentence-like text: long enough, several words."""
    s = v.strip()
    return len(s) >= 20 and s.count(" ") >= 3


def is_number(v: str) -> bool:
    """A number, including Finnish formats: '3 519,16', '14,5'."""
    s = v.strip().replace(" ", " ")
    return bool(re.match(r"^-?\d{1,3}( \d{3})*(,\d+)?$|^-?\d+([.,]\d+)?$", s))


def is_coded_id(v: str) -> bool:
    """An identifier-like code: letters + digits with a separator, e.g. KC-5078, VLR-5393160923, ED25-000002."""
    s = v.strip()
    return bool(re.match(r"^[A-Za-z]{1,6}\d{0,4}[-_]?\d{3,}$", s)) or bool(re.match(r"^[A-Za-z]{1,4}\d{5,}$", s))


CHECKERS = {
    "hetu": is_hetu, "business_id": is_business_id, "iban": is_iban, "payment_card": is_payment_card, "gsrn": is_gsrn,
    "phone": is_phone, "email": is_email, "postcode": is_postcode_fi, "street_address": is_street_address,
    "plate": is_plate_fi, "coordinate": is_coordinate, "ipv4": is_ipv4, "ipv6": is_ipv6, "mac": is_mac, "uuid": is_uuid,
    "hex_hash": is_hex_hash, "url": is_url, "user_agent": is_user_agent, "hostname": is_hostname, "icd10": is_icd10,
    "timestamp": is_timestamp, "date": is_date, "year_month": is_year_month, "person_name": is_person_name,
    "free_text": is_free_text, "number": is_number, "coded_id": is_coded_id, "domain": is_domain,
    "first_name": is_first_name, "surname": is_surname, "known_name": has_known_name,
}


def profile(values: pd.Series, sample: int = 400, seed: int = 0) -> dict:
    """Share of non-empty values passing each checker, plus basic statistics for the whole column."""
    s = values.astype(str).str.strip()
    nonempty = s[(s != "") & (s.str.lower() != "nan")]
    n = len(s)
    if nonempty.empty:
        return {"n": n, "empty": 1.0, "n_unique": 0, "unique_ratio": 0.0, "pass": {}, "avg_len": 0.0, "samples": []}
    smp = nonempty.sample(min(sample, len(nonempty)), random_state=seed) if len(nonempty) > sample else nonempty
    passes = {name: round(float(smp.map(fn).mean()), 3) for name, fn in CHECKERS.items()}
    nu = int(nonempty.nunique())
    return {
        "n": n, "empty": round(1 - len(nonempty) / n, 3), "n_unique": nu, "unique_ratio": round(nu / len(nonempty), 3),
        "avg_len": round(float(smp.str.len().mean()), 1), "pass": passes,
        "samples": smp.drop_duplicates().head(3).tolist(),
    }
