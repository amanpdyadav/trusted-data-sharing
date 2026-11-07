"""Mosaic-attack problem demo: follow public scraps across the raw synthetic datasets.

Two traces:
  - trace_post: a social-media post that names the person (POST00635)
  - trace_news: a local news clip with NO name, only age, sex, town and date (NEWS00100)

Every link uses only what an attacker could hold (the public adversary files) plus the raw tables as they
would leak if shared unprotected. Ground-truth files are read ONLY to confirm each link afterwards.

    .venv/bin/python demo/mosaic_attack.py            # writes demo/mosaic_trace.json

The output JSON drives the demo page. All people and values are synthetic (TrustED PETs Proving Ground 2026).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "TRUSTED_PETS_PROVING_GROUND_2026"
OUT = Path(__file__).resolve().parent / "mosaic_trace.json"
QUICKSTART_ED = PKG / "results/quickstart/health/ed_visits.csv"
STARTER_PROTECTION = ("Starter protection: names, ID codes, phones and addresses removed; keyed patient pseudonym; "
                      "10-year age bands; arrival rounded to the hour; ICD-10 cut to 3 characters.")


def read(rel: str) -> pd.DataFrame:
    return pd.read_csv(PKG / rel, dtype=str, keep_default_na=False)


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[^\wåäöÅÄÖ-]+", str(s).lower()) if len(t) > 1}


def name_match(series: pd.Series, name: str) -> pd.Series:
    """True where every token of `name` appears in the row's name (order, case and middle names ignored)."""
    want = tokens(name)
    return series.map(lambda v: bool(want) and want <= tokens(v))


def truth(rel: str) -> dict:
    t = read(rel)
    return dict(zip(t.iloc[:, 0], t.iloc[:, 1]))


def trace_post(POST_ID: str = "POST00635") -> dict:
    posts = read("adversary/social_posts_health.csv")
    post = posts[posts.adv_row_id == POST_ID].iloc[0]
    person = truth("truth/adversary__social_posts_health.csv")[POST_ID]  # used ONLY to verify links
    steps = []

    # 0. the public scrap
    steps.append({
        "id": "post", "dataset": "Social media", "file": "adversary/social_posts_health.csv", "kind": "public",
        "title": "A public post", "rows_total": int(len(posts)),
        "known": {"name": post.display_name, "posted": post.posted_ts, "text": post.text, "place": post.place_tag},
        "funnel": [], "revealed": {}, "verified": True,
        "how": "Anyone can read it. Name, time and the hospital are all in the post.",
    })

    # 1. post -> ED visits: name + arrival in the 12 h before the post
    ed = read("data/health/ed_visits.csv")
    t_post = pd.Timestamp(post.posted_ts)
    arr = pd.to_datetime(ed.arrival_ts)
    m_name = name_match(ed.patient_name, post.display_name)
    m_time = (arr >= t_post - pd.Timedelta(hours=12)) & (arr <= t_post + pd.Timedelta(hours=1))
    hit = ed[m_name & m_time]
    v = hit.iloc[0]
    steps.append({
        "id": "ed", "dataset": "Hospital ED", "file": "data/health/ed_visits.csv", "kind": "leaked",
        "title": "Emergency visit found", "rows_total": int(len(ed)),
        "funnel": [["all visits", int(len(ed))], ["same name", int(m_name.sum())],
                   ["arrived in the 12 h before the post", int(len(hit))]],
        "revealed": {"Diagnosis": f"{v.icd10_primary} (wrist fracture)", "Chief complaint": v.chief_complaint,
                     "Arrival": v.arrival_ts, "Length of stay": f"{v.los_minutes} min (post said ~3 h)",
                     "Disposition": v.disposition, "Birth date": v.date_of_birth, "Postcode": v.postcode,
                     "Phone": v.phone, "National ID": v.patient_hetu},
        "verified": truth("truth/health__ed_visits.csv").get(v.visit_id) == person and len(hit) == 1,
        "how": "Match the name, then keep visits that arrived in the 12 hours before the post.",
    })

    # 2. ED -> public directory: name + postcode
    d = read("adversary/public_directory.csv")
    m_name = d["name"].map(lambda n: bool(tokens(n)) and tokens(n) <= tokens(v.patient_name))
    hit = d[m_name & (d.postcode == v.postcode)]
    dr = hit.iloc[0]
    steps.append({
        "id": "directory", "dataset": "Public directory", "file": "adversary/public_directory.csv", "kind": "public",
        "title": "Home address", "rows_total": int(len(d)),
        "funnel": [["all listings", int(len(d))], ["same name", int(m_name.sum())], ["same postcode", int(len(hit))]],
        "revealed": {"Address": f"{dr.street_address}, {dr.postcode} {dr.city}"},
        "verified": truth("truth/adversary__public_directory.csv").get(dr.adv_row_id) == person and len(hit) == 1,
        "how": "Same name, same postcode as the hospital record.",
    })

    # 3. leaked marketing list: name + city
    lk = read("adversary/leaked_customer_list.csv")
    m_name = name_match(lk["name"], dr["name"])
    hit = lk[m_name & (lk.city == dr.city)]
    steps_leak = None
    if len(hit):
        lr = hit.iloc[0]
        steps_leak = {
            "id": "leak", "dataset": "Old leaked list", "file": "adversary/leaked_customer_list.csv", "kind": "public",
            "title": "Phone and interests", "rows_total": int(len(lk)),
            "funnel": [["all entries", int(len(lk))], ["same name", int(m_name.sum())], ["same city", int(len(hit))]],
            "revealed": {"Phone": lr.phone or "—", "Interest": lr.interest, "Listed": lr.list_year},
            "verified": truth("truth/adversary__leaked_customer_list.csv").get(lr.adv_row_id) == person and len(hit) == 1,
            "how": "A 2019 marketing list leaked online: same name, same city.",
        }
        steps.append(steps_leak)

    # 4. bank customers: name + postcode
    fc = read("data/finance/customers.csv")
    m_name = name_match(fc.full_name, dr["name"])
    hit = fc[m_name & (fc.postcode == dr.postcode)]
    br = hit.iloc[0]
    steps.append({
        "id": "bank", "dataset": "Saaristo Bank", "file": "data/finance/customers.csv", "kind": "leaked",
        "title": "Income and employer", "rows_total": int(len(fc)),
        "funnel": [["all customers", int(len(fc))], ["same name", int(m_name.sum())], ["same postcode", int(len(hit))]],
        "revealed": {"Income band": br.income_band, "Employer": br.employer, "Occupation": br.occupation,
                     "IBAN": br.iban},
        "verified": truth("truth/finance__customers.csv").get(br.customer_id) == person and len(hit) == 1,
        "how": "Same name and postcode as the directory entry.",
    })

    # 5. employer's identity directory (cyber): name, employer from the bank record
    idt = read("data/cyber/identity.csv")
    m_name = name_match(idt.display_name, dr["name"])
    hit = idt[m_name]
    ir = hit.iloc[0]
    steps.append({
        "id": "work", "dataset": "Employer IT logs", "file": "data/cyber/identity.csv", "kind": "leaked",
        "title": "Job, laptop and logs", "rows_total": int(len(idt)),
        "funnel": [["all employees", int(len(idt))], ["same name", int(len(hit))]],
        "revealed": {"Job title": ir.job_title, "Department": ir.department, "Shift": ir["shift"],
                     "Laptop": ir.laptop_hostname, "Work e-mail": ir.upn},
        "verified": truth("truth/cyber__identity.csv").get(ir.identity_id) == person and len(hit) == 1,
        "how": f"The bank says she works at {br.employer}; their staff directory has one match.",
    })
    upn = ir.upn
    counts = {}
    for tbl in ["signin_logs", "proxy_logs", "vpn_logs"]:
        df = pd.read_csv(PKG / f"data/cyber/{tbl}.csv", dtype=str, usecols=["upn"])
        counts[tbl] = int((df.upn == upn).sum())
    steps[-1]["revealed"]["Log events"] = f"{counts['signin_logs']} sign-ins, {counts['proxy_logs']} web requests, {counts['vpn_logs']} VPN events"

    # 6. telecom customer service: name + postcode -> conversations
    cs = read("data/customer_service/customers.csv")
    m_name = name_match(cs.full_name, dr["name"])
    hit = cs[m_name & (cs.postcode == dr.postcode)]
    if len(hit):
        cr = hit.iloc[0]
        conv = read("data/customer_service/conversations.csv")
        mine = conv[conv.customer_id == cr.customer_id]
        steps.append({
            "id": "telecom", "dataset": "Telecom calls", "file": "data/customer_service/customers.csv", "kind": "leaked",
            "title": "Contracts and calls", "rows_total": int(len(cs)),
            "funnel": [["all customers", int(len(cs))], ["same name", int(m_name.sum())], ["same postcode", int(len(hit))]],
            "revealed": {"Products": cr.products.replace("|", ", "), "E-mail": cr.email or "—",
                         "Calls": f"{len(mine)} conversation(s): " + ", ".join(sorted(set(mine.intent)))},
            "verified": truth("truth/customer_service__customers.csv").get(cr.customer_id) == person and len(hit) == 1,
            "how": "Same name and postcode in the telecom's customer master.",
        })

    # AFTER: the same first link against the starter-protected ED table (quickstart output), if present
    after = None
    qs = PKG / "results/quickstart/health/ed_visits.csv"
    if qs.exists():
        p = pd.read_csv(qs, dtype=str, keep_default_na=False)
        pa = pd.to_datetime(p.arrival_ts)
        win = (pa >= t_post - pd.Timedelta(hours=12)) & (pa <= t_post + pd.Timedelta(hours=1))
        fem = win & (p.sex == "F")  # display name is a woman's name
        los = pd.to_numeric(p.los_minutes, errors="coerce")
        three_h = fem & los.between(150, 210)  # "spent 3 hours in the ER"
        injury = three_h & p.icd10_primary.str.startswith(("S", "T"))  # "slipped on ice, wrist pain"
        hit = p[injury]
        after = {
            "source": "results/quickstart/health/ed_visits.csv",
            "protection": "Starter protection: names, ID codes, phones and addresses removed; keyed patient pseudonym; "
                          "10-year age bands; arrival rounded to the hour; ICD-10 cut to 3 characters.",
            "funnel": [["all protected visits", int(len(p))], ["arrived in the 12 h before the post", int(win.sum())],
                       ["female (from the name)", int(fem.sum())], ["stayed about 3 hours", int(three_h.sum())],
                       ["injury diagnosis (slipped, wrist)", int(len(hit))]],
            "revealed": ({"Age band": hit.iloc[0].age, "Municipality": hit.iloc[0].municipality,
                          "Diagnosis": hit.iloc[0].icd10_primary, "Disposition": hit.iloc[0].disposition,
                          "Patient pseudonym": hit.iloc[0].patient_pseudonym + " (links her other visits)"}
                         if len(hit) == 1 else {}),
            "verified": len(hit) == 1 and truth("truth/health__ed_visits.csv").get(hit.iloc[0].visit_id) == person,
            "note": "No name needed: the post's own clues (time, sex, length of stay, injury) single out one visit.",
        }

    return {"source_id": POST_ID, "person_id_for_verification_only": person, "steps": steps, "after": after,
            "all_links_verified": all(s["verified"] for s in steps) and bool(after and after["verified"])}


def trace_news(NEWS_ID: str = "NEWS00100") -> dict:
    """A news clip without a name: age, sex, town and date are enough to find the visit, which supplies the name."""
    news = read("adversary/news_clips_health.csv")
    clip = news[news.adv_row_id == NEWS_ID].iloc[0]
    person = truth("truth/adversary__news_clips_health.csv")[NEWS_ID]  # used ONLY to verify links
    age, sex, town = int(clip.age_mentioned), clip.sex_mentioned, clip.place
    day = pd.Timestamp(clip.event_date or clip.published_date)
    steps = [{
        "id": "news", "dataset": "Local news", "file": "adversary/news_clips_health.csv", "kind": "public",
        "title": "A news clip, no name", "rows_total": int(len(news)),
        "known": {"headline": clip.headline, "published": clip.published_date, "text": clip.text,
                  "age": age, "sex": sex, "place": town},
        "funnel": [], "revealed": {}, "verified": True,
        "how": "No name anywhere. Only an age, a sex, a town and a date.",
    }]

    # 1. clip -> ED: arrival on the day (and the evening before), town, sex, age within 3 years, injury code
    ed = read("data/health/ed_visits.csv")
    arr = pd.to_datetime(ed.arrival_ts)
    on_day = (arr >= day - pd.Timedelta(days=1)) & (arr < day + pd.Timedelta(days=1))
    in_town = on_day & (ed.municipality == town)
    of_sex = in_town & (ed.sex == sex)
    ages = (day - pd.to_datetime(ed.date_of_birth, errors="coerce")).dt.days / 365.25
    of_age = of_sex & ages.between(age - 3, age + 3 + 1)
    injury = of_age & ed.icd10_primary.str.startswith(("S", "T"))
    hit = ed[injury]
    v = hit.iloc[0]
    steps.append({
        "id": "ed", "dataset": "Hospital ED", "file": "data/health/ed_visits.csv", "kind": "leaked",
        "title": "Emergency visit, and a name", "rows_total": int(len(ed)),
        "funnel": [["all visits", int(len(ed))], ["arrived that day or the evening before", int(on_day.sum())],
                   [f"lives in {town}", int(in_town.sum())], ["male" if sex == "M" else "female", int(of_sex.sum())],
                   [f"aged about {age}", int(of_age.sum())], ["injury diagnosis", int(len(hit))]],
        "revealed": {"Name": v.patient_name, "Diagnosis": f"{v.icd10_primary}", "Chief complaint": v.chief_complaint,
                     "Arrival": v.arrival_ts, "Birth date": v.date_of_birth, "Postcode": v.postcode,
                     "National ID": v.patient_hetu, "Phone": v.phone},
        "verified": truth("truth/health__ed_visits.csv").get(v.visit_id) == person and len(hit) == 1,
        "how": "Narrow the visits by the clip’s date, town, sex and age. The record that is left has his name.",
    })

    # 2. same table, same name + birth date -> his other visits (medical history)
    m_hist = name_match(ed.patient_name, v.patient_name) & (ed.date_of_birth == v.date_of_birth)
    other = ed[m_hist & (ed.visit_id != v.visit_id)]
    tr = truth("truth/health__ed_visits.csv")
    steps.append({
        "id": "history", "dataset": "Hospital ED", "file": "data/health/ed_visits.csv", "kind": "leaked",
        "title": "His other hospital visits", "rows_total": int(len(ed)),
        "funnel": [["all visits", int(len(ed))], ["same name and birth date", int(m_hist.sum())],
                   ["other than the fireworks visit", int(len(other))]],
        "revealed": {f"Visit {i + 1}": f"{r.arrival_ts[:10]}: {r.icd10_primary}, {r.chief_complaint}"
                     for i, r in enumerate(other.itertuples())},
        "verified": len(other) > 0 and all(tr.get(x) == person for x in other.visit_id),
        "how": "Now that the name is known, search the same table again.",
    })

    # 3. directory: name + postcode
    d = read("adversary/public_directory.csv")
    m_name = d["name"].map(lambda n: bool(tokens(n)) and tokens(n) <= tokens(v.patient_name))
    hit = d[m_name & (d.postcode == v.postcode)]
    dr = hit.iloc[0]
    steps.append({
        "id": "directory", "dataset": "Public directory", "file": "adversary/public_directory.csv", "kind": "public",
        "title": "Home address", "rows_total": int(len(d)),
        "funnel": [["all listings", int(len(d))], ["name fits the hospital record", int(m_name.sum())],
                   ["same postcode", int(len(hit))]],
        "revealed": {"Home address": f"{dr.street_address}, {dr.postcode} {dr.city}"},
        "verified": truth("truth/adversary__public_directory.csv").get(dr.adv_row_id) == person and len(hit) == 1,
        "how": "Same name, same postcode as the hospital record.",
    })

    # 4. bank: full name from hospital + postcode
    fc = read("data/finance/customers.csv")
    m_name = name_match(fc.full_name, v.patient_name)
    hit = fc[m_name & (fc.postcode == v.postcode)]
    br = hit.iloc[0]
    steps.append({
        "id": "bank", "dataset": "Saaristo Bank", "file": "data/finance/customers.csv", "kind": "leaked",
        "title": "Income and employer", "rows_total": int(len(fc)),
        "funnel": [["all customers", int(len(fc))], ["same full name", int(m_name.sum())],
                   ["same postcode", int(len(hit))]],
        "revealed": {"Income band": br.income_band, "Employer": br.employer, "Occupation": br.occupation,
                     "E-mail": br.email, "IBAN": br.iban},
        "verified": truth("truth/finance__customers.csv").get(br.customer_id) == person and len(hit) == 1,
        "how": "All four given names and the postcode match the hospital record.",
    })

    # (City feedback by home address was tried and rejected: the requests at that address were filed by
    #  other residents, so verification failed. An address is shared; it is not a person.)

    # AFTER: same clip against the starter-protected table
    after = None
    if QUICKSTART_ED.exists():
        p = pd.read_csv(QUICKSTART_ED, dtype=str, keep_default_na=False)
        pa = pd.to_datetime(p.arrival_ts)
        a_day = (pa >= day - pd.Timedelta(days=1)) & (pa < day + pd.Timedelta(days=1))
        a_town = a_day & (p.municipality == town)
        a_sex = a_town & (p.sex == sex)
        lo = (age // 10) * 10
        band = f"{lo}-{lo + 9}" if age < 80 else "80+"
        a_age = a_sex & (p.age == band)
        a_inj = a_age & p.icd10_primary.str.startswith(("S", "T"))
        h = p[a_inj]
        after = {
            "source": "results/quickstart/health/ed_visits.csv", "protection": STARTER_PROTECTION,
            "funnel": [["all protected visits", int(len(p))], ["arrived that day or the evening before", int(a_day.sum())],
                       [f"lives in {town}", int(a_town.sum())], ["male" if sex == "M" else "female", int(a_sex.sum())],
                       [f"age band {band}", int(a_age.sum())], ["injury diagnosis", int(len(h))]],
            "revealed": ({"Age band": h.iloc[0].age, "Municipality": h.iloc[0].municipality,
                          "Diagnosis": h.iloc[0].icd10_primary, "Disposition": h.iloc[0].disposition,
                          "Patient pseudonym": h.iloc[0].patient_pseudonym + " (links his other visits)"}
                         if len(h) == 1 else {}),
            "verified": len(h) == 1 and truth("truth/health__ed_visits.csv").get(h.iloc[0].visit_id) == person,
            "candidates": int(len(h)),
        }
    return {"source_id": NEWS_ID, "person_id_for_verification_only": person, "steps": steps, "after": after,
            "all_links_verified": all(s["verified"] for s in steps)}


def main() -> None:
    people = [trace_post(), trace_news()]
    OUT.write_text(json.dumps({"people": people}, ensure_ascii=False, indent=1), encoding="utf-8")
    for t in people:
        print(f"== {t['source_id']}  all links verified: {t['all_links_verified']}")
        for s in t["steps"]:
            print(f"  {s['dataset']:18s} {'OK ' if s['verified'] else 'BAD'} {s['funnel']}")
        if t["after"]:
            print(f"  AFTER (names removed): {t['after']['funnel']}  verified={t['after']['verified']}")


if __name__ == "__main__":
    main()
