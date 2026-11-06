"""Small client for the PETs Transformer API, shared by the Streamlit pages.

The API must be running: .venv/bin/uvicorn api.main:app --port 8000 (or set PETS_API_URL).
"""
import os

import httpx
import streamlit as st

API = os.environ.get("PETS_API_URL", "http://localhost:8000")


def get(path: str, timeout: float = 120):
    try:
        r = httpx.get(f"{API}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except httpx.ConnectError:
        st.error(f"The API is not running at {API}. Start it with: `.venv/bin/uvicorn api.main:app --port 8000`")
        st.stop()
    except httpx.HTTPStatusError as e:
        st.error(f"The API returned {e.response.status_code}: {e.response.text[:200]}")
        st.stop()


@st.cache_data(show_spinner="Loading from the API…", ttl=600)
def cached(path: str):
    return get(path)
