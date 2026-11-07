"""Generalisation: keep the information the analysis needs at a coarser, less identifying resolution.

One technique, several named strategies chosen by `params["to"]`:

    age_band   birth date (+ optional reference date column) -> "30-39", top-coded "80+"
    time       timestamp -> "2025-W04" (week) | "2025-01" (month) | "2025-01-22" (day) | "2025-01-22 20:00" (hour)
               | "20:00" (time_of_day: hour of the day only, no date)
    truncate   keep the first n characters, e.g. ICD-10 "S52.5" -> "S52"
    code_group map codes to groups by longest matching prefix, e.g. {"J10": "ILI", "S": "injury"} (a code list)
    number_band  number -> band of a fixed width, e.g. 190 minutes -> "180-209", top-coded "1440+"
    keep_values  keep the listed values, merge every other one, e.g. eight largest municipalities, rest -> "other"

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

_TIME_FORMATS = {
    "hour": "%Y-%m-%d %H:00",
    "day": "%Y-%m-%d",
    "month": "%Y-%m",
    "time_of_day": "%H:00",  # the hour only, no date: keeps daily rhythms, drops when it happened
}


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
        raise ValueError(f"unknown time unit {unit!r}; use week, month, day, hour or time_of_day")
    return _blank_missing(out.astype(str), ts.isna())


def truncate(values: pd.Series, params: Mapping[str, Any], _: TransformContext) -> pd.Series:
    n = int(params["length"])
    if n < 1:
        raise ValueError("truncate length must be at least 1")
    return values.fillna("").astype(str).str.replace(".", "", regex=False).str[:n]


def code_group(values: pd.Series, params: Mapping[str, Any], _: TransformContext) -> pd.Series:
    groups = {str(k).replace(".", "").upper(): str(v) for k, v in dict(params["groups"]).items()}
    default = str(params.get("default", "other"))
    lengths = sorted({len(k) for k in groups}, reverse=True)

    def one(code: str) -> str:
        c = code.replace(".", "").strip().upper()
        if not c:
            return ""
        return next((groups[c[:n]] for n in lengths if c[:n] in groups), default)

    return values.fillna("").astype(str).map(one)


def number_band(values: pd.Series, params: Mapping[str, Any], _: TransformContext) -> pd.Series:
    """Fixed-width bands for a measurement such as length of stay: exact values link to a post that states them."""
    width = int(params["width"])
    top = params.get("top")
    nums = pd.to_numeric(values.fillna("").astype(str).str.replace(",", ".", regex=False), errors="coerce")

    def one(x: float) -> str:
        if pd.isna(x):
            return ""
        if top is not None and x >= float(top):
            return f"{int(top)}+"
        low = int(x // width * width)
        return f"{low}-{low + width - 1}"

    return nums.map(one)


def keep_values(values: pd.Series, params: Mapping[str, Any], _: TransformContext) -> pd.Series:
    """Keep the values an analysis needs (e.g. the eight largest towns); small groups single people out."""
    keep = {str(v) for v in params["keep"]}
    other = str(params.get("other", "other"))
    v = values.fillna("").astype(str)
    return v.where(v.isin(keep) | (v == ""), other)


for _name, _fn in (
    ("keep_values", keep_values),
    ("age_band", age_band),
    ("time", time),
    ("truncate", truncate),
    ("code_group", code_group),
    ("number_band", number_band),
):
    STRATEGIES.register(_name, _fn)


@dataclass(frozen=True)
class Generalise:
    technique: Technique = Technique.GENERALISE

    def apply(self, values: pd.Series, params: Mapping[str, Any], ctx: TransformContext) -> pd.Series:
        if "to" not in params:
            raise ValueError(f"generalise needs params.to, one of {sorted(s.__name__ for s in STRATEGIES)}")
        return STRATEGIES.get(str(params["to"]))(values, params, ctx)


TRANSFORMS.register(Technique.GENERALISE, Generalise())
