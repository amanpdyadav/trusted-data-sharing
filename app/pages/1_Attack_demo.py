"""Attack demo: play the attacker against a release before and after protection. All data is synthetic."""
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pets import PG_ROOT  # noqa: E402
from pets import attack_demo as ad  # noqa: E402

st.set_page_config(page_title="Attack demo · PETs Transformer", layout="wide")
st.title("Can an attacker find these patients?")
st.caption("Health / emergency-department visits · attackers use only public knowledge shipped with the challenge · synthetic data")

RELEASES = {
    "Names removed (what most organisations do)": None,
}
if (PG_ROOT / "results" / "quickstart" / "health" / "rowmap_ed_visits.csv").exists():
    RELEASES["Quickstart protection (toolkit example)"] = PG_ROOT / "results" / "quickstart" / "health"
outputs = Path(__file__).resolve().parents[2] / "outputs" / "health"
if (outputs / "rowmap_ed_visits.csv").exists():
    RELEASES["Our release"] = outputs


@st.cache_data(show_spinner="Running the attacks…")
def attack_all(label: str):
    folder = RELEASES[label]
    prot, rm = ad.names_removed("health", "ed_visits") if folder is None else ad.load_release(folder)
    rows = []
    for name, desc in ad.ADVERSARIES.items():
        r = ad.run_attack(prot, rm, name)
        rows.append({"Attacker": desc, "Re-identified": r.get("reidentification_rate", 0.0),
                     "Targets in data": r.get("n_targets_in_data"), "Unique matches claimed": r.get("n_unique_claims"),
                     "Typical candidates per target": r.get("median_candidate_set")})
    return pd.DataFrame(rows), ad.example_matches(prot, n=3)


tab1, tab2 = st.tabs(["Single-dataset attack", "Mosaic: linking two datasets"])

with tab1:
    cols = st.columns(len(RELEASES))
    for col, label in zip(cols, RELEASES):
        with col:
            st.subheader(label)
            table, examples = attack_all(label)
            st.dataframe(table, hide_index=True, width="stretch",
                         column_config={"Re-identified": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=0.2)})
            st.markdown("**What the attacker read, and what it reveals**")
            for e in examples:
                verdict = (f"⚠️ exactly 1 matching visit · diagnosis revealed: `{e['revealed']}`" if e["revealed"]
                           else f"✅ {e['matching_records']} matching visits · cannot tell which")
                st.markdown(f"> {e['attacker_knows'][:220]}\n\n{verdict}")

with tab2:
    st.markdown("Two organisations each publish data **with names removed**. An attacker joins them on "
                "**birth date and postcode** alone.")
    if st.button("Link the hospital and bank releases"):
        with st.spinner("Joining…"):
            r = ad.mosaic_link(("health", "ed_visits"), ("finance", "customers"),
                               ["date_of_birth", "postcode"], ["birth_date", "postcode"])
        c1, c2, c3 = st.columns(3)
        c1.metric("People linked", f"{r['linked']:,}")
        c2.metric("Correct links", f"{r['precision']:.0%}")
        c3.metric("Joined on", "birth date + postcode")
        st.markdown("Each linked row combines a **hospital diagnosis** with **income and occupation** from the bank:")
        st.dataframe(r["matches"][["sex", "municipality", "icd10_primary", "income_band", "occupation"]].head(15),
                     hide_index=True, width="stretch")
