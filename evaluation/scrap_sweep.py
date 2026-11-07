"""Post and news sweep: every public social post and news clip in the package, replayed as an attack on a release.

The two demo attacks (attack_cases.py) show the problem on two hand-picked scraps. The sweep builds the same kind of
AttackCase automatically for all of them (948 posts, 220 news clips), with the clues an attacker reads from the
text: when, which town, sex (from the first name or the clip), age, how long they stayed, and what was wrong.
It replays them with the same engine (attacks.replay), which understands generalised values.

A release passes when no scrap leaves 1-4 candidates with the real visit among them (k = 5 for this attacker).
Evaluation only: it reads the attacker files and the ground truth (to pick each scrap's real visit and to check the
result). Ported from the main branch's reid_chain.py.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import pandas as pd
from pets_eval.utility.health import diagnosis_group

from evaluation.attacks import (
    AgedBetween,
    ArrivedBetween,
    AttackCase,
    Clue,
    Equals,
    ReplayResult,
    StayedBetween,
    replay,
)

POST_WINDOW_H = (16, 1)  # posts appear up to ~16 h after arrival, occasionally just before
STAY_PATTERNS = (r"Spent (\d+) hours", r"Jo (\d+) tuntia", r"(\d+) timmar")
STAY_TOLERANCE_MIN = (60, 30)  # the stated hours match the real stay within about half an hour
AGE_TOLERANCE = 2  # "noin 40-vuotias" (about 40)

# Symptom words → diagnosis group, in Finnish, English and Swedish. First match wins.
SYMPTOM_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cardiovascular", ("rintakipu", "chest pain", "bröstsmärta", "sydämentykyty", "palpitation", "sudden breathless")),
    ("allergy", ("ampiai", "huulten turpo", "kutisee", "wasp", "itch")),
    ("endocrine", ("verensokeri", "blood sugar", "blodsocker")),
    ("urological", ("virtsa", "urinat", "kylkikipu", "flank", "flanksmärta")),
    ("injury", ("kaatui", "fall", "fell", "slipped", "liukkaalla", "haava", "cut ", "viilsi", "nilkka", "ankle",
                "wrist", "ranne", "palovamm", "burn", "raketti", "olkapää", "shoulder", "fotled", "föll", "loukkaant",
                "ilotulit", "firework", "onnettomuu", "accident", "injured", "skadad")),
    ("musculoskeletal", ("selkä", "back pain", "ryggont")),
    ("neurological", ("päänsärky", "headache", "huvudvärk", "kouristel", "seizure", "kramp", "näköhäiriö",
                      "voimattomuus", "weakness", "slurred")),
    ("ILI", ("kotitesti", "home test", "lihaskiv", "body aches", "nuha", "runny nose")),
    ("respiratory", ("hengenahdistus", "breathless", "wheez", "andnöd", "cough")),
    ("gastrointestinal", ("vatsa", "abdominal", "ripuli", "diarrh", "oksentel", "vomit", "kylkikaaren", "quadrant")),
    ("other_infection", ("korvakipu", "earache", "kuume 39", "high temperature")),
    ("other", ("pyörtyi", "fainted", "svimmade", "huonovointi", "unwell", "mådde illa")),
)  # fmt: skip


def symptom_group(text: str) -> str | None:
    t = text.lower()
    return next((g for g, words in SYMPTOM_GROUPS if any(w in t for w in words)), None)


@dataclass(frozen=True)
class InGroup:
    """The visit's diagnosis falls in a group (from the codes, or a released diagnosis_group column)."""

    group: str
    label: str

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        if "diagnosis_group" in frame.columns:
            g = frame["diagnosis_group"].fillna("").astype(str).str.strip()
        elif "icd10_primary" in frame.columns:
            codes = frame["icd10_primary"].fillna("").astype(str).str.strip()
            g = pd.Series(diagnosis_group(codes).to_numpy(), index=frame.index).fillna("").astype(str)
            g[codes == ""] = ""
        else:
            return None
        return (g == self.group) | (g == "")


# ---------------------------------------------------------------- reading the package
def _read(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _hetu_sex(h: str) -> str | None:
    digits = re.sub(r"\D", "", h[7:10]) if len(h) >= 10 else ""
    return ("M" if int(digits) % 2 else "F") if len(digits) == 3 else None


@cache
def _name_sex(root: Path) -> dict[str, str]:
    """Stand-in for public first-name statistics: the usual sex of each first name, from ID codes in two customer
    lists and the school register."""
    f, c = _read(root / "data/finance/customers.csv"), _read(root / "data/customer_service/customers.csv")
    st = _read(root / "data/education/students.csv")
    rows = pd.concat([
        pd.DataFrame({"first": f.full_name.str.split().str[0], "sex": f.hetu.map(_hetu_sex)}),
        pd.DataFrame({"first": c.full_name.str.split().str[0], "sex": c.hetu.map(_hetu_sex)}),
        pd.DataFrame({"first": st.first_names.str.split().str[0], "sex": st.sex}),
    ]).dropna()  # fmt: skip
    rows = rows[rows["first"] != ""]
    usual: dict[str, str] = {}
    for first, sexes in rows.groupby("first")["sex"]:
        usual[str(first)] = str(sexes.value_counts().index[0])
    return usual


@cache
def _visits(root: Path) -> pd.DataFrame:
    ed = _read(root / "data/health/ed_visits.csv").merge(
        _read(root / "truth/health__ed_visits.csv").rename(columns={"record_id": "visit_id"}), on="visit_id"
    )
    ed["arrival"] = pd.to_datetime(ed.arrival_ts)
    return ed


def _target(ed: pd.DataFrame, person: str, when: pd.Timestamp) -> str | None:
    """The scrap's real visit: that person's visit closest in time (ground truth, evaluation only)."""
    v = ed[ed.person_id == person]
    if v.empty:
        return None
    gaps = [abs((t - when).total_seconds()) for t in v["arrival"]]
    return str(v["visit_id"].iloc[gaps.index(min(gaps))])


Row = dict[str, str]


def _post_clues(p: Row, name_sex: dict[str, str]) -> list[Clue]:
    t = pd.Timestamp(p["posted_ts"])
    before, after = pd.Timedelta(hours=POST_WINDOW_H[0]), pd.Timedelta(hours=POST_WINDOW_H[1])
    clues: list[Clue] = [ArrivedBetween(t - before, t + after, "arrived in the hours before the post")]
    if p["profile_city"]:
        clues.append(Equals("municipality", p["profile_city"], f"lives in {p['profile_city']}"))
    first = p["display_name"].split()[0] if p["display_name"].strip() else ""
    if sex := name_sex.get(first):
        clues.append(Equals("sex", sex, f"'{first}' is usually {'a woman' if sex == 'F' else 'a man'}'s name"))
    if stay := next((int(m.group(1)) for pat in STAY_PATTERNS if (m := re.search(pat, p["text"]))), None):
        lo, hi = stay * 60 - STAY_TOLERANCE_MIN[0], stay * 60 + STAY_TOLERANCE_MIN[1]
        clues.append(StayedBetween(lo, hi, f"stayed about {stay} hours"))
    if group := symptom_group(p["text"]):
        clues.append(InGroup(group, f"symptoms point to {group.replace('_', ' ')}"))
    return clues


def _news_clues(n: Row, day: pd.Timestamp) -> list[Clue]:
    if n["event_date"]:
        clues: list[Clue] = [ArrivedBetween(day, day + pd.Timedelta(days=1), "arrived on the day of the accident")]
    else:
        clues = [ArrivedBetween(day - pd.Timedelta(days=2), day + pd.Timedelta(days=1), "arrived in the days before")]
    if hour := re.search(r"kello (\d+)", n["text"]):
        h = day + pd.Timedelta(hours=int(hour.group(1)))
        clues.append(ArrivedBetween(h, h + pd.Timedelta(hours=2), f"rescue called at {hour.group(1)}:00"))
    if n["place"]:
        clues.append(Equals("municipality", n["place"], f"happened in {n['place']}"))
    if sex := n["sex_mentioned"]:
        clues.append(Equals("sex", sex, "a woman" if sex == "F" else "a man"))
    if n["age_mentioned"]:
        a = int(n["age_mentioned"])
        clues.append(AgedBetween(a - AGE_TOLERANCE, a + AGE_TOLERANCE + 1, day, f"aged about {a}"))
    if group := symptom_group(n["text"]):
        clues.append(InGroup(group, f"{group.replace('_', ' ')} diagnosis"))
    return clues


def _scraps(root: Path, name: str) -> list[Row]:
    frame = _read(root / f"adversary/{name}.csv").merge(_read(root / f"truth/adversary__{name}.csv"), on="adv_row_id")
    return [{str(k): str(v) for k, v in r.items()} for r in frame.to_dict("records")]


def build_cases(root: Path) -> list[AttackCase]:
    root = Path(root)
    ed, name_sex = _visits(root), _name_sex(root)
    cases: list[AttackCase] = []
    for p in _scraps(root, "social_posts_health"):
        target = _target(ed, p["person_id"], pd.Timestamp(p["posted_ts"]))
        if target is not None:
            cases.append(
                AttackCase(p["adv_row_id"], "social post", p["text"][:80], target, tuple(_post_clues(p, name_sex)))
            )
    for n in _scraps(root, "news_clips_health"):
        day = pd.Timestamp(n["event_date"] or n["published_date"])
        target = _target(ed, n["person_id"], day)
        if target is not None:
            cases.append(AttackCase(n["adv_row_id"], "news clip", n["text"][:80], target, tuple(_news_clues(n, day))))
    return cases


# ---------------------------------------------------------------- running the sweep
@dataclass(frozen=True)
class SweepResult:
    scraps: int
    single: int  # one candidate left
    single_target: int  # ... and it is the real visit
    exposed: int  # 1-4 candidates left with the real visit among them
    median_candidates: float
    worst: list[ReplayResult]

    def summary(self) -> str:
        return (
            f"{self.scraps} scraps · one visit left {self.single} (real {self.single_target}) · "
            f"real visit in a group of 1-4: {self.exposed} · median group {self.median_candidates:.0f}"
        )


def sweep(root: Path, release: pd.DataFrame, record_ids: Sequence[str] | None, k: int = 5) -> SweepResult:
    results = [replay(c, release, record_ids) for c in build_cases(root)]
    left = pd.Series([r.candidates_left for r in results])
    hit = pd.Series([bool(r.target_among_candidates) for r in results])
    exposed = (left.between(1, k - 1)) & hit
    worst = sorted((r for r, e in zip(results, exposed, strict=True) if e), key=lambda r: r.candidates_left)[:10]
    return SweepResult(len(results), int((left == 1).sum()), int(((left == 1) & hit).sum()), int(exposed.sum()),
                       float(left.median()), worst)  # fmt: skip
