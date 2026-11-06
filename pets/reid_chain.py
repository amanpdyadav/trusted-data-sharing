"""Re-identification chain: start from one social media post and follow it across every dataset.

The story for the demo: each organisation releases its data the way most do, with names, ID codes, phone
numbers and street addresses removed. Starting from a single public post ("7 hours in the ER, bad headache"),
an attacker narrows the hospital's ED visits down to one patient, then pivots on the birth date and postcode
that the hospital left in, and joins the bank, the energy company, public transport and the school register.

Every step reports how many candidates are left. The ground truth (`truth/`) is used only to mark whether a
step picked the right person; the attacker never sees it. Everything is synthetic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

import pandas as pd
from pets_eval.utility.health import diagnosis_group

from . import DATA, PG_ROOT

ARRIVAL_WINDOW_H = (16, 1)  # posts appear up to ~16 h after arrival (and occasionally just before)

# Symptom words in a post → diagnosis group. Plain clinical common sense, in Finnish, English and Swedish.
# Order matters: the first group whose words appear wins.
SYMPTOM_GROUPS = [
    ("cardiovascular", ["rintakipu", "chest pain", "bröstsmärta", "sydämentykyty", "palpitation", "sudden breathlessness"]),
    ("allergy", ["ampiai", "huulten turpo", "kutisee", "wasp", "itch"]),
    ("endocrine", ["verensokeri", "blood sugar", "blodsocker"]),
    ("urological", ["virtsa", "urinat", "kylkikipu", "flank", "flanksmärta", "kissa"]),
    ("injury", ["kaatui", "fall", "fell", "slipped", "liukkaalla", "haava", "cut ", "cut finger", "viilsi", "nilkka",
                "ankle", "wrist", "ranne", "palovamma", "burn", "raketti", "olkapää", "shoulder", "fotled", "föll"]),
    ("musculoskeletal", ["selkä", "back pain", "ryggont"]),
    ("neurological", ["päänsärky", "headache", "huvudvärk", "kouristel", "seizure", "kramp", "näköhäiriö",
                      "voimattomuus", "weakness", "slurred"]),
    ("ILI", ["kotitesti", "home test", "lihaskiv", "body aches", "nuha", "runny nose"]),
    ("respiratory", ["hengenahdistus", "breathless", "wheez", "andnöd", "cough"]),
    ("gastrointestinal", ["vatsa", "abdominal", "ripuli", "diarrh", "oksentel", "vomit", "kylkikaaren", "quadrant", "magont"]),
    ("other_infection", ["korvakipu", "earache", "kuume 39", "high temperature"]),
    ("other", ["pyörtyi", "fainted", "svimmade", "huonovointi", "unwell", "mådde illa"]),
]


@dataclass
class Step:
    source: str          # which dataset or public source the attacker used
    clue: str            # what the attacker matched on, in plain words
    candidates: int      # how many records are still possible after this step
    correct: bool | None = None  # ground truth: is the real person still among the candidates / the unique match?


@dataclass
class Chain:
    post: dict
    clues: dict
    funnel: list[Step] = field(default_factory=list)
    visit: dict | None = None
    links: list[dict] = field(default_factory=list)   # one per dataset joined after the hospital
    dossier: dict = field(default_factory=dict)       # everything learned about the person
    identified: bool = False
    person_correct: bool | None = None


def _read(path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _with_truth(df: pd.DataFrame, dataset: str, table: str, key: str) -> pd.DataFrame:
    t = _read(PG_ROOT / "truth" / f"{dataset}__{table}.csv").rename(columns={"record_id": key, "adv_row_id": key})
    return df.merge(t, on=key, how="left")


@lru_cache(maxsize=1)
def _load() -> dict:
    """Load each dataset once. Direct identifiers stay in memory only for the ground-truth check, never for matching."""
    ed = _with_truth(_read(DATA / "health" / "ed_visits.csv"), "health", "ed_visits", "visit_id")
    ed = ed[ed.disposition != "cancelled_duplicate"].copy()
    ed["arrival"] = pd.to_datetime(ed.arrival_ts)
    ed["group"] = diagnosis_group(ed.icd10_primary).values
    posts = _with_truth(_read(PG_ROOT / "adversary" / "social_posts_health.csv"), "adversary", "social_posts_health", "adv_row_id")
    directory = _with_truth(_read(PG_ROOT / "adversary" / "public_directory.csv"), "adversary", "public_directory", "adv_row_id")
    directory["first"] = directory.name.str.split().str[0]
    students = _read(DATA / "education" / "students.csv")
    # Public first-name statistics stand-in: the sex most often carried by each first name.
    first = students.first_names.str.split().str[0]
    name_sex = students.assign(first=first).groupby("first").sex.agg(lambda s: s.mode().iat[0]).to_dict()
    return {
        "ed": ed, "posts": posts, "directory": directory, "name_sex": name_sex,
        "labs": _read(DATA / "health" / "lab_results.csv"),
        "notes": _read(DATA / "health" / "clinical_notes.csv"),
        "finance": _with_truth(_read(DATA / "finance" / "customers.csv"), "finance", "customers", "customer_id"),
        "energy": _with_truth(_read(DATA / "energy" / "customers.csv"), "energy", "customers", "customer_id"),
        "mobility": _with_truth(_read(DATA / "mobility" / "cards.csv"), "mobility", "cards", "card_id"),
        "students": _with_truth(students, "education", "students", "student_id"),
        "stops": _read(DATA / "mobility" / "stops.csv"),
    }


def symptom_group(text: str) -> str | None:
    t = text.lower()
    for group, words in SYMPTOM_GROUPS:
        if any(w in t for w in words):
            return group
    return None


def read_post(post: dict) -> dict:
    """What a person reading the post learns: name, home city, when, and what is wrong."""
    d = _load()
    parts = post["display_name"].split()
    first = parts[0] if parts else None
    hours = re.search(r"(\d+)\s*(?:hours|tuntia|timmar)", post["text"])
    return {
        "first_name": first,
        "full_name": post["display_name"] if len(parts) > 1 else None,
        "sex": d["name_sex"].get(first) if first else None,
        "city": post["profile_city"] or None,
        "posted": pd.Timestamp(post["posted_ts"]),
        "hours_in_er": int(hours.group(1)) if hours else None,
        "symptom_group": symptom_group(post["text"]),
    }


def _step(source, clue, cand: pd.DataFrame, truth_pid: str | None) -> Step:
    ok = None if truth_pid is None else bool((cand.person_id == truth_pid).any())
    return Step(source, clue, int(len(cand)), ok)


def run_chain(post_id: str) -> Chain:
    d = _load()
    post = d["posts"].set_index("adv_row_id").loc[post_id].to_dict() | {"adv_row_id": post_id}
    pid = post.get("person_id") or None
    c = read_post(post)
    chain = Chain(post=post, clues=c)
    ed = d["ed"]
    lo, hi = c["posted"] - pd.Timedelta(hours=ARRIVAL_WINDOW_H[0]), c["posted"] + pd.Timedelta(hours=ARRIVAL_WINDOW_H[1])

    chain.funnel.append(_step("Hospital ED visits (names removed)", "all visits in 2025", ed, pid))
    cand = ed[(ed.arrival >= lo) & (ed.arrival <= hi)]
    chain.funnel.append(_step("Social post", f"arrived within {ARRIVAL_WINDOW_H[0]} h before the post "
                              f"({c['posted']:%a %d %b %H:%M})", cand, pid))
    if c["city"]:
        cand = cand[cand.municipality == c["city"]]
        chain.funnel.append(_step("Social post", f"profile says they live in {c['city']}", cand, pid))
    if c["sex"]:
        cand = cand[cand.sex == c["sex"]]
        chain.funnel.append(_step("First-name statistics", f"'{c['first_name']}' is almost always "
                                  f"{'a woman' if c['sex'] == 'F' else 'a man'}'s name", cand, pid))
    if c["symptom_group"]:
        narrowed = cand[cand.group == c["symptom_group"]]
        if len(narrowed):
            cand = narrowed
            chain.funnel.append(_step("Social post", f"symptoms in the post point to: {c['symptom_group'].replace('_', ' ')} "
                                      "diagnosis", cand, pid))
    dir_hits = pd.DataFrame()
    if c["full_name"]:
        dir_hits = d["directory"][d["directory"].name == c["full_name"]]
        if c["city"]:
            dir_hits = dir_hits[dir_hits.city == c["city"]]
        if len(dir_hits):
            narrowed = cand[cand.postcode.isin(dir_hits.postcode)]
            if len(narrowed):
                cand = narrowed
                chain.funnel.append(_step("Public phone directory", f"'{c['full_name']}' is listed at postcode "
                                          f"{', '.join(sorted(dir_hits.postcode.unique()))}", cand, pid))
    # One person can have two visits in the window; the attacker cares about people, not visits.
    people = cand.drop_duplicates(["date_of_birth", "postcode", "sex"])
    if len(people) != 1:
        return chain
    v = cand.sort_values("arrival").iloc[-1]
    chain.identified = True
    chain.visit = v.to_dict()
    chain.person_correct = None if pid is None else v.person_id == pid
    _pivot(chain, v, d, dir_hits)
    return chain


def _pivot(chain: Chain, v: pd.Series, d: dict, dir_hits: pd.DataFrame) -> None:
    """From the unique hospital visit, join every other release on birth date and postcode."""
    dob, pc, true_pid = v.date_of_birth, v.postcode, v.person_id
    labs = d["labs"][d["labs"].visit_id == v.visit_id]
    notes = d["notes"][d["notes"].visit_id == v.visit_id]
    chain.dossier["Health"] = {
        "Birth date": dob, "Sex": v.sex, "Postcode": f"{pc} {v.municipality}",
        "Arrived": v.arrival_ts, "Triage": v.triage, "Complaint": v.chief_complaint,
        "Diagnosis": f"{v.icd10_primary} ({v.group.replace('_', ' ')})"
                     + (f" + {v.icd10_secondary}" if v.icd10_secondary else ""),
        "Lab tests": ", ".join(f"{r.test_name} {r.value} {r.unit}" for r in labs.head(6).itertuples()) or "none",
        "Doctor's note": notes.note_text.iat[0][:400] if len(notes) else "none",
        "Previous visits": int(((d["ed"].date_of_birth == dob) & (d["ed"].postcode == pc)).sum()) - 1,
    }

    def link(name, df, dob_col, pc_col, show: dict, how: str):
        m = df[(df[dob_col] == dob) & (df[pc_col] == pc)] if dob_col else df[df[pc_col] == pc]
        row = {"Dataset": name, "Joined on": how, "Matches": int(len(m)),
               "Correct": bool(len(m) == 1 and m.person_id.iat[0] == true_pid) if len(m) else None}
        chain.links.append(row)
        if len(m) == 1:
            chain.dossier[name] = {label: m[col].iat[0] for label, col in show.items() if m[col].iat[0] not in ("", None)}
        return m

    link("Bank", d["finance"], "birth_date", "postcode",
         {"Income": "income_band", "Occupation": "occupation", "Employer": "employer",
          "Customer since": "account_open_date", "Politically exposed": "pep_flag", "KYC risk": "kyc_risk"},
         "birth date + postcode")
    link("Energy company", d["energy"], "birth_date", "postcode",
         {"Heating": "heating_type", "Home size m²": "floor_area_m2", "EV charger": "ev_charger",
          "Solar kW": "solar_pv_kw", "Late payments": "late_payment_count",
          "Medical device at home": "medical_device_priority", "Meter ID": "metering_point_id"},
         "birth date + postcode")
    card = link("Public transport", d["mobility"], "holder_birth_date", "holder_postcode",
                {"Card type": "card_type", "Card issued": "issued_date", "Card number": "card_id"},
                "birth date + postcode")
    if len(card) == 1:
        _add_travel(chain, card.card_id.iat[0], d)
    link("School register", d["students"], "birth_date", "postcode",
         {"School": "school_name", "Programme": "programme", "Class": "class_group",
          "Special support": "special_support", "Home language": "home_language"},
         "birth date + postcode")

    # Last step: put a name and street address on it.
    dr = dir_hits if len(dir_hits) else d["directory"][(d["directory"].postcode == pc)
                                                       & (d["directory"]["first"] == chain.clues["first_name"])]
    row = {"Dataset": "Public phone directory", "Matches": int(len(dr)),
           "Joined on": "full name" if len(dir_hits) else "first name + postcode",
           "Correct": bool(len(dr) == 1 and dr.person_id.iat[0] == true_pid) if len(dr) else None}
    chain.links.append(row)
    if len(dr) == 1:
        chain.dossier["Identity"] = {"Name": dr.name.iat[0], "Street address": dr.street_address.iat[0],
                                     "City": f"{dr.postcode.iat[0]} {dr.city.iat[0]}", "Phone": dr.phone.iat[0] or "unlisted"}


def _add_travel(chain: Chain, card_id: str, d: dict) -> None:
    taps = _taps_for(card_id)
    if taps.empty:
        return
    stops = d["stops"].set_index("stop_id")
    top = taps.stop_id.value_counts().head(2)
    hours = pd.to_datetime(taps.ts).dt.hour
    chain.dossier["Public transport"]["Trips in data"] = len(taps)
    chain.dossier["Public transport"]["Most used stops"] = ", ".join(
        f"{stops.name.get(s, s)} ({stops.district.get(s, '')})" for s in top.index)
    chain.dossier["Public transport"]["Usual first tap"] = f"{int(hours.groupby(pd.to_datetime(taps.ts).dt.date).min().median()):02d}:00"


@lru_cache(maxsize=1)
def _taps() -> pd.DataFrame:
    return pd.read_csv(DATA / "mobility" / "taps.csv", dtype=str, usecols=["card_id", "ts", "stop_id"])


def _taps_for(card_id: str) -> pd.DataFrame:
    t = _taps()
    return t[t.card_id == card_id]


@lru_cache(maxsize=1)
def survey() -> pd.DataFrame:
    """Run the chain on every post: how often does a single post lead to one named person?"""
    rows = []
    for pid in _load()["posts"].adv_row_id:
        ch = run_chain(pid)
        joined = [l["Dataset"] for l in ch.links if l["Matches"] == 1 and l["Dataset"] != "Public phone directory"]
        named = any(l["Dataset"] == "Public phone directory" and l["Correct"] for l in ch.links)
        rows.append({"post": pid, "identified": ch.identified, "correct": bool(ch.person_correct),
                     "named": bool(ch.person_correct and named), "datasets_joined": len(joined),
                     "candidates_left": ch.funnel[-1].candidates, "steps": len(ch.funnel)})
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def _release() -> pd.DataFrame:
    from . import OUTPUTS
    r = _read(OUTPUTS / "health" / "ed_visits.csv")
    r["hour"] = pd.to_datetime(r.arrival_ts).dt.hour
    return r


def protected_funnel(chain: Chain) -> list[Step] | None:
    """The same attacker, same post, against our HEALTH-S1 release. None if the release has not been built."""
    from . import OUTPUTS
    if not (OUTPUTS / "health" / "ed_visits.csv").exists():
        return None
    r, c = _release(), chain.clues
    steps = [Step("Our release", "all released visits", len(r))]
    lo = c["posted"] - pd.Timedelta(hours=ARRIVAL_WINDOW_H[0])
    hours = {(lo + pd.Timedelta(hours=h)).hour for h in range(sum(ARRIVAL_WINDOW_H) + 1)}
    r = r[r.hour.isin(hours)]
    steps.append(Step("Social post", "arrival hour fits the post (the date is not released)", len(r)))
    if c["city"]:
        r = r[r.municipality == (c["city"] if c["city"] in set(_release().municipality) else "other")]
        steps.append(Step("Social post", f"lives in {c['city']}" + ("" if c["city"] in set(_release().municipality)
                                                                      else " (small towns are merged into 'other')"), len(r)))
    if c["sex"]:
        steps.append(Step("First-name statistics", "sex is not released, so this clue is useless", len(r)))
    if c["symptom_group"] and (r.diagnosis_group == c["symptom_group"]).any():
        r = r[r.diagnosis_group == c["symptom_group"]]
        steps.append(Step("Social post", f"{c['symptom_group'].replace('_', ' ')} diagnosis", len(r)))
    return steps
