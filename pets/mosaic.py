"""Mosaic attack cases and release audit: the data behind both front ends (Streamlit and React), served by the API.

A case starts from one public scrap (a social post or a news clip) and has three modes:

  raw    every organisation shares its raw files, names included: once the hospital row gives a name, any
         dataset with a name column opens up (directory, leaked list, bank, energy, transport, school,
         employer IT logs, telecom)
  names  every organisation removes names, ID codes, phones and addresses: the attacker narrows the hospital
         data with the scrap's clues, then joins other releases on birth date + postcode
  ours   the same scrap against our HEALTH-S1 release

Every step is checked against the ground truth (`truth/`), which the attacker never uses for matching.
Identifiers are partly masked, as on the team's problem demo page. Everything is synthetic.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

import pandas as pd

from . import DATA, OUTPUTS, PG_ROOT
from . import reid_chain as rc

MODES = {"raw": "Raw data shared", "names": "Names removed", "ours": "Our release"}


# ---------------------------------------------------------------- masking (identifiers shown partly, as on the demo)
def mask_hetu(h: str) -> str:
    return f"{h[:8]}••{h[-1]}" if len(h) == 11 else "•••"


def mask_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    if not d:
        return "unlisted"
    d = "0" + d[3:] if d.startswith("358") else d
    return f"{d[:3]} ••• {d[-4:]}"


def mask_iban(i: str) -> str:
    return f"{i[:4]} •••• •••• •••• {i[-2:]}" if i else "–"


def mask_email(e: str) -> str:
    if "@" not in (e or ""):
        return "–"
    user, dom = e.split("@", 1)
    return f"{user[:7]}•••@{dom}"


def mask_street(a: str) -> str:
    return re.sub(r"\d.*$", "••", a).strip() if a else "–"


def mask_card(c: str) -> str:
    return f"•••• {c[-4:]}" if c else "–"


# ---------------------------------------------------------------- data
@lru_cache(maxsize=1)
def _extra() -> dict:
    """Datasets only the raw-data attacker can use (joined by name)."""
    rd, wt = rc._read, rc._with_truth
    leak = wt(rd(PG_ROOT / "adversary" / "leaked_customer_list.csv"), "adversary", "leaked_customer_list", "adv_row_id")
    cyber = wt(rd(DATA / "cyber" / "identity.csv"), "cyber", "identity", "identity_id")
    cs = wt(rd(DATA / "customer_service" / "customers.csv"), "customer_service", "customers", "customer_id")
    conv = rd(DATA / "customer_service" / "conversations.csv")[["customer_id", "intent", "started_ts"]]
    return {"leak": leak, "cyber": cyber, "cs": cs, "conv": conv}


def _name_parts(ed_name: str) -> tuple[str, str]:
    """ED names are 'Surname Given Middle…'. Returns (first given name, surname)."""
    p = ed_name.split()
    return (p[1] if len(p) > 1 else ""), (p[0] if p else "")


def _verified(m: pd.DataFrame, pid: str | None) -> bool | None:
    if pid is None or len(m) != 1:
        return None
    return bool(m.person_id.iat[0] == pid)


def _step(id_, dataset, file, kind, title, rows_total, funnel, revealed, how, verified=None, quote=None):
    s = {"id": id_, "dataset": dataset, "file": file, "kind": kind, "title": title, "rows_total": int(rows_total),
         "funnel": [[lab, int(n)] for lab, n in funnel], "revealed": {k: str(v) for k, v in revealed.items() if v not in ("", None)},
         "how": how, "verified": verified}
    if quote:
        s["quote"] = quote
    return s


def _source_step(ch: rc.Chain) -> dict:
    p, c = ch.post, ch.clues
    if ch.source == "news":
        revealed = {"Event": p["headline"], "Town": c["city"], "Age": c["age"], "Sex": {"F": "Female", "M": "Male"}.get(c["sex"]),
                    "Date": (c["date"] or c["published"]).strftime("%d %b %Y"), "Hour": f"{c['hour']}:00" if c["hour"] is not None else None,
                    "Name": c["full_name"]}
        return _step("news", "Local news", "adversary/news_clips_health.csv", "public",
                     "A news clip" + ("" if c["full_name"] else ", no name"), len(rc._load()["news"]), [], revealed,
                     "Anyone can read it." + ("" if c["full_name"] else " No name anywhere: only a date, a town, an age and a sex."),
                     quote={"who": p["headline"], "when": f"Published {p['published_date']}", "text": p["text"]})
    revealed = {"Name": p["display_name"] or None, "Lives in": c["city"], "Posted": c["posted"].strftime("%d %b %Y, %H:%M"),
                "Symptoms": (c["symptom_group"] or "").replace("_", " ") or None,
                "Stayed": f"about {c['stay_hours']} hours" if c.get("stay_hours") else None}
    return _step("post", "Social media", "adversary/social_posts_health.csv", "public", "A public post",
                 len(rc._load()["posts"]), [], revealed, "Anyone can read it. The name, the time and what happened are in the post.",
                 quote={"who": p["display_name"] or f"@{p['handle']}", "when": p["posted_ts"][:16], "text": p["text"]})


def _health_revealed(v: dict, with_name: bool) -> dict:
    h = {"Diagnosis": f"{v['icd10_primary']} ({v['group'].replace('_', ' ')})", "Chief complaint": v["chief_complaint"],
         "Arrival": v["arrival_ts"][:16], "Length of stay": f"{v['los_minutes']} min" if v["los_minutes"] else None,
         "Outcome": v["disposition"], "Birth date": v["date_of_birth"], "Sex": v["sex"], "Postcode": f"{v['postcode']} {v['municipality']}"}
    if with_name:
        given, sur = v["patient_name"].split()[1:], v["patient_name"].split()[0]
        h = {"Name": " ".join(given + [sur]), **h, "National ID": mask_hetu(v["patient_hetu"]), "Phone": mask_phone(v["phone"])}
    return h


# ---------------------------------------------------------------- the three modes
def _names_mode(ch: rc.Chain) -> list[dict]:
    """Names removed everywhere: our chain, as steps."""
    d, v, pid = rc._load(), ch.visit, ch.post.get("person_id") or None
    steps = [_source_step(ch)]
    steps.append(_step("ed", "Hospital ED", "data/health/ed_visits.csv", "release", "One emergency visit left",
                       len(d["ed"]), [(f.clue, f.candidates) for f in ch.funnel], _health_revealed(v, False),
                       "Names, ID codes, phones and addresses are removed. The clues still narrow the visits to one.",
                       verified=ch.person_correct))
    files = {"Bank": ("bank", "Saaristo Bank", "data/finance/customers.csv", "finance", "Income and employer"),
             "Energy company": ("energy", "Energy company", "data/energy/customers.csv", "energy", "Home and heating"),
             "Public transport": ("transport", "Travel cards", "data/mobility/cards.csv", "mobility", "Where they travel"),
             "School register": ("school", "School register", "data/education/students.csv", "students", "School and class")}
    for link in ch.links:
        if link["Dataset"] in files and link["Matches"] == 1:
            id_, ds, f, key, title = files[link["Dataset"]]
            rev = {k: v_ for k, v_ in ch.dossier[link["Dataset"]].items()}
            if "Card number" in rev:
                rev["Card number"] = mask_card(rev["Card number"])
            if "Meter ID" in rev:
                rev["Meter ID"] = mask_card(rev["Meter ID"])
            steps.append(_step(id_, ds, f, "release", title, len(d[key]),
                               [("all records", len(d[key])), ("same birth date + postcode", 1)], rev,
                               f"The hospital row kept birth date {v['date_of_birth']} and postcode {v['postcode']}. "
                               f"Exactly one {ds.lower()} record has both.", verified=link["Correct"]))
    ident = next((l for l in ch.links if l["Dataset"] == "Public phone directory"), None)
    if ident and ident["Matches"] == 1 and "Identity" in ch.dossier:
        i = ch.dossier["Identity"]
        steps.append(_step("directory", "Public directory", "adversary/public_directory.csv", "public", "A name and a home",
                           len(d["directory"]), [("all listings", len(d["directory"])), (ident["Joined on"], 1)],
                           {"Name": i["Name"], "Home address": f"{mask_street(i['Street address'])}, {i['City']}",
                            "Phone": mask_phone(i["Phone"]) if i["Phone"] != "unlisted" else "unlisted"},
                           "Same name and postcode as the hospital record." if ident["Joined on"] == "full name"
                           else "One listing at that postcode has the poster's first name.", verified=ident["Correct"]))
    return steps


def _raw_mode(ch: rc.Chain) -> list[dict]:
    """Raw files shared: the hospital row carries the name, and every named dataset opens up."""
    d, x, v = rc._load(), _extra(), ch.visit
    pid = v["person_id"]
    first, surname = _name_parts(v["patient_name"])
    full = f"{first} {surname}"
    pc, dob, town = v["postcode"], v["date_of_birth"], v["municipality"]
    steps = [_source_step(ch)]
    named_post = ch.source == "post" and ch.clues.get("full_name")
    if named_post:
        ed = d["ed"]
        by_name = ed[ed.patient_name.map(lambda n: " ".join(_name_parts(n))) == ch.clues["full_name"]]
        funnel = [("all visits", len(ed)), ("same name", by_name.person_id.nunique()), ("arrived in the hours before the post", 1)]
        how = "Match the name, then keep the visit that arrived in the hours before the post."
    else:
        funnel = [(f.clue, f.candidates) for f in ch.funnel]
        how = "Narrow the visits by the clues. The one record left carries the name."
    steps.append(_step("ed", "Hospital ED", "data/health/ed_visits.csv", "leaked",
                       "Emergency visit found" if named_post else "Emergency visit, and a name",
                       len(d["ed"]), funnel, _health_revealed(v, True), how, verified=ch.person_correct))

    other = d["ed"][(d["ed"].person_id == pid) & (d["ed"].visit_id != v["visit_id"])]
    if len(other):
        o = other.sort_values("arrival").iloc[-1]
        steps.append(_step("history", "Hospital ED, again", "data/health/ed_visits.csv", "leaked", "Other hospital visits",
                           len(d["ed"]), [("all visits", len(d["ed"])), ("same name and birth date", len(other) + 1),
                                          ("other than this visit", len(other))],
                           {"Other visits": len(other), "Latest other": f"{o.arrival_ts[:10]}: {o.icd10_primary}, {o.chief_complaint}"},
                           "Now that the name is known, search the same table again.", verified=True))

    def add(id_, ds, file, title, df, mask, funnel_labels, reveal, how):
        m = df[mask]
        if len(m) == 1 and m.person_id.iat[0] == pid:
            steps.append(_step(id_, ds, file, "leaked" if file.startswith("data/") else "public", title, len(df),
                               [("all records", len(df))] + [(lab, n) for lab, n in funnel_labels] + [("match", 1)],
                               reveal(m.iloc[0]), how, verified=True))
            return m.iloc[0]
        return None

    dr = d["directory"]
    add("directory", "Public directory", "adversary/public_directory.csv", "Home address", dr,
        (dr.name == full) & (dr.postcode == pc), [("same name", int((dr.name == full).sum()))],
        lambda r: {"Home address": f"{mask_street(r.street_address)}, {r.postcode} {r.city}", "Phone": mask_phone(r.phone)},
        "Same name, same postcode as the hospital record.")
    lk = x["leak"]
    add("leak", "Old leaked list", "adversary/leaked_customer_list.csv", "Phone and e-mail", lk,
        (lk.name == full) & ((lk.city == town) | (lk.city == "")), [("same name", int((lk.name == full).sum()))],
        lambda r: {"Phone": mask_phone(r.phone), "E-mail": mask_email(r.email), "Interest": f"{r.interest} ({r.list_year} list)"},
        "A marketing list that leaked online: same name, same town.")
    fin = d["finance"]
    bank = add("bank", "Saaristo Bank", "data/finance/customers.csv", "Income and employer", fin,
               (fin.birth_date == dob) & (fin.postcode == pc) & fin.full_name.str.startswith(first),
               [("same birth date + postcode", int(((fin.birth_date == dob) & (fin.postcode == pc)).sum()))],
               lambda r: {"Income band": r.income_band, "Employer": r.employer, "Occupation": r.occupation, "IBAN": mask_iban(r.iban)},
               "Same name, birth date and postcode as the hospital record.")
    en = d["energy"]
    add("energy", "Energy company", "data/energy/customers.csv", "Home and heating", en,
        (en.postcode == pc) & en.customer_name.str.contains(surname, regex=False) & en.customer_name.str.contains(first, regex=False),
        [("same postcode", int((en.postcode == pc).sum()))],
        lambda r: {"Heating": r.heating_type, "Home size": f"{r.floor_area_m2} m²", "EV charger": r.ev_charger,
                   "Medical device at home": r.medical_device_priority, "Late payments": r.late_payment_count},
        "Same name and postcode in the energy customer list.")
    mob = d["mobility"]
    card = add("transport", "Travel cards", "data/mobility/cards.csv", "Where they travel", mob,
               (mob.holder_birth_date == dob) & (mob.holder_postcode == pc),
               [("same birth date + postcode", int(((mob.holder_birth_date == dob) & (mob.holder_postcode == pc)).sum()))],
               lambda r: {"Card": f"{r.card_type}, {mask_card(r.card_id)}"}, "A registered travel card with the same birth date and postcode.")
    if card is not None:
        taps = rc._taps_for(card.card_id)
        if len(taps):
            stops = d["stops"].set_index("stop_id")
            steps[-1]["revealed"]["Trips"] = str(len(taps))
            steps[-1]["revealed"]["Most used stops"] = ", ".join(str(stops.name.get(s, s)) for s in taps.stop_id.value_counts().index[:2])
    st = d["students"]
    add("school", "School register", "data/education/students.csv", "School and class", st,
        (st.birth_date == dob) & (st.last_name == surname), [("same surname", int((st.last_name == surname).sum()))],
        lambda r: {"School": r.school_name, "Class": r.class_group, "Special support": r.special_support},
        "Same surname and birth date in the school register.")
    cy = x["cyber"]
    if bank is not None and bank.employer and "meridian" in bank.employer.lower():
        add("work", "Employer IT logs", "data/cyber/identity.csv", "Job and work logs", cy, cy.display_name == full,
            [("same name", int((cy.display_name == full).sum()))],
            lambda r: {"Job title": r.job_title, "Department": r.department, "Shift": r.shift, "Work e-mail": mask_email(r.upn)},
            "The bank says they work at Meridian Logistics; its staff directory has exactly one match.")
    cs = x["cs"]
    tel = add("telecom", "Telecom customers", "data/customer_service/customers.csv", "Contracts and calls", cs,
              (cs.full_name.str.startswith(first)) & cs.full_name.str.endswith(surname) & (cs.postcode == pc),
              [("same name", int((cs.full_name.str.startswith(first) & cs.full_name.str.endswith(surname)).sum()))],
              lambda r: {"Products": r.products, "Private e-mail": mask_email(r.email)},
              "Same name and postcode in the telecom's customer master.")
    if tel is not None:
        calls = x["conv"][x["conv"].customer_id == tel.customer_id]
        steps[-1]["revealed"]["Calls"] = f"{len(calls)}: " + ", ".join(calls.intent.str.replace("_", " ").head(3))
    return steps


def _ours(ch: rc.Chain) -> dict | None:
    f = rc.protected_funnel(ch)
    if not f:
        return None
    n = f[-1].candidates
    holds = n >= 5
    return {"funnel": [[s.clue, s.candidates] for s in f], "candidates": n, "holds": holds,
            "verdict": (f"{n:,} visits still fit. No birth date, postcode or name is released, so nothing joins to other data."
                        if holds else f"Only {n} visits fit. That is below k = 5 for this attacker: a residual risk we report."),
            "revealed": {"Diagnosis group": (ch.clues.get("symptom_group") or "unknown").replace("_", " "),
                         "Pseudonym": "keyed per release, so it cannot be joined to other releases"}}


# ---------------------------------------------------------------- public API
def _title(ch: rc.Chain) -> dict:
    if ch.source == "news":
        c = ch.clues
        return {"kicker": "News clip", "title": "Nobody is named" if not c["full_name"] else f"{c['full_name']} in the news",
                "desc": f"“{'A' if c['age'] else 'Someone'}{' ' + str(c['age']) + '-year-old' if c['age'] else ''} "
                        f"{'woman' if c['sex'] == 'F' else 'man'} in {c['city']}.”"}
    named = bool(ch.clues.get("full_name"))
    return {"kicker": "Social post", "title": "They name themselves" if named else "Only a first name",
            "desc": f"“{ch.post['text'][:70]}”"}


def build_case(source_id: str) -> dict:
    ch = rc.run_chain(source_id)
    case = {"id": source_id, "source": ch.source, **_title(ch), "identified": ch.identified,
            "correct": ch.person_correct, "modes": {}}
    if not ch.identified:
        case["modes"]["names"] = [_source_step(ch), _step("ed", "Hospital ED", "data/health/ed_visits.csv", "release",
                                  "No single visit", len(rc._load()["ed"]), [(f.clue, f.candidates) for f in ch.funnel], {},
                                  "The clues leave more than one person, so the chain stops here.")]
    else:
        case["modes"]["raw"] = _raw_mode(ch)
        case["modes"]["names"] = _names_mode(ch)
        case["person"] = ch.visit["patient_name"].split()[1] + " " + ch.visit["patient_name"].split()[0]
    ours = _ours(ch)
    if ours:
        case["modes"]["ours"] = ours
    return case


FEATURED = ["POST00635", "NEWS00100", "POST00211"]  # the problem demo's two cases, then a post that reaches the school register


@lru_cache(maxsize=1)
def summary() -> dict:
    s = rc.survey()
    out = {}
    for src, g in s.groupby("source"):
        out[src] = {"tested": int(len(g)), "one_patient": int(g.correct.sum()), "wrong": int((g.identified & ~g.correct).sum()),
                    "linked": int((g.correct & (g.datasets_joined > 0)).sum()), "named": int(g.named.sum())}
    return out


@lru_cache(maxsize=1)
def case_list() -> list[dict]:
    s = rc.survey()
    good = s[s.correct].sort_values(["named", "datasets_joined", "steps"], ascending=False)
    d = rc._load()
    posts, news = d["posts"].set_index("adv_row_id"), d["news"].set_index("adv_row_id")
    out = []
    for sid in FEATURED + [x for x in good.post if x not in FEATURED]:
        src = news if sid.startswith("NEWS") else posts
        r = src.loc[sid]
        out.append({"id": sid, "source": "news" if sid.startswith("NEWS") else "post", "featured": sid in FEATURED,
                    "label": (r["headline"] if sid.startswith("NEWS") else (r["display_name"] or "anonymous")) + ": " + r["text"][:70]})
    return out


# ---------------------------------------------------------------- release audit
@lru_cache(maxsize=1)
def _attack_pools() -> pd.DataFrame:
    """Every post and news clip against our release: how small a group can each one narrow it to, and is the
    real person in it? Uses the scoring row map, which never leaves our machine."""
    rel = rc._read(OUTPUTS / "health" / "ed_visits.csv")
    rm = rc._read(OUTPUTS / "health" / "rowmap_ed_visits.csv")
    truth = rc._load()["ed"].set_index("visit_id").person_id
    rows = []
    d = rc._load()
    for sid in list(d["posts"].adv_row_id) + list(d["news"].adv_row_id):
        ch = rc.run_chain(sid)
        n = rc.protected_funnel(ch)[-1].candidates
        rows.append({"id": sid, "source": ch.source, "pool": n, "person_id": ch.post.get("person_id")})
    return pd.DataFrame(rows)


def _pool_contains_truth(df: pd.DataFrame) -> int:
    """Count small pools (1–4) that contain the real person, by re-running those few with the row map."""
    rel = rc._read(OUTPUTS / "health" / "ed_visits.csv")
    rm = rc._read(OUTPUTS / "health" / "rowmap_ed_visits.csv")
    rel["person_id"] = rm.original_record_id.map(rc._load()["ed"].set_index("visit_id").person_id).values
    rel["hour"] = pd.to_datetime(rel.arrival_ts).dt.hour
    hits = 0
    for r in df[(df.pool >= 1) & (df.pool < 5)].itertuples():
        ch = rc.run_chain(r.id)
        pool = _replay(rel, ch)
        hits += int(r.person_id in set(pool.person_id))
    return hits


def _replay(rel: pd.DataFrame, ch: rc.Chain) -> pd.DataFrame:
    c, r = ch.clues, rel
    towns = set(rel.municipality)
    if ch.source == "news":
        if c["hour"] is not None:
            r = r[r.hour.isin([c["hour"], (c["hour"] + 1) % 24])]
        if c["city"]:
            r = r[r.municipality == (c["city"] if c["city"] in towns else "other")]
        if c["age"] is not None:
            bands = {rc._band(a) for a in range(c["age"] - rc.NEWS_AGE_TOLERANCE, c["age"] + rc.NEWS_AGE_TOLERANCE + 1)}
            r = r[r.age.isin(bands)]
    else:
        lo = c["posted"] - pd.Timedelta(hours=rc.ARRIVAL_WINDOW_H[0])
        r = r[r.hour.isin({(lo + pd.Timedelta(hours=h)).hour for h in range(sum(rc.ARRIVAL_WINDOW_H) + 1)})]
        if c["city"]:
            r = r[r.municipality == (c["city"] if c["city"] in towns else "other")]
    if c["symptom_group"] and (r.diagnosis_group == c["symptom_group"]).any():
        r = r[r.diagnosis_group == c["symptom_group"]]
    if c.get("stay_hours"):
        r = rc._stay_filter(r, c["stay_hours"])
    return r


@lru_cache(maxsize=1)
def audit(dataset: str = "health") -> dict:
    """Everything a reviewer needs to sign off one release: who it is for, what was done to each column and why,
    the before/after measurements, every attack, the files with fingerprints, and what risk is left."""
    out = OUTPUTS / dataset
    man = json.loads((out / "manifest.json").read_text())
    sc = json.loads((out / "scorecard.json").read_text())
    log = json.loads((out / "build_log.json").read_text())
    b2 = PG_ROOT / "results" / "b2k" / dataset / "scorecard.json"
    baseline = json.loads(b2.read_text())["summary"] if b2.exists() else None
    ed = sc["tables"]["ed_visits"]
    attacks = [{"adversary": k, "description": v.get("attack"), "before": v.get("baseline_reidentification_rate_original"),
                "after": v.get("reidentification_rate"), "targets": v.get("n_targets_in_data")}
               for k, v in ed["linkage"].items() if isinstance(v, dict) and v.get("evaluated")]
    pools = _attack_pools()
    small = int(((pools.pool >= 1) & (pools.pool < 5)).sum())
    small_true = _pool_contains_truth(pools)
    hist_edges = [0, 1, 5, 10, 50, 100, 500, 1000, 5000, 100000]
    hist = pd.cut(pools.pool, hist_edges, right=False).value_counts().sort_index()
    files = []
    for f in man["files"]:
        p = out / f["name"]
        rows = sum(1 for _ in p.open()) - 1 if p.exists() else None
        files.append({**f, "rows": rows, "bytes": p.stat().st_size if p.exists() else None})
    checks = [
        {"name": "No direct identifiers in the release", "pass": not ed["direct_identifiers_retained"], "detail": "pets-eval scan of every released column"},
        {"name": f"k ≥ {log['k']} on {', '.join(log['qis'])}", "pass": ed["k_anonymity"]["min_k"] >= log["k"],
         "detail": f"smallest group {ed['k_anonymity']['min_k']}, median {ed['k_anonymity']['median_k']:.0f}"},
        {"name": "Official linkage attacks re-identify nobody", "pass": all((a["after"] or 0) == 0 for a in attacks),
         "detail": ", ".join(f"{a['adversary']}: {a['before']:.0%} → {a['after']:.0%}" for a in attacks if a["before"] is not None)},
        {"name": "No scrap narrows the release to one visit", "pass": int((pools.pool == 1).sum()) == 0,
         "detail": f"{len(pools)} posts and news clips replayed; smallest non-empty pool {int(pools.pool[pools.pool > 0].min())}"},
        {"name": "No scrap narrows the release below 5 with the real person in it", "pass": small_true == 0,
         "detail": f"{small_true} of {len(pools)} land in a group of 2–4 that contains the real person"},
        {"name": "Row maps and keys are not in the release", "pass": not any(f["name"].startswith("rowmap_") for f in man["files"]),
         "detail": "manifest lists only released tables; HMAC key stays in .env"},
        {"name": "All required utility tasks answerable", "pass": all(u["score"] > 0 for u in sc["utility"] if u.get("required")),
         "detail": f"{len(sc['utility'])} tasks, mean {sc['summary']['utility']:.2f}"},
    ]
    residual = [
        f"Length of stay and diagnosis group are released but not covered by the k ≥ 5 check. A post that states how long "
        f"someone stayed narrows the release to 2–4 visits for {small_true} of {len(pools)} scraps (real person included). "
        f"Fix to test: release length of stay in 30-minute bands and add it to the k-anonymity check.",
        "The patient pseudonym links all visits of one person inside this release. That is needed for revisit analysis, "
        "but anyone who finds one visit also finds the others.",
        "Lab values are released for every visit; rare test combinations were not checked for uniqueness.",
        "All scores are the toolkit's self-assessment, not the official judging score.",
    ]
    return {
        "release": {**man["scenario"], "created_utc": man["created_utc"], "rows_in": log["rows_in"], "rows_out": log["rows_out"],
                    "k": log["k"], "qis": log["qis"], "k_enforcement": log["k_enforcement"], "lab_rows": log["lab_rows"]},
        "scores": sc["summary"], "baseline": baseline,
        "decisions": man["decisions"],
        "k_anonymity": {"before": ed["k_anonymity_original"], "after": ed["k_anonymity"]},
        "l_diversity": ed["l_diversity"],
        "attacks": attacks,
        "scrap_attack": {"tested": int(len(pools)), "posts": int((pools.source == "post").sum()), "news": int((pools.source == "news").sum()),
                         "pool_1": int((pools.pool == 1).sum()), "pool_2_4": small, "pool_2_4_with_truth": small_true,
                         "median_pool": float(pools.pool.median()),
                         "histogram": [{"bin": f"{int(i.left)}–{int(i.right) - 1}" if i.right - i.left > 1 else f"{int(i.left)}", "count": int(c)}
                                       for i, c in hist.items()]},
        "utility": [{"id": u["id"], "description": u["description"], "score": u["score"], "metric": u["metric"], "required": u.get("required")}
                    for u in sc["utility"]],
        "columns": {"dropped": ed["columns_dropped"], "added": ed["columns_added"]},
        "files": files,
        "checks": checks,
        "residual_risks": residual,
    }
