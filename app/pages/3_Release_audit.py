"""Release audit for HEALTH-S1: who the release is for, what was done and why, every measurement and attack,
the released files with fingerprints, the checks and the risk left. Data comes from the PETs Transformer API."""
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api_client import cached  # noqa: E402

st.set_page_config(page_title="Release audit · PETs Transformer", layout="wide")
RISK, OK, MUTED = "#B93E0B", "#1E7A4C", "#8795A1"

a = cached("/api/audit/health")
r, s, b = a["release"], a["scores"], a["baseline"]

st.caption("RELEASE AUDIT · HEALTH-S1")
st.title(r["recipient"])
st.markdown(f"**Purpose:** {r['purpose']}  \n**Trust level:** {r['trust_level'].replace('_', ' ')} · "
            f"**Built:** {r['created_utc'].replace('T', ' ')[:16]} UTC · **Rows:** {r['rows_in']:,} in → {r['rows_out']:,} out · "
            f"**k ≥ {r['k']}** on {', '.join(r['qis'])}")

c = st.columns(4)
for col, key in zip(c[:3], ["privacy", "utility", "composite"]):
    col.metric(key.title(), f"{s[key]:.2f}", f"{s[key] - b[key]:+.2f} vs baseline B2-k" if b else None)
passed = sum(x["pass"] for x in a["checks"])
c[3].metric("Checks passed", f"{passed} of {len(a['checks'])}")
st.caption(s["label"])

st.subheader("Checks")
for x in a["checks"]:
    (st.success if x["pass"] else st.error)(f"**{'Pass' if x['pass'] else 'Fail'} · {x['name']}**  \n{x['detail']}")

left, right = st.columns(2)
with left:
    st.subheader("Official linkage attacks")
    at = a["attacks"]
    fig = go.Figure([go.Bar(name="Before", x=[x["adversary"].replace("_", " ") for x in at], y=[x["before"] for x in at], marker_color=RISK),
                     go.Bar(name="Our release", x=[x["adversary"].replace("_", " ") for x in at], y=[x["after"] for x in at], marker_color=OK)])
    fig.update_layout(barmode="group", yaxis_tickformat=".0%", height=320, margin=dict(l=10, r=10, t=10, b=10), legend_orientation="h")
    st.plotly_chart(fig, width="stretch")
with right:
    sa = a["scrap_attack"]
    st.subheader("Every post and news clip, replayed")
    h = sa["histogram"]
    small = {"0", "1–4"}
    fig = go.Figure(go.Bar(x=[x["bin"] for x in h], y=[x["count"] for x in h],
                           marker_color=[RISK if x["bin"] in small else MUTED for x in h]))
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), xaxis_title="visits left after all clues",
                      yaxis_title="scraps")
    st.plotly_chart(fig, width="stretch")
    st.caption(f"{sa['tested']:,} scraps ({sa['posts']} posts, {sa['news']} news clips). Median pool {sa['median_pool']:.0f}. "
               f"{sa['pool_2_4']} reach 2–4 visits; {sa['pool_2_4_with_truth']} of those contain the real person.")

st.subheader("k-anonymity on the quasi-identifiers")
kb, ka = a["k_anonymity"]["before"], a["k_anonymity"]["after"]
st.dataframe(pd.DataFrame([
    {"": "Before", "Groups": kb["n_classes"], "Smallest group": kb["min_k"], "Rows in groups under 5": f"{kb['share_below']['k<5']:.0%}",
     "Unique rows": f"{kb['sample_uniqueness']:.0%}"},
    {"": "Our release", "Groups": ka["n_classes"], "Smallest group": ka["min_k"], "Rows in groups under 5": f"{ka['share_below']['k<5']:.0%}",
     "Unique rows": f"{ka['sample_uniqueness']:.0%}"}]), hide_index=True, width="stretch")

st.subheader("Utility tasks")
st.dataframe(pd.DataFrame(a["utility"])[["id", "description", "score", "metric"]], hide_index=True, width="stretch",
             column_config={"score": st.column_config.ProgressColumn("Score", min_value=0, max_value=1, format="%.2f")})

st.subheader("Decisions per column")
st.dataframe(pd.DataFrame(a["decisions"]), hide_index=True, width="stretch")

st.subheader("Released files")
st.dataframe(pd.DataFrame(a["files"]), hide_index=True, width="stretch")

st.subheader("Risk left")
for x in a["residual_risks"]:
    st.markdown(f"- {x}")
