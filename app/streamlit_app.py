"""PETs Transformer UI. Run with: .venv/bin/streamlit run app/streamlit_app.py

Skeleton: browse the datasets and the baseline scorecards. The Detect, Plan, Transform and
Measure steps are added here as each module lands.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pets import DATA, PG_ROOT  # noqa: E402

st.set_page_config(page_title="PETs Transformer", layout="wide")
st.title("PETs Transformer")
st.caption("Protect the data, keep its value. Beyond Syntax · Since AI Hackathon 2026")

datasets = sorted(p.name for p in DATA.iterdir() if p.is_dir())
dataset = st.sidebar.selectbox("Dataset", datasets, index=datasets.index("health"))
tables = sorted(p.stem for p in (DATA / dataset).glob("*.csv"))
table = st.sidebar.selectbox("Table", tables)

st.subheader(f"{dataset} / {table}")
df = pd.read_csv(DATA / dataset / f"{table}.csv", dtype=str, nrows=200)
st.dataframe(df, width="stretch")

st.subheader("Baseline to beat (B2, classic de-identification)")
sc = PG_ROOT / "results" / "b2" / dataset / "scorecard.json"
if sc.exists():
    summary = json.loads(sc.read_text())["summary"]
    c1, c2, c3 = st.columns(3)
    c1.metric("Privacy", summary["privacy"])
    c2.metric("Utility", summary["utility"])
    c3.metric("Composite", summary["composite"])
else:
    st.info("No baseline scorecard for this dataset.")
