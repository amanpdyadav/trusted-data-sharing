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
                "ankle", "wrist", "ranne", "palovamma", "burn", "raketti", "olkapää", "shoulder", "fotled", "föll",
                "loukkaant", "palovamm", "ilotulit", "firework", "onnettomuu", "accident", "injured", "skadad"]),
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
    post: dict                                         # the public source row: a social post or a news clip
    clues: dict
    funnel: list[Step] = field(default_factory=list)
    visit: dict | None = None
    links: list[dict] = field(default_factory=list)   # one per dataset joined after the hospital
    dossier: dict = field(default_factory=dict)       # everything learned about the person
    identified: bool = False
    person_correct: bool | None = None
    source: str = "post"                               # "post" or "news"


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
    news = _with_truth(_read(PG_ROOT / "adversary" / "news_clips_health.csv"), "adversary", "news_clips_health", "adv_row_id")
    return {
        "ed": ed, "posts": posts, "news": news, "directory": directory, "name_sex": _name_sex(students),
        "labs": _read(DATA / "health" / "lab_results.csv"),
        "notes": _read(DATA / "health" / "clinical_notes.csv"),
        "finance": _with_truth(_read(DATA / "finance" / "customers.csv"), "finance", "customers", "customer_id"),
        "energy": _with_truth(_read(DATA / "energy" / "customers.csv"), "energy", "customers", "customer_id"),
        "mobility": _with_truth(_read(DATA / "mobility" / "cards.csv"), "mobility", "cards", "card_id"),
        "students": _with_truth(students, "education", "students", "student_id"),
        "stops": _read(DATA / "mobility" / "stops.csv"),
    }


def _hetu_sex(hetu: str) -> str | None:
    """Finnish ID codes encode sex in the individual number: odd is male, even is female."""
    try:
        return "M" if int(hetu[7:10]) % 2 else "F"
    except (ValueError, TypeError):
        return None


def _name_sex(students: pd.DataFrame) -> dict:
    """Stand-in for public first-name statistics (Finland publishes these): the sex most people with each first
    name have, taken from the ID codes in the bank and telecom customer lists and from the school register."""
    f = _read(DATA / "finance" / "customers.csv")
    c = _read(DATA / "customer_service" / "customers.csv")
    rows = pd.concat([
        pd.DataFrame({"first": f.full_name.str.split().str[0], "sex": f.hetu.map(_hetu_sex)}),
        pd.DataFrame({"first": c.full_name.str.split().str[0], "sex": c.hetu.map(_hetu_sex)}),
        pd.DataFrame({"first": students.first_names.str.split().str[0], "sex": students.sex}),
    ]).dropna()
    rows = rows[rows["first"] != ""]
    return rows.groupby("first").sex.agg(lambda s: s.mode().iat[0]).to_dict()


STAY_PATTERNS = [r"Spent (\d+) hours", r"Jo (\d+) tuntia", r"(\d+) timmar"]
STAY_TOLERANCE_H = (1.0, 0.5)  # the stated hours match the real length of stay within about half an hour


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
    stay = next((int(m.group(1)) for pat in STAY_PATTERNS if (m := re.search(pat, post["text"]))), None)
    return {
        "first_name": first,
        "full_name": post["display_name"] if len(parts) > 1 else None,
        "sex": d["name_sex"].get(first) if first else None,
        "city": post["profile_city"] or None,
        "posted": pd.Timestamp(post["posted_ts"]),
        "stay_hours": stay,
        "symptom_group": symptom_group(post["text"]),
    }


def _step(source, clue, cand: pd.DataFrame, truth_pid: str | None) -> Step:
    ok = None if truth_pid is None else bool((cand.person_id == truth_pid).any())
    return Step(source, clue, int(len(cand)), ok)


def run_chain(source_id: str) -> Chain:
    """Run the chain from a social post (POST…) or a news clip (NEWS…)."""
    if source_id.startswith("NEWS"):
        return run_news_chain(source_id)
    return run_post_chain(source_id)


def read_news(clip: dict) -> dict:
    """What a reader of the news clip learns: when, which town, age, sex, sometimes the hour and a name."""
    hour = re.search(r"kello (\d+)", clip["text"])
    age = pd.to_numeric(clip["age_mentioned"], errors="coerce")
    return {
        "date": pd.Timestamp(clip["event_date"]) if clip["event_date"] else None,
        "published": pd.Timestamp(clip["published_date"]),
        "hour": int(hour.group(1)) if hour else None,
        "city": clip["place"] or None,
        "sex": clip["sex_mentioned"] or None,
        "age": None if pd.isna(age) else int(age),
        "full_name": clip["name_mentioned"] or None,
        "first_name": clip["name_mentioned"].split()[0] if clip["name_mentioned"] else None,
        "symptom_group": symptom_group(clip["text"]),
    }


NEWS_AGE_TOLERANCE = 2  # "noin 40-vuotias" (about 40): the real age is within about two years


def _age_at(df: pd.DataFrame) -> pd.Series:
    dob = pd.to_datetime(df.date_of_birth, errors="coerce")
    return ((df.arrival - dob).dt.days / 365.25).round()


def run_news_chain(news_id: str) -> Chain:
    d = _load()
    clip = d["news"].set_index("adv_row_id").loc[news_id].to_dict() | {"adv_row_id": news_id}
    pid = clip.get("person_id") or None
    c = read_news(clip)
    chain = Chain(post=clip, clues=c, source="news")
    ed = d["ed"]
    chain.funnel.append(_step("Hospital ED visits (names removed)", "all visits in 2025", ed, pid))
    if c["date"] is not None:
        day = c["date"]
        cand = ed[ed.arrival.dt.normalize() == day]
        chain.funnel.append(_step("News clip", f"arrived on {day:%a %d %b %Y}, the day of the accident", cand, pid))
    else:
        lo = c["published"] - pd.Timedelta(days=2)
        cand = ed[(ed.arrival >= lo) & (ed.arrival < c["published"] + pd.Timedelta(days=1))]
        chain.funnel.append(_step("News clip", f"arrived in the 3 days up to publication ({c['published']:%d %b %Y})", cand, pid))
    if c["hour"] is not None:
        cand = cand[cand.arrival.dt.hour.isin([c["hour"], (c["hour"] + 1) % 24])]
        chain.funnel.append(_step("News clip", f"rescue services were called at {c['hour']}:00", cand, pid))
    if c["city"]:
        cand = cand[cand.municipality == c["city"]]
        chain.funnel.append(_step("News clip", f"it happened in {c['city']}", cand, pid))
    if c["sex"]:
        cand = cand[cand.sex == c["sex"]]
        chain.funnel.append(_step("News clip", "a woman" if c["sex"] == "F" else "a man", cand, pid))
    if c["age"] is not None:
        a = _age_at(cand)
        cand = cand[(a >= c["age"] - NEWS_AGE_TOLERANCE) & (a <= c["age"] + NEWS_AGE_TOLERANCE)]
        chain.funnel.append(_step("News clip", f"aged about {c['age']}", cand, pid))
    if c["symptom_group"]:
        narrowed = cand[cand.group == c["symptom_group"]]
        if len(narrowed):
            cand = narrowed
            chain.funnel.append(_step("News clip", f"{c['symptom_group'].replace('_', ' ')} diagnosis", cand, pid))
    dir_hits = pd.DataFrame()
    if c["full_name"]:
        dir_hits = d["directory"][d["directory"].name == c["full_name"]]
        narrowed = cand[cand.postcode.isin(dir_hits.postcode)] if len(dir_hits) else cand.iloc[:0]
        if len(narrowed):
            cand = narrowed
            chain.funnel.append(_step("Public phone directory", f"'{c['full_name']}' is listed at postcode "
                                      f"{', '.join(sorted(dir_hits.postcode.unique()))}", cand, pid))
    people = cand.drop_duplicates(["date_of_birth", "postcode", "sex"])
    if len(people) != 1:
        return chain
    v = cand.sort_values("arrival").iloc[-1]
    chain.identified, chain.visit = True, v.to_dict()
    chain.person_correct = None if pid is None else v.person_id == pid
    _pivot(chain, v, d, dir_hits)
    return chain


def run_post_chain(post_id: str) -> Chain:
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
    if c["stay_hours"]:
        cand = _stay_filter(cand, c["stay_hours"])
        chain.funnel.append(_step("Social post", f"stayed about {c['stay_hours']} hours (the post says so)", cand, pid))
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


def _stay_filter(df: pd.DataFrame, hours: int, col: str = "los_minutes") -> pd.DataFrame:
    los_h = pd.to_numeric(df[col], errors="coerce") / 60
    return df[(los_h >= hours - STAY_TOLERANCE_H[0]) & (los_h <= hours + STAY_TOLERANCE_H[1])]


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
    if not len(dir_hits) and not chain.clues.get("first_name"):
        return  # nobody is named and names are removed everywhere: the person stays unnamed
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
    d = _load()
    for pid in list(d["posts"].adv_row_id) + list(d["news"].adv_row_id):
        ch = run_chain(pid)
        joined = [l["Dataset"] for l in ch.links if l["Matches"] == 1 and l["Dataset"] != "Public phone directory"]
        named = any(l["Dataset"] == "Public phone directory" and l["Correct"] for l in ch.links)
        rows.append({"post": pid, "source": ch.source, "identified": ch.identified, "correct": bool(ch.person_correct),
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
    if chain.source == "news":
        return _protected_news(r, c, steps)
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
    if c.get("stay_hours"):
        r = _stay_filter(r, c["stay_hours"])
        steps.append(Step("Social post", f"stayed about {c['stay_hours']} hours (length of stay is released)", len(r)))
    return steps


def _protected_news(r: pd.DataFrame, c: dict, steps: list[Step]) -> list[Step]:
    steps.append(Step("News clip", "the date is not released, so every day of the year still fits", len(r)))
    if c["hour"] is not None:
        r = r[r.hour.isin([c["hour"], (c["hour"] + 1) % 24])]
        steps.append(Step("News clip", f"arrival hour {c['hour']}:00", len(r)))
    if c["city"]:
        towns = set(_release().municipality)
        r = r[r.municipality == (c["city"] if c["city"] in towns else "other")]
        steps.append(Step("News clip", f"{c['city']}" + ("" if c["city"] in towns else " (merged into 'other')"), len(r)))
    if c["sex"]:
        steps.append(Step("News clip", "sex is not released, so this clue is useless", len(r)))
    if c["age"] is not None:
        bands = {_band(a) for a in range(c["age"] - NEWS_AGE_TOLERANCE, c["age"] + NEWS_AGE_TOLERANCE + 1)}
        r = r[r.age.isin(bands)]
        steps.append(Step("News clip", f"age band {' or '.join(sorted(bands))}", len(r)))
    if c["symptom_group"] and (r.diagnosis_group == c["symptom_group"]).any():
        r = r[r.diagnosis_group == c["symptom_group"]]
        steps.append(Step("News clip", f"{c['symptom_group'].replace('_', ' ')} diagnosis", len(r)))
    return steps


def _band(age: int) -> str:
    return "80+" if age >= 80 else f"{age // 10 * 10}-{age // 10 * 10 + 9}"
