"""Step 1, Detect: classify every column of a table by privacy role and subtype, with evidence and a basis.

Layers, in order (see docs/detection/DECISIONS.md):
  1. Format proof: a checker with a check digit or a strict format fires on most values (pets/checkers.py).
  2. Structure: unique per row → record key; a repeated identifier-like code → technical identifier.
  3. Value vocabularies: sex, language, municipality, trade unions, health words.
  4. Table context: a table that holds ICD-10 codes holds health records, so its clinical numbers are health data.
  5. Column names (Finnish, English, Swedish): used only when `use_names` is on, and only to decide between
     options the values leave open or to raise confidence. The unseen HR file has no meaningful names.

Every result carries `evidence` (what fired) and `basis` (source IDs from docs/detection/SOURCES.md).
The output CSV `dataset,table,column,privacy_role,subtype` is what `pets-eval detect` scores.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import pandas as pd

from . import checkers as C

ROLES = ["direct_identifier", "quasi_identifier", "sensitive_attribute", "technical_identifier",
         "free_text", "record_key", "non_sensitive"]
STRONG = 0.8   # share of values that must pass a format checker for it to decide the column


@dataclass
class Detection:
    dataset: str
    table: str
    column: str
    privacy_role: str
    subtype: str
    sure: float
    method: str                      # rule | name | context | llm
    evidence: str
    basis: list[str] = field(default_factory=list)
    needed_by: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- value vocabularies (work without column names)
SEX_VALUES = {"m", "f", "n", "x", "male", "female", "mies", "nainen", "man", "kvinna", "muu", "other", "unknown"}
LANG_VALUES = {"fi", "sv", "en", "ru", "et", "ar", "so", "fa", "de", "fr", "es", "uk", "suomi", "ruotsi", "englanti",
               "finnish", "swedish", "english", "svenska", "finska"}
# Municipalities of Southwest Finland (Varsinais-Suomi) and nearby, as they appear in the data.
MUNICIPALITIES = {m.lower() for m in """Turku Salo Kaarina Raisio Naantali Lieto Uusikaupunki Parainen Pargas Loimaa Masku
Mynämäki Nousiainen Rusko Paimio Sauvo Marttila Koski Aura Pöytyä Oripää Somero Laitila Vehmaa Taivassalo Kustavi Pyhäranta
Kemiönsaari Kimitoön Länsi-Turunmaa Helsinki Tampere Espoo Vantaa Pori Rauma non-resident""".split()}
UNION_WORDS = ("jhl", "tehy", "super", "pam", "tek", "pro", "ytn", "jyty", "akava", "sak", "sttk", "ay-", "ammattiliit",
               "liitto", "union")
HEALTH_WORDS = ("kipu", "kuume", "lääkär", "sairaus", "diagnoos", "migreeni", "masennus", "ahdistus", "leikkaus",
                "tulehdus", "pain", "fever", "diagnos", "injury", "fracture", "admitted", "ward", "sick", "symptom",
                "hoito", "potilas", "patient", "allerg", "astma", "diabet", "raskaus", "pregnan")
YES_NO = {"0", "1", "true", "false", "yes", "no", "y", "n", "kyllä", "ei", "ja", "nej"}

# ---------------------------------------------------------------- column-name hints (Finnish, English, Swedish)
NAME_HINTS = [  # (regex on the column name, role, subtype, basis)
    (r"birth|dob|syntym|födel", "quasi_identifier", "BIRTH_DATE", ["L-GDPR-R26"]),
    (r"(^|_)sex($|_)|gender|sukupuol|kön", "quasi_identifier", "SEX", ["L-GDPR-R26"]),
    (r"(^|_)age($|_)|(^|_)ikä|ålder", "quasi_identifier", "AGE", ["L-GDPR-R26"]),
    (r"postcode|zip|postal|postinum", "quasi_identifier", "POSTCODE", ["L-GDPR-R26"]),
    (r"municipal|(^|_)city|(^|_)town|kunta|kaupunki|kommun", "quasi_identifier", "MUNICIPALITY", ["L-GDPR-R26"]),
    (r"special_?support|disab|accessib|(^|_)tuki|esteettöm|second_language", "sensitive_attribute", "HEALTH_DATA", ["L-GDPR-9"]),
    (r"language|kieli|språk", "quasi_identifier", "LANGUAGE", ["L-GDPR-R26"]),
    (r"nationality|kansalais|citizenship", "quasi_identifier", "NATIONALITY", ["L-GDPR-R26"]),
    (r"occupation|job_?title|ammatti|nimike|profession", "quasi_identifier", "OCCUPATION", ["L-GDPR-R26"]),
    (r"employer|työnantaja|arbetsgivare", "quasi_identifier", "ORG_NAME", ["L-GDPR-R26"]),
    (r"icd|diagnos", "sensitive_attribute", "DIAGNOSIS_CODE", ["L-GDPR-9", "F-ICD10"]),
    (r"triage|disposition|readmit|(^|_)los($|_)|los_min|symptom|sick|sairaus|abnormal|lab_?value|(^|_)value$",
     "sensitive_attribute", "HEALTH_DATA", ["L-GDPR-9"]),
    (r"systolic|diastolic|(^|_)bp($|_)|heart|pulse|resp_?rate|spo2|temp_c|temperature|pain|weight|height|bmi",
     "sensitive_attribute", "MEASUREMENT", ["L-GDPR-9"]),
    (r"(^|_)grade$|arvosana|raw_points|grade_points|absence|excused|unexcused|late_arriv|poissa|student.*status",
     "sensitive_attribute",
     "EDUCATION_DATA", ["L-GDPR-R26"]),
    (r"union|ammattiliit|(^|_)ay_|religio|uskonto|ethnic|politic|sexual", "sensitive_attribute", "SOCIAL_DATA", ["L-GDPR-9"]),
    (r"medical|lääkinn|hälso|health", "sensitive_attribute", "HEALTH_DATA", ["L-GDPR-9"]),
    (r"income|salary|wage|palkka|(^|_)tulo|lön|default|garnish|ulosotto|kyc|(^|_)pep|credit_?score|debt|late_?pay|"
     r"payment_?plan|arrear|perintä|maksuhäiri",
     "sensitive_attribute", "FINANCIAL_DATA", ["L-GDPR-R26"]),
    (r"(^|_)mcc$|merchant_?category", "sensitive_attribute", "CATEGORY", ["L-GDPR-R26", "L-GDPR-9"]),
    (r"amount|(^|_)sum$|summa|belopp", "quasi_identifier", "FINANCIAL_DATA", ["L-GDPR-R26"]),
    (r"country|maa$|land$", "quasi_identifier", "LOCATION_NAME", ["L-GDPR-R26"]),
    (r"department|(^|_)office|(^|_)school|osasto|toimipiste|yksikkö", "quasi_identifier", "ORG_NAME", ["L-GDPR-R26"]),
    (r"(^|_)shift|vuoro|currency|valuutta", "quasi_identifier", "CATEGORY", ["L-GDPR-R26"]),
    (r"course|subject|programme|program$|class_?group|oppiaine|kurssi", "quasi_identifier", "EDUCATION_DATA", ["L-GDPR-R26"]),
    (r"expiry|exam_?session", "quasi_identifier", "DATE", ["L-GDPR-R26"]),
    (r"note|text|comment|description|message(?!_id)|subject$|complaint|body|kommentti|viesti|kuvaus|selite|attachment|command|path",
     "free_text", "FREE_TEXT", ["L-GDPR-4.1"]),
    (r"(^|_)name$|nimi|first_?name|last_?name|surname|given|holder_name|guardian\d?_name|agent_name|author_name",
     "direct_identifier", "PERSON_NAME", ["L-GDPR-4.1"]),
    (r"customer_?id|client_?id|asiakas", "technical_identifier", "CUSTOMER_ID", ["L-GDPR-4.1"]),
    (r"employee|staff|agent_id|physician_id|author_staff|henkilöstö|työntekijä", "technical_identifier", "EMPLOYEE_ID",
     ["L-GDPR-4.1"]),
    (r"student|learner|oppilas", "technical_identifier", "STUDENT_ID", ["L-GDPR-4.1"]),
    (r"patient_?id|potilas", "technical_identifier", "PATIENT_ID", ["L-GDPR-4.1"]),
    (r"account_?(id|no|num)|reference|contract|tilinro", "technical_identifier", "ACCOUNT_ID", ["L-GDPR-4.1"]),
    (r"(_|^)id$|_ref$|message_id|session|correlation", "technical_identifier", "RECORD_ID", ["L-GDPR-R26"]),
    (r"upn|user(name)?$|login|(^|_)user_", "technical_identifier", "USERNAME", ["L-GDPR-4.1"]),
]


def name_hint(col: str):
    c = col.lower()
    for pat, role, sub, basis in NAME_HINTS:
        if re.search(pat, c):
            return role, sub, basis
    return None


# ---------------------------------------------------------------- table context
def table_context(profiles: dict[str, dict], dataset: str | None, use_names: bool) -> set[str]:
    """What kind of records the table holds, from its values (and the dataset name when names are allowed)."""
    ctx = set()
    for p in profiles.values():
        if p["pass"].get("icd10", 0) >= STRONG and p.get("icd_letters", 0) >= 3:
            ctx.add("health")
    if use_names and dataset:
        if dataset in ("health",):
            ctx.add("health")
        if dataset in ("education",):
            ctx.add("education")
    return ctx


# ---------------------------------------------------------------- the classifier
def _det(dataset, table, col, role, sub, sure, method, evidence, basis):
    return Detection(dataset, table, col, role, sub, round(float(sure), 2), method, evidence, basis)


FORMAT_RULES = [  # (checker, role, subtype, basis, label for the evidence text)
    ("hetu", "direct_identifier", "NATIONAL_ID", ["L-GDPR-4.1", "L-FI-DPA", "F-HETU"], "Finnish ID code (check character verified)"),
    ("iban", "direct_identifier", "IBAN", ["L-GDPR-4.1", "F-IBAN"], "IBAN (mod-97 verified)"),
    ("payment_card", "direct_identifier", "PAYMENT_CARD", ["L-GDPR-4.1", "F-CARD"], "card number (Luhn verified)"),
    ("email", "direct_identifier", "EMAIL", ["L-GDPR-4.1", "F-EMAIL"], "e-mail address"),
    ("street_address", "direct_identifier", "STREET_ADDRESS", ["L-GDPR-4.1"], "street address"),
    ("plate", "direct_identifier", "LICENSE_PLATE", ["L-GDPR-4.1", "F-PLATE"], "vehicle registration plate"),
    ("gsrn", "technical_identifier", "METER_ID", ["L-GDPR-4.1", "F-GSRN"], "GS1 service relation number (check digit verified)"),
    ("mac", "technical_identifier", "MAC_ADDRESS", ["L-GDPR-4.1", "F-MAC", "L-FI-ECSA"], "MAC address"),
    ("ipv4", "technical_identifier", "IP_ADDRESS", ["L-CJEU-IP", "F-IP", "L-FI-ECSA"], "IPv4 address"),
    ("ipv6", "technical_identifier", "IP_ADDRESS", ["L-CJEU-IP", "F-IP", "L-FI-ECSA"], "IPv6 address"),
    ("user_agent", "technical_identifier", "USER_AGENT", ["L-GDPR-R26", "L-FI-ECSA"], "browser or app user agent"),
    ("hostname", "technical_identifier", "HOSTNAME", ["L-GDPR-R26", "L-FI-ECSA"], "device hostname"),
    ("icd10", "sensitive_attribute", "DIAGNOSIS_CODE", ["L-GDPR-9", "F-ICD10"], "ICD-10 diagnosis code"),
    ("url", "free_text", "URL", ["L-GDPR-R26"], "web address"),
    ("timestamp", "quasi_identifier", "TIMESTAMP", ["L-GDPR-R26"], "date and time"),
    ("coordinate", "quasi_identifier", "GPS_COORDINATE", ["L-GDPR-R26"], "GPS coordinate"),
]


def classify(col: str, p: dict, ctx: set[str], dataset: str, table: str, use_names: bool, position: int,
             people_table: bool = False) -> Detection:
    pas, n_unique, ur = p["pass"], p["n_unique"], p["unique_ratio"]
    nonempty = max(1, round(p["n"] * (1 - p["empty"])))
    hint = name_hint(col) if use_names else None
    D = lambda role, sub, sure, method, ev, basis: _det(dataset, table, col, role, sub, sure, method, ev, basis)  # noqa: E731
    pct = lambda k: f"{pas.get(k, 0):.0%} of sampled values"  # noqa: E731

    if p["empty"] >= 1.0:
        return D("non_sensitive", "OTHER", 0.3, "rule", "column is empty", [])
    if p["empty"] >= 0.8 and n_unique <= 20 and not (hint and hint[0] == "sensitive_attribute"):
        return D("non_sensitive", "CATEGORY", 0.5, "rule",
                 f"{p['empty']:.0%} empty with {n_unique} distinct values: a sparse label, not about a person", [])

    # 1. Format proof
    for key, role, sub, basis, label in FORMAT_RULES:
        if pas.get(key, 0) >= STRONG:
            if key == "coordinate" and not (10 <= p.get("num_median", 0) <= 180):
                continue  # 0.987 or 0.512 are confidences or readings, not latitudes or longitudes
            if key == "hostname" and pas.get("coded_id", 0) >= STRONG and not hint:
                continue
            if key == "icd10" and p.get("icd_letters", 0) < 3:
                continue  # codes like S01, S02 share one letter: school or site codes, not diagnoses
            return D(role, sub, pas[key], "rule", f"{pct(key)} are a {label}", basis)
    if pas.get("phone", 0) >= STRONG and pas.get("coordinate", 0) < 0.5 and pas.get("postcode", 0) < 0.5 and \
            (pas.get("number", 0) < 0.9 or any(str(s).startswith(("0", "+")) for s in p["samples"])):
        return D("direct_identifier", "PHONE", pas["phone"], "rule", f"{pct('phone')} are a phone number", ["L-GDPR-4.1", "F-PHONE"])
    if pas.get("person_name", 0) >= STRONG and n_unique >= 10 and pas.get("known_name", 0) >= 0.5:
        return D("direct_identifier", "PERSON_NAME", pas["person_name"], "rule",
                 f"{pct('person_name')} look like personal names and {pas['known_name']:.0%} contain a known first name",
                 ["L-GDPR-4.1"])
    if n_unique >= 10 and (pas.get("first_name", 0) >= 0.6 or pas.get("surname", 0) >= 0.6) and pas.get("number", 0) < 0.1:
        which = "first names" if pas.get("first_name", 0) >= 0.6 else "Finnish surnames"
        return D("direct_identifier", "PERSON_NAME", max(pas.get("first_name", 0), pas.get("surname", 0)), "rule",
                 f"most values are {which}; with the rest of the row they name a person", ["L-GDPR-4.1"])
    if pas.get("domain", 0) >= STRONG:
        return D("quasi_identifier", "URL", pas["domain"], "rule", f"{pct('domain')} are internet domains: browsing reveals interests",
                 ["L-GDPR-R26", "L-FI-ECSA"])
    if pas.get("free_text", 0) >= 0.5 and p["avg_len"] >= 25 and n_unique >= 30:
        return D("free_text", "FREE_TEXT", pas["free_text"], "rule",
                 f"{pct('free_text')} are sentences (average {p['avg_len']:.0f} characters)", ["L-GDPR-4.1", "L-GDPR-9"])

    # 2. Structure: identifiers and keys
    idlike = max(pas.get("uuid", 0), pas.get("hex_hash", 0), pas.get("coded_id", 0))
    digits_only = all(str(x).isdigit() for x in p["samples"]) and p["avg_len"] >= 10
    numeric_id = (pas.get("number", 0) >= STRONG and ur >= 0.98 and p["avg_len"] >= 5 and pas.get("coordinate", 0) < 0.5) \
        or digits_only
    if (idlike >= STRONG or numeric_id) and n_unique > 20:
        if ur >= 0.98 and position == 0:
            return D("record_key", "RECORD_ID", 0.85, "rule", f"identifier-like and unique in {ur:.0%} of rows, first column",
                     ["S-TAX"])
        if ur >= 0.98 and people_table:
            sub = hint[1] if hint and hint[0] == "technical_identifier" and hint[1] != "RECORD_ID" else "CUSTOMER_ID"
            return D("direct_identifier", sub, 0.7, "rule",
                     "unique number per row in a table that lists people (names or ID codes found): it identifies them directly",
                     ["L-GDPR-4.1"])
        sub = hint[1] if hint and hint[0] == "technical_identifier" else ("DEVICE_ID" if pas.get("uuid", 0) >= STRONG else "OTHER")
        if hint and hint[0] == "record_key":
            sub = "RECORD_ID"
        return D("technical_identifier", sub, 0.75, "rule" if not hint else "name",
                 f"identifier-like code repeated across rows ({n_unique} distinct): links records to a person or device",
                 ["L-GDPR-4.1", "L-GDPR-R26"])

    # 3. Dates (birth dates vs other dates)
    if pas.get("date", 0) >= STRONG:
        years = _years(p["samples_all"]) if "samples_all" in p else []
        birth = hint and hint[1] == "BIRTH_DATE"
        if not birth and years and (max(years) - min(years) >= 30) and pd.Series(years).median() < 2005:
            birth = True
        return D("quasi_identifier", "BIRTH_DATE" if birth else "DATE", pas["date"], "rule",
                 f"{pct('date')} are dates" + (" spread over decades, as birth dates are" if birth and not hint else ""),
                 ["L-GDPR-R26"])
    if pas.get("year_month", 0) >= STRONG:
        return D("quasi_identifier", "DATE", pas["year_month"], "rule", f"{pct('year_month')} are year-month periods", ["L-GDPR-R26"])

    vals = {str(s).strip().lower() for s in p.get("distinct", [])}
    # 4. Value vocabularies
    if vals and n_unique <= 6 and vals <= SEX_VALUES:
        return D("quasi_identifier", "SEX", 0.9, "rule", f"values are {sorted(vals)}: sex", ["L-GDPR-R26"])
    if vals and n_unique <= 30 and len(vals & LANG_VALUES) / len(vals) >= 0.8:
        return D("quasi_identifier", "LANGUAGE", 0.85, "rule", "values are language codes", ["L-GDPR-R26"])
    if vals and len(vals & MUNICIPALITIES) / len(vals) >= 0.6:
        return D("quasi_identifier", "MUNICIPALITY", 0.85, "rule", "values are Finnish municipalities", ["L-GDPR-R26"])
    if vals and n_unique <= 40 and sum(any(w in v for w in UNION_WORDS) for v in vals) / len(vals) >= 0.5:
        return D("sensitive_attribute", "SOCIAL_DATA", 0.7, "rule", "values name trade unions: union membership", ["L-GDPR-9"])
    if pas.get("postcode", 0) >= STRONG and n_unique < 2000:
        return D("quasi_identifier", "POSTCODE", pas["postcode"], "rule", f"{pct('postcode')} are 5-digit postal codes", ["L-GDPR-R26", "F-POST"])

    # 5. Column-name hints decide what the values leave open
    if hint:
        role, sub, basis = hint
        if role == "technical_identifier" and people_table and ur >= 0.98 and sub != "RECORD_ID":
            return D("direct_identifier", sub, 0.65, "name",
                     f"'{col}' is unique per person in a table that lists people: it identifies them directly", ["L-GDPR-4.1"])
        if role == "direct_identifier" and sub == "PERSON_NAME" and pas.get("person_name", 0) < 0.3:
            pass  # e.g. merchant_name: a name column whose values are not personal names
        elif role == "free_text" and p["avg_len"] < 12:
            pass
        else:
            return D(role, sub, 0.65, "name", f"column name '{col}' indicates {sub.replace('_', ' ').lower()}", basis)

    # 6. Table context: clinical numbers and codes in a health table are health data
    numeric = pas.get("number", 0) >= STRONG
    if "health" in ctx and numeric:
        return D("sensitive_attribute", "MEASUREMENT", 0.55, "context",
                 "table holds health records (diagnosis codes found), so its clinical numbers are health data", ["L-GDPR-9"])

    # 7. Defaults
    if numeric:
        return D("non_sensitive", "MEASUREMENT", 0.5, "rule", "numbers with no identifying format", [])
    if vals and vals <= YES_NO:
        return D("non_sensitive", "CATEGORY", 0.5, "rule", "yes/no flag", [])
    if n_unique <= 50:
        return D("non_sensitive", "CATEGORY", 0.5, "rule", f"{n_unique} categories", [])
    if pas.get("coded_id", 0) >= 0.5:
        return D("technical_identifier", "OTHER", 0.45, "rule", "mostly identifier-like codes", ["L-GDPR-R26"])
    return D("non_sensitive", "OTHER", 0.35, "rule", "no identifying pattern found", [])


def _years(samples) -> list[int]:
    out = []
    for s in samples:
        m = re.search(r"(\d{4})", str(s))
        if m:
            out.append(int(m.group(1)))
        else:
            m = re.match(r"^\d{1,2}[./]\d{1,2}[./](\d{2})$", str(s).strip())
            if m:
                y = int(m.group(1))
                out.append(1900 + y if y > 25 else 2000 + y)
    return out


def detect_table(df: pd.DataFrame, dataset: str, table: str, use_names: bool = True) -> list[Detection]:
    """Classify every column of one table. With use_names=False, column names are hidden (as in the unseen file)."""
    profiles = {}
    for col in df.columns:
        p = C.profile(df[col])
        s = df[col].astype(str).str.strip()
        s = s[(s != "") & (s.str.lower() != "nan")]
        p["distinct"] = s.unique()[:60].tolist() if s.nunique() <= 60 else []
        p["samples_all"] = s.sample(min(300, len(s)), random_state=0).tolist() if len(s) else []
        nums = pd.to_numeric(s.str.replace(",", ".", regex=False), errors="coerce").abs()
        p["num_median"] = float(nums.median()) if nums.notna().mean() > 0.8 else 0.0
        p["icd_letters"] = s.str.strip().str[:1].str.upper().nunique() if p["pass"].get("icd10", 0) >= STRONG else 0
        profiles[col] = p
    ctx = table_context(profiles, dataset, use_names)
    people = any(max(pr["pass"].get("hetu", 0), pr["pass"].get("person_name", 0) * pr["pass"].get("known_name", 0))
                 >= STRONG * 0.75 for pr in profiles.values())
    dets = [classify(col, profiles[col], ctx, dataset, table, use_names, i, people) for i, col in enumerate(df.columns)]
    return _not_about_people(dets, ctx)


PLACE_SUBTYPES = {"GPS_COORDINATE", "LOCATION_NAME", "MUNICIPALITY", "POSTCODE", "TIMESTAMP", "DATE"}


def _not_about_people(dets: list[Detection], ctx: set[str]) -> list[Detection]:
    """A table with no personal, device or account identifier at all describes places, equipment or weather
    (bus stops, sensors, IP ranges), not people. Its coordinates, places and times are not quasi-identifiers."""
    if "health" in ctx or any(d.privacy_role in ("direct_identifier", "technical_identifier", "free_text") for d in dets):
        return dets
    for d in dets:
        if d.privacy_role == "quasi_identifier" and d.subtype in PLACE_SUBTYPES:
            d.privacy_role, d.method, d.sure = "non_sensitive", "context", 0.6
            d.evidence += "; but the table has no personal, device or account identifiers, so it describes places or equipment"
            d.basis = ["L-GDPR-4.1"]
    return dets


def detect_dataset(folder, dataset: str, use_names: bool = True, nrows: int | None = 20000) -> list[Detection]:
    out = []
    for f in sorted(folder.glob("*.csv")):
        df = pd.read_csv(f, dtype=str, keep_default_na=False, nrows=nrows)
        out += detect_table(df, dataset, f.stem, use_names)
    return out


def to_frame(dets: list[Detection]) -> pd.DataFrame:
    return pd.DataFrame([asdict(d) for d in dets])
