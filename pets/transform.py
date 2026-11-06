"""Step 3, Transform: apply the plan with deterministic code.

Owner: Transform. Writes the protected tables plus rowmap_<table>.csv (scoring only, never publish).
Each technique is a small function; a plan maps columns to techniques with parameters and a reason.
"""
import hashlib
import hmac
import os

import numpy as np
import pandas as pd
from pets_eval import parse as Pz


def hmac_pseudonym(value: str, key: bytes | None = None, length: int = 16) -> str:
    """Keyed pseudonym: the same input always gives the same token, so joins and revisits survive.
    Unlike a plain hash it cannot be reversed by hashing a list of candidate values."""
    key = key or os.environ["PETS_HMAC_KEY"].encode()
    return hmac.new(key, str(value).encode(), hashlib.sha256).hexdigest()[:length]


def pseudonymise(s: pd.Series, domain: str, prefix: str = "") -> pd.Series:
    """HMAC per value, keyed by domain so the same id gets different tokens in different releases.
    The letter prefix (e.g. "pt"), written directly before the token, also stops hex tokens from looking like phone numbers to scanners."""
    key = os.environ["PETS_HMAC_KEY"].encode()
    return s.map(lambda v: "" if pd.isna(v) or v == "" else prefix + hmac_pseudonym(f"{domain}:{v}", key))


def age_band(dob: pd.Series, at: pd.Series, width: int = 10, top: int = 80) -> pd.Series:
    """Age at the event in bands (30-39, 80+), from exact birth dates that are then dropped."""
    age = (Pz.to_datetime(at) - Pz.to_datetime(dob)).dt.days / 365.25
    return Pz.to_age_band(age, width=width, top=top)


def month_and_hour(ts: pd.Series) -> pd.Series:
    """Keep only the month and the hour of day: 2025-03-17 14:37 -> 2025-03-01 14:00.
    The day is removed (it links to news and social posts); the hour stays for arrival-curve analysis."""
    t = Pz.to_datetime(ts)
    return t.dt.strftime("%Y-%m-01 %H:00").where(t.notna(), "")


def hour_only(ts: pd.Series, placeholder_date: str = "2025-01-01") -> pd.Series:
    """Keep only the hour of day on a fixed placeholder date: 2025-03-17 14:37 -> 2025-01-01 14:00.
    The real date is removed entirely; the placeholder keeps the column in a standard timestamp format."""
    t = Pz.to_datetime(ts)
    return t.dt.strftime(f"{placeholder_date} %H:00").where(t.notna(), "")


def top_categories(s: pd.Series, keep: list, other: str = "other") -> pd.Series:
    """Keep the listed categories, merge every other value into one group."""
    return s.where(s.isin(keep), other)


def merge_rare(s: pd.Series, min_count: int, other: str = "other") -> pd.Series:
    counts = s.value_counts()
    return s.where(s.map(counts) >= min_count, other)


def fix_fahrenheit(temp: pd.Series) -> pd.Series:
    """Data-quality fix: a few temperatures were recorded in °F."""
    t = Pz.parse_numeric(temp)
    return t.where(t < 50, (t - 32) * 5 / 9).round(1)


def enforce_k(df: pd.DataFrame, qis: list, k: int, coarsen: list) -> tuple[pd.DataFrame, dict]:
    """Make every quasi-identifier combination shared by at least k rows.
    First generalise the listed columns one by one, only for rows still below k; then suppress what remains.
    `coarsen` is a list of (column, function) applied to the small classes."""
    df = df.copy()
    log = {}
    for col, fn in coarsen:
        small = df.groupby(qis, dropna=False)[qis[0]].transform("size") < k
        log[f"generalised {col}"] = int(small.sum())
        df.loc[small, col] = fn(df.loc[small, col])
    small = df.groupby(qis, dropna=False)[qis[0]].transform("size") < k
    log["suppressed rows"] = int(small.sum())
    return df[~small], log
