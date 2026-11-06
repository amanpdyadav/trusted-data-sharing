"""HEALTH-S1 release: ED visits and lab results for a university research group in a controlled environment.

Purpose (from the scenario): length of stay, 30-day revisits and diagnosis patterns, plus the CRP-temperature
relationship. Everything else is minimised. Each decision below carries the reason shown in the app and manifest.
"""
import json
from pathlib import Path

import pandas as pd
from pets_eval import io
from pets_eval.utility.health import diagnosis_group

from . import DATA, OUTPUTS, PG_ROOT
from . import transform as T

SCENARIO = "HEALTH-S1"
K = 5
QIS = ["age", "municipality", "arrival_ts"]  # the quasi-identifiers left in the release

DECISIONS = [
    ("visit_id", "keyed pseudonym", "Joins visits to lab results without exposing the hospital's sequential visit numbers."),
    ("patient_hetu", "keyed pseudonym → patient_pseudonym", "Revisit analysis needs to know which visits belong to one patient, not who the patient is. The ID code itself also encodes birth date and sex."),
    ("patient_name", "drop", "Not needed for any research question."),
    ("phone", "drop", "Not needed for any research question."),
    ("home_address", "drop", "Not needed for any research question."),
    ("date_of_birth", "→ 10-year age band at arrival", "Revisit rates are analysed by age band; exact birth dates make 99% of patients unique."),
    ("sex", "drop", "None of this scenario's questions use it, and it is one of the attributes news stories match on. Dropping it lets far more visits keep their municipality."),
    ("postcode", "drop", "Municipality is enough for the regional analysis; rural postcodes have very few residents."),
    ("municipality", "keep 8 largest, merge the rest", "The diagnosis-mix analysis covers the eight largest municipalities; small municipalities single people out."),
    ("arrival_ts", "→ hour of day only (date set to 2025-01-01)", "The arrival-time analysis needs the hour; the date is what news stories and social posts match on, and length of stay and revisits are already kept as their own columns."),
    ("arrival_mode", "drop", "Not needed for this scenario; helicopter and police arrivals are rare and newsworthy."),
    ("ambulance_unit", "drop", "Unit base codes reveal the patient's home area."),
    ("triage", "keep", "Length of stay is analysed by triage level."),
    ("chief_complaint", "drop (until free-text redaction is ready)", "Free text can name workplaces and places."),
    ("icd10_primary", "→ diagnosis group", "The research asks about diagnosis patterns; exact and rare codes (mental health, pregnancy) are near-unique."),
    ("icd10_secondary", "drop", "Rare chronic diseases single out patients across visits."),
    ("systolic_bp, diastolic_bp, heart_rate, resp_rate, spo2, pain_nrs", "drop", "Not needed for this scenario's questions (data minimisation)."),
    ("temp_c", "keep, fix °F values", "Needed for the CRP–temperature analysis; a few values were recorded in °F."),
    ("attending_physician_id, attending_physician_name", "drop", "Staff are data subjects too; shift patterns identify them."),
    ("discharge_ts", "drop", "Length of stay is kept as minutes, so the exact discharge time adds only linkage risk."),
    ("los_minutes, disposition, readmit_30d", "keep", "These are the outcomes the research group studies."),
    ("lab_results", "release CRP and routine tests, joined by pseudonymised visit", "CRP–temperature analysis needs the join; sample times, sex-specific reference ranges and blood-alcohol and pregnancy tests are removed."),
    ("rows", "enforce k ≥ 5 on age band, municipality and arrival hour", "Merge the municipality into 'other' only where groups are small, then suppress the few rows still below 5."),
]


def build(out_dir: Path | None = None) -> dict:
    out = Path(out_dir or OUTPUTS / "health")
    out.mkdir(parents=True, exist_ok=True)
    v = io.read_table(DATA / "health" / "ed_visits.csv")
    v = v[v.disposition != "cancelled_duplicate"]

    p = pd.DataFrame(index=v.index)
    p["visit_id"] = T.pseudonymise(v.visit_id, "health-s1-visit", "v")
    p["patient_pseudonym"] = T.pseudonymise(v.patient_hetu, "health-s1-patient", "pt")
    p["age"] = T.age_band(v.date_of_birth, v.arrival_ts)
    top8 = v[~v.municipality.isin(["", "non-resident"])].municipality.value_counts().index[:8].tolist()
    p["municipality"] = T.top_categories(v.municipality, top8, "other")
    p["arrival_ts"] = T.hour_only(v.arrival_ts)
    p["triage"] = v.triage
    p["diagnosis_group"] = diagnosis_group(v.icd10_primary).fillna("other")
    p["temp_c"] = T.fix_fahrenheit(v.temp_c)
    for c in ("los_minutes", "disposition", "readmit_30d"):
        p[c] = v[c]

    p, klog = T.enforce_k(p, QIS, K, coarsen=[("municipality", lambda s: "other")])
    rowmap = pd.DataFrame({"protected_row": range(len(p)), "original_record_id": v.loc[p.index, "visit_id"].values})
    p = p.reset_index(drop=True)
    p.to_csv(out / "ed_visits.csv", index=False)
    rowmap.to_csv(out / "rowmap_ed_visits.csv", index=False)

    labs = io.read_table(DATA / "health" / "lab_results.csv")
    labs = labs[labs.visit_id.isin(set(rowmap.original_record_id)) & ~labs.test_code.isin(["P-Etanol", "U-hCG"])]
    lp = pd.DataFrame({"lab_id": T.pseudonymise(labs.lab_id, "health-s1-lab", "lab"),
                       "visit_id": T.pseudonymise(labs.visit_id, "health-s1-visit", "v")})
    for c in ("test_code", "test_name", "value", "unit", "abnormal_flag"):
        lp[c] = labs[c].values
    lp.to_csv(out / "lab_results.csv", index=False)
    pd.DataFrame({"protected_row": range(len(lp)), "original_record_id": labs.lab_id.values}).to_csv(
        out / "rowmap_lab_results.csv", index=False)

    info = {"scenario": SCENARIO, "k": K, "qis": QIS, "rows_in": int(len(v)), "rows_out": int(len(p)),
            "k_enforcement": klog, "lab_rows": int(len(lp))}
    (out / "build_log.json").write_text(json.dumps(info, indent=2))
    return info


def scenario() -> dict:
    return io.get_scenario(SCENARIO, PG_ROOT)
