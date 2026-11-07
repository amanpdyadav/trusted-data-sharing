"""Mosaic chains for every public post and news clip: how one scrap leads to a person, dataset by dataset.

For the web app's Mosaic attack screen (see screens.py).
Each case has two chains and a replay:

  raw    every organisation shares raw files: once the hospital row gives a name, every dataset with a name opens up
  names  names, ID codes, phones and addresses removed everywhere: the scrap's clues narrow the hospital visits to one
         person, whose birth date + postcode then join the bank, energy, travel-card and school releases
  ours   the same clues replayed on our release (attacks.replay)

Every link is checked against the ground truth, which the attacker never uses for matching. Identifiers are partly
masked at the source, as on the team's problem demo page. Evaluation only: it reads the attacker files and truth.
"""

import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Any

import pandas as pd
from pets_eval.utility.health import diagnosis_group

from evaluation.attacks import AttackCase, replay, replay_summary
from evaluation.scrap_sweep import Row, build_cases, load_scraps, load_visits
from pets_transformer.io import read_table

Step = dict[str, Any]


# ---------------------------------------------------------------- masking (as on the problem demo page)
def mask_hetu(h: str) -> str:
    return f"{h[:8]}••{h[-1]}" if len(h) == 11 else "•••"


def mask_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if not d:
        return "unlisted"
    d = "0" + d[3:] if d.startswith("358") else d
    return f"{d[:3]} ••• {d[-4:]}"


def mask_iban(i: str) -> str:
    return f"{i[:4]} •••• •••• •••• {i[-2:]}" if i else "-"


def mask_email(e: str) -> str:
    if "@" not in (e or ""):
        return "-"
    user, dom = e.split("@", 1)
    return f"{user[:7]}•••@{dom}"


def mask_street(a: str) -> str:
    return re.sub(r"\d.*$", "••", a).strip() if a else "-"


# ---------------------------------------------------------------- data
@dataclass(frozen=True)
class Tables:
    ed: pd.DataFrame
    directory: pd.DataFrame
    leak: pd.DataFrame
    bank: pd.DataFrame
    energy: pd.DataFrame
    cards: pd.DataFrame
    school: pd.DataFrame
    work: pd.DataFrame
    telecom: pd.DataFrame
    calls: pd.DataFrame
    group: dict[str, str] = field(default_factory=dict)


def _with_truth(df: pd.DataFrame, root: Path, name: str, key: str) -> pd.DataFrame:
    t = read_table(root / f"truth/{name}.csv").rename(columns={"record_id": key, "adv_row_id": key})
    return df.merge(t, on=key, how="left")


@cache
def tables(root: Path) -> Tables:
    ed = load_visits(root)
    codes = ed["icd10_primary"]
    groups = pd.Series(diagnosis_group(codes).to_numpy(), index=ed.index).fillna("").astype(str)
    directory = _with_truth(
        read_table(root / "adversary/public_directory.csv"), root, "adversary__public_directory", "adv_row_id"
    )
    return Tables(
        ed=ed.assign(group=groups),
        directory=directory,
        leak=_with_truth(
            read_table(root / "adversary/leaked_customer_list.csv"),
            root,
            "adversary__leaked_customer_list",
            "adv_row_id",
        ),
        bank=_with_truth(read_table(root / "data/finance/customers.csv"), root, "finance__customers", "customer_id"),
        energy=_with_truth(read_table(root / "data/energy/customers.csv"), root, "energy__customers", "customer_id"),
        cards=_with_truth(read_table(root / "data/mobility/cards.csv"), root, "mobility__cards", "card_id"),
        school=_with_truth(read_table(root / "data/education/students.csv"), root, "education__students", "student_id"),
        work=_with_truth(read_table(root / "data/cyber/identity.csv"), root, "cyber__identity", "identity_id"),
        telecom=_with_truth(
            read_table(root / "data/customer_service/customers.csv"), root, "customer_service__customers", "customer_id"
        ),
        calls=read_table(root / "data/customer_service/conversations.csv")[["customer_id", "intent"]],
    )


def _step(  # noqa: PLR0913, PLR0917  (one flat record per step)
    sid: str,
    dataset: str,
    file: str,
    kind: str,
    title: str,
    total: int,
    funnel: list[list[Any]],
    revealed: dict[str, Any],
    how: str,
    link: str,
    verified: bool | None,
) -> Step:
    return {
        "id": sid,
        "dataset": dataset,
        "file": file,
        "kind": kind,
        "title": title,
        "rows_total": total,
        "funnel": funnel,
        "revealed": {k: str(v) for k, v in revealed.items() if v not in ("", None)},
        "how": how,
        "link": link,
        "verified": verified,
    }


def _source_step(case: AttackCase, scrap: Row, news: bool) -> Step:
    if news:
        quote = {"who": scrap["headline"], "when": f"published {scrap['published_date']}", "text": scrap["text"]}
        revealed = {
            "Event": scrap["headline"],
            "Town": scrap["place"],
            "Age": scrap["age_mentioned"],
            "Sex": {"F": "female", "M": "male"}.get(scrap["sex_mentioned"], ""),
            "Name": scrap["name_mentioned"],
        }
        step = _step(
            "news",
            "Local news",
            "adversary/news_clips_health.csv",
            "public",
            "A news clip",
            220,
            [],
            revealed,
            "Anyone can read it: a date, a town, an age and a sex.",
            "",
            None,
        )
    else:
        quote = {
            "who": scrap["display_name"] or f"@{scrap['handle']}",
            "when": scrap["posted_ts"][:16],
            "text": scrap["text"],
        }
        revealed = {"Name": scrap["display_name"], "Lives in": scrap["profile_city"], "Posted": scrap["posted_ts"][:16]}
        step = _step(
            "post",
            "Social media",
            "adversary/social_posts_health.csv",
            "public",
            "A public post",
            948,
            [],
            revealed,
            "Anyone can read it: the name, the time and what happened.",
            "",
            None,
        )
    step["quote"] = quote
    step["clues"] = [c.label for c in case.clues]
    return step


def _health(v: Row, with_name: bool) -> dict[str, str]:
    h = {
        "Diagnosis": f"{v['icd10_primary']} ({v['group'].replace('_', ' ')})",
        "Chief complaint": v["chief_complaint"],
        "Arrival": v["arrival_ts"][:16],
        "Length of stay": f"{v['los_minutes']} min" if v["los_minutes"] else "",
        "Outcome": v["disposition"],
        "Birth date": v["date_of_birth"],
        "Sex": v["sex"],
        "Postcode": v["postcode"],
    }
    if with_name:
        parts = v["patient_name"].split()
        h = {
            "Name": " ".join([*parts[1:], parts[0]]) if parts else "",
            **h,
            "National ID": mask_hetu(v["patient_hetu"]),
            "Phone": mask_phone(v["phone"]),
        }
    return h


def _row(df: pd.DataFrame) -> Row:
    return {str(k): str(v) for k, v in df.iloc[0].to_dict().items()}


# ---------------------------------------------------------------- the chains
_CLUE_WORDS = (
    ("arrived", "time"),
    ("rescue", "hour"),
    ("lives in", "town"),
    ("happened in", "town"),
    ("usually", "sex"),
    ("a woman", "sex"),
    ("a man", "sex"),
    ("aged", "age"),
    ("stayed", "stay"),
    ("symptoms", "symptoms"),
    ("diagnosis", "symptoms"),
    ("directory", "name + postcode"),
)


def link_label(funnel: list[list[Any]]) -> str:
    """'time · town · sex · stay · symptoms': the clues that actually narrowed the visits."""
    words: list[str] = []
    for label, *_ in funnel:
        w = next((w for key, w in _CLUE_WORDS if key in str(label)), None)
        if w and w not in words:
            words.append(w)
    return " · ".join(words)


@dataclass
class Found:
    visit: Row | None
    funnel: list[list[Any]]
    verified: bool | None


def find_visit(case: AttackCase, scrap: Row, t: Tables, person: str) -> Found:
    """Names removed: replay the scrap's clues on the hospital visits; then a directory postcode for full names."""
    mask = pd.Series(True, index=t.ed.index)
    funnel: list[list[Any]] = []
    for clue in case.clues:
        m = clue.matches(t.ed)
        if m is not None:
            mask &= m.fillna(True).astype(bool)
            funnel.append([clue.label, int(mask.sum())])
    cand = t.ed[mask]
    full = scrap.get("display_name", "") or scrap.get("name_mentioned", "")
    if len(full.split()) > 1 and cand.drop_duplicates(["date_of_birth", "postcode"]).shape[0] > 1:
        hits = t.directory[t.directory["name"] == full]
        narrowed = cand[cand["postcode"].isin(hits["postcode"])]
        if len(narrowed):
            cand = narrowed
            funnel.append(
                [f"the directory lists '{full}' at postcode {', '.join(sorted(set(hits['postcode'])))}", len(cand)]
            )
    if cand.drop_duplicates(["date_of_birth", "postcode", "sex"]).shape[0] != 1:
        return Found(None, funnel, None)
    v = _row(cand.sort_values("arrival").tail(1))
    return Found(v, funnel, v["person_id"] == person)


def names_chain(src: Step, found: Found, scrap: Row, t: Tables) -> list[Step]:
    steps = [src]
    v = found.visit
    steps.append(
        _step(
            "ed",
            "Hospital ED",
            "data/health/ed_visits.csv",
            "release",
            "One emergency visit left",
            len(t.ed),
            [["all visits", len(t.ed)], *found.funnel],
            _health(v, False) if v else {},
            "Names, ID codes, phones and addresses are removed; the clues still narrow the visits to one."
            if v
            else "The clues leave more than one person, so the chain stops here.",
            link_label(found.funnel),
            found.verified,
        )
    )
    if v is None:
        return steps
    dob, pc, pid = v["date_of_birth"], v["postcode"], v["person_id"]
    joins = (
        (
            "bank",
            "Saaristo Bank",
            "data/finance/customers.csv",
            "Income and employer",
            t.bank,
            "birth_date",
            "postcode",
            {"Income band": "income_band", "Occupation": "occupation", "Employer": "employer"},
        ),
        (
            "energy",
            "Energy company",
            "data/energy/customers.csv",
            "Home and heating",
            t.energy,
            "birth_date",
            "postcode",
            {
                "Heating": "heating_type",
                "Home size m²": "floor_area_m2",
                "Medical device at home": "medical_device_priority",
            },
        ),
        (
            "transport",
            "Travel cards",
            "data/mobility/cards.csv",
            "A registered travel card",
            t.cards,
            "holder_birth_date",
            "holder_postcode",
            {"Card type": "card_type", "Issued": "issued_date"},
        ),
        (
            "school",
            "School register",
            "data/education/students.csv",
            "School and class",
            t.school,
            "birth_date",
            "postcode",
            {"School": "school_name", "Class": "class_group", "Special support": "special_support"},
        ),
    )
    for sid, ds, file, title, df, dob_col, pc_col, show in joins:
        m = df[(df[dob_col] == dob) & (df[pc_col] == pc)]
        if len(m) == 1:
            r = _row(m)
            steps.append(
                _step(
                    sid,
                    ds,
                    file,
                    "release",
                    title,
                    len(df),
                    [["all records", len(df)], ["same birth date + postcode", 1]],
                    {label: r[col] for label, col in show.items()},
                    f"The hospital row kept birth date {dob} and postcode {pc}; exactly one record has both.",
                    "birth date + postcode",
                    r["person_id"] == pid,
                )
            )
    full = scrap.get("display_name", "")
    first = full.split()[0] if full.strip() else ""
    d = t.directory
    hits = (
        d[(d["name"] == full) & (d["postcode"] == pc)]
        if len(full.split()) > 1
        else d[(d["name"].str.split().str[0] == first) & (d["postcode"] == pc)]
        if first
        else d.iloc[:0]
    )
    if len(hits) == 1:
        r = _row(hits)
        how = "name + postcode" if len(full.split()) > 1 else "first name + postcode"
        steps.append(
            _step(
                "directory",
                "Public directory",
                "adversary/public_directory.csv",
                "public",
                "A name and a home",
                len(d),
                [["all listings", len(d)], [f"same {how}", 1]],
                {
                    "Name": r["name"],
                    "Home address": f"{mask_street(r['street_address'])}, {r['postcode']} {r['city']}",
                    "Phone": mask_phone(r["phone"]),
                },
                "The public directory puts a name and a street address on the record.",
                how,
                r["person_id"] == pid,
            )
        )
    return steps


def raw_chain(src: Step, found: Found, t: Tables) -> list[Step]:
    """Raw files shared: the hospital row carries the name, and every dataset with a name column opens up."""
    v = found.visit
    if v is None:
        return []
    pid, pc, dob, town = v["person_id"], v["postcode"], v["date_of_birth"], v["municipality"]
    parts = v["patient_name"].split()
    first, surname = (parts[1] if len(parts) > 1 else ""), (parts[0] if parts else "")
    full = f"{first} {surname}"
    steps = [
        src,
        _step(
            "ed",
            "Hospital ED",
            "data/health/ed_visits.csv",
            "leaked",
            "Emergency visit, and a name",
            len(t.ed),
            [["all visits", len(t.ed)], *found.funnel],
            _health(v, True),
            "The one visit left carries the patient's name, ID code and phone.",
            link_label(found.funnel),
            found.verified,
        ),
    ]

    def add(  # noqa: PLR0913, PLR0917
        sid: str,
        ds: str,
        file: str,
        title: str,
        df: pd.DataFrame,
        mask: pd.Series,
        how: str,
        link: str,
        reveal: dict[str, str],
    ) -> Row | None:
        m = df[mask]
        if len(m) != 1 or str(m["person_id"].iloc[0]) != pid:
            return None
        r = _row(m)
        steps.append(
            _step(
                sid,
                ds,
                file,
                "public" if file.startswith("adversary") else "leaked",
                title,
                len(df),
                [["all records", len(df)], [f"same {link}", 1]],
                {label: r.get(col, col) if col in r else col for label, col in reveal.items()},
                how,
                link,
                True,
            )
        )
        return r

    other = t.ed[(t.ed["person_id"] == pid) & (t.ed["visit_id"] != v["visit_id"])]
    if len(other):
        o = _row(other.sort_values("arrival").tail(1))
        steps.append(
            _step(
                "history",
                "Hospital ED, again",
                "data/health/ed_visits.csv",
                "leaked",
                "Other visits",
                len(t.ed),
                [["all visits", len(t.ed)], ["same name and birth date", len(other) + 1]],
                {"Other visits": str(len(other)), "Latest other": f"{o['arrival_ts'][:10]}: {o['icd10_primary']}"},
                "Now that the name is known, search the same table again.",
                "name + birth date",
                True,
            )
        )
    d, lk = t.directory, t.leak
    r = add(
        "directory",
        "Public directory",
        "adversary/public_directory.csv",
        "Home address",
        d,
        (d["name"] == full) & (d["postcode"] == pc),
        "Same name and postcode as the hospital record.",
        "name + postcode",
        {"Home address": "street_address", "City": "city"},
    )
    if r:
        steps[-1]["revealed"]["Home address"] = mask_street(r["street_address"]) + f", {r['postcode']} {r['city']}"
    r = add(
        "leak",
        "Old leaked list",
        "adversary/leaked_customer_list.csv",
        "Phone and e-mail",
        lk,
        (lk["name"] == full) & ((lk["city"] == town) | (lk["city"] == "")),
        "A marketing list that leaked online: same name, same town.",
        "name + town",
        {"Interest": "interest"},
    )
    if r:
        steps[-1]["revealed"] |= {"Phone": mask_phone(r["phone"]), "E-mail": mask_email(r["email"])}
    b = t.bank
    bank = add(
        "bank",
        "Saaristo Bank",
        "data/finance/customers.csv",
        "Income and employer",
        b,
        (b["birth_date"] == dob) & (b["postcode"] == pc) & b["full_name"].str.startswith(first),
        "Same name, birth date and postcode as the hospital record.",
        "name + birth date",
        {"Income band": "income_band", "Employer": "employer", "Occupation": "occupation"},
    )
    if bank:
        steps[-1]["revealed"]["IBAN"] = mask_iban(bank["iban"])
    e = t.energy
    add(
        "energy",
        "Energy company",
        "data/energy/customers.csv",
        "Home and heating",
        e,
        (e["postcode"] == pc)
        & e["customer_name"].str.contains(surname, regex=False)
        & e["customer_name"].str.contains(first, regex=False),
        "Same name and postcode in the energy customer list.",
        "name + postcode",
        {"Heating": "heating_type", "Medical device at home": "medical_device_priority"},
    )
    s = t.school
    add(
        "school",
        "School register",
        "data/education/students.csv",
        "School and class",
        s,
        (s["birth_date"] == dob) & (s["last_name"] == surname),
        "Same surname and birth date in the school register.",
        "name + birth date",
        {"School": "school_name", "Class": "class_group"},
    )
    w = t.work
    if bank and "meridian" in bank["employer"].lower():
        r = add(
            "work",
            "Employer IT logs",
            "data/cyber/identity.csv",
            "Job and work logs",
            w,
            w["display_name"] == full,
            "The bank says Meridian Logistics; its staff directory has one match.",
            "name + employer",
            {"Job title": "job_title", "Department": "department", "Shift": "shift"},
        )
        if r:
            steps[-1]["revealed"]["Work e-mail"] = mask_email(r["upn"])
    tc = t.telecom
    r = add(
        "telecom",
        "Telecom customers",
        "data/customer_service/customers.csv",
        "Contracts and calls",
        tc,
        tc["full_name"].str.startswith(first) & tc["full_name"].str.endswith(surname) & (tc["postcode"] == pc),
        "Same name and postcode in the telecom's customer master.",
        "name + postcode",
        {"Products": "products"},
    )
    if r:
        calls = t.calls[t.calls["customer_id"] == r["customer_id"]]
        steps[-1]["revealed"]["Calls"] = f"{len(calls)}: " + ", ".join(calls["intent"].str.replace("_", " ").head(3))
    return steps


def build(
    root: Path, release: pd.DataFrame, record_ids: list[str] | None, limit: int = 400
) -> tuple[list[dict[str, Any]], dict[str, dict[str, int]]]:
    """Every scrap that leads to one verified person, richest chains first (plus a replay on our release), and the
    headline counted over every scrap (before `limit`): per kind, how many scraps there are, how many lead to one
    verified person with names removed, and how many still expose someone on our release."""
    t = tables(root)
    scraps = {s["adv_row_id"]: (s, False) for s in load_scraps(root, "social_posts_health")}
    scraps |= {s["adv_row_id"]: (s, True) for s in load_scraps(root, "news_clips_health")}
    out: list[dict[str, Any]] = []
    for case in build_cases(root):
        scrap, news = scraps[case.id]
        found = find_visit(case, scrap, t, scrap["person_id"])
        if not found.verified:
            continue
        src = _source_step(case, scrap, news)
        names = names_chain(src, found, scrap, t)
        ours = replay(case, release, record_ids)
        out.append(
            {
                "id": case.id,
                "kind": "news" if news else "post",
                "text": scrap["text"],
                "label": (scrap["headline"] if news else (scrap["display_name"] or "anonymous")),
                "raw": raw_chain(src, found, t),
                "names": names,
                "ours": replay_summary(ours),
            }
        )
    demo = ("POST00635", "NEWS00100")  # the problem demo's two cases come first
    out.sort(
        key=lambda c: (
            c["id"] not in demo,
            demo.index(c["id"]) if c["id"] in demo else 0,
            -len(c["names"]),
            -len(c["raw"]),
        )
    )
    summary = {
        kind: {
            "scraps": sum(1 for _, is_news in scraps.values() if is_news == (kind == "news")),
            "one_person_names_removed": sum(1 for c in out if c["kind"] == kind),
            "exposed_on_release": sum(1 for c in out if c["kind"] == kind and not c["ours"]["holds"]),
        }
        for kind in ("post", "news")
    }
    return out[:limit], summary
