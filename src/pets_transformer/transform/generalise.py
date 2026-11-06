"""Generalisation: keep the information the analysis needs at a coarser, less identifying resolution.

One technique, several named strategies chosen by `params["to"]`:

    age_band   birth date (+ optional reference date column) -> "30-39", top-coded "80+"
    time       timestamp -> "2025-W04" (week) | "2025-01" (month) | "2025-01-22" (day) | "2025-01-22 20:00" (hour)
    truncate   keep the first n characters, e.g. ICD-10 "S52.5" -> "S52"

Missing or unparseable values stay empty; they are never invented. Add a strategy by registering a function.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pandas as pd

from pets_transformer.contracts import Technique
from pets_transformer.registry import Registry
from pets_transformer.transform.base import TRANSFORMS, TransformContext

Strategy = Callable[[pd.Series, Mapping[str, Any], TransformContext], pd.Series]
STRATEGIES: Registry[str, Strategy] = Registry("generalisation")

_TIME_FORMATS = {"hour": "%Y-%m-%d %H:00", "day": "%Y-%m-%d", "month": "%Y-%m"}


def _to_datetime(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.replace("", None), errors="coerce", format="mixed")


def _blank_missing(out: pd.Series, missing: pd.Series) -> pd.Series:
    return out.where(~missing, "")


def age_band(values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
    width = int(params.get("width", 10))
    top = int(params.get("top", 80))
    if width < 1 or top % width:
        raise ValueError("age_band needs width >= 1 and a top that is a multiple of width")
    born = _to_datetime(values)
    ref_col = params.get("reference_column")
    ref = (
        _to_datetime(ctx.source_column(ref_col))
        if ref_col
        else pd.Series(pd.Timestamp(params["at"]), index=values.index)
    )
    years = (ref - born).dt.days / 365.25
    low = ((years // width) * width).clip(lower=0, upper=top)
    labels = low.map(lambda lo: _band_label(lo, width, top))
    return _blank_missing(labels.astype(str), years.isna())


def _band_label(low: float, width: int, top: int) -> str:
    if pd.isna(low):
        return ""
    lo = int(low)
    return f"{lo}+" if lo >= top else f"{lo}-{lo + width - 1}"


def time(values: pd.Series, params: Mapping[str, Any], _: TransformContext) -> pd.Series:
    unit = str(params.get("unit", "week"))
    ts = _to_datetime(values)
    if unit == "week":
        iso = ts.dt.isocalendar()
        out = iso.year.astype("Int64").astype(str) + "-W" + iso.week.astype("Int64").astype(str).str.zfill(2)
    elif unit in _TIME_FORMATS:
        out = ts.dt.strftime(_TIME_FORMATS[unit])
    else:
        raise ValueError(f"unknown time unit {unit!r}; use week, month, day or hour")
    return _blank_missing(out.astype(str), ts.isna())


def truncate(values: pd.Series, params: Mapping[str, Any], _: TransformContext) -> pd.Series:
    n = int(params["length"])
    if n < 1:
        raise ValueError("truncate length must be at least 1")
    return values.fillna("").astype(str).str.replace(".", "", regex=False).str[:n]


for _name, _fn in (("age_band", age_band), ("time", time), ("truncate", truncate)):
    STRATEGIES.register(_name, _fn)


@dataclass(frozen=True)
class Generalise:
    technique: Technique = Technique.GENERALISE

    def apply(self, values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
        if "to" not in params:
            raise ValueError(f"generalise needs params.to, one of {sorted(s.__name__ for s in STRATEGIES)}")
        return STRATEGIES.get(str(params["to"]))(values, params, ctx)


TRANSFORMS.register(Technique.GENERALISE, Generalise())
