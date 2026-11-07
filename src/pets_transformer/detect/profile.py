"""Column statistics the detector reasons with. Format rates use a sample, so 1.6M-row tables stay fast."""

import re
from dataclasses import dataclass, field

import pandas as pd

from pets_transformer.detect.base import match_rate
from pets_transformer.detect.validators import VALIDATORS

SAMPLE = 2000
_NUMBER = re.compile(r"^-?\d{1,3}([ \u00a0]?\d{3})*([.,]\d+)?$|^-?\d+([.,]\d+)?$")  # 3 987,96 and 1234.5
_DATETIME = re.compile(
    r"^(\d{4}-\d{2}-\d{2}([ T]\d{1,2}:\d{2}(:\d{2})?)?"  # ISO date or timestamp
    r"|\d{1,2}[./]\d{1,2}[./]\d{2,4}([ ]\d{1,2}[:.]\d{2})?"  # 22.1.2025 [20.08]
    r"|\d{4}-W\d{2})$"  # ISO week
)
_HAS_TIME = re.compile(r"\d{1,2}[:.]\d{2}$|\d{1,2}:\d{2}:\d{2}$")
_NAME_WORD = re.compile(r"^[A-Za-zÅÄÖåäöÜüÉé'\-]{2,}$")


@dataclass(frozen=True)
class ColumnProfile:
    name: str
    rows: int
    filled: int
    distinct: int
    avg_len: float
    space_share: float  # share of values containing a space (text, names, addresses)
    numeric_share: float
    datetime_share: float
    time_share: float  # of the datetime values, how many carry a time of day
    person_name_share: float  # values shaped like a person's name: 2-5 words of letters
    name_word_share: float  # values made of 1-5 words of letters (single surnames count)
    sample: tuple[str, ...] = ()
    format_rates: dict[str, float] = field(default_factory=dict)

    @property
    def unique_ratio(self) -> float:
        return self.distinct / self.filled if self.filled else 0.0

    @property
    def fill_ratio(self) -> float:
        return self.filled / self.rows if self.rows else 0.0


def _share(values: pd.Series, pattern: re.Pattern[str]) -> float:
    return float(values.str.match(pattern).mean()) if len(values) else 0.0


def _name_words(value: str, minimum: int) -> bool:
    words = value.split()
    return minimum <= len(words) <= 5 and all(_NAME_WORD.match(w) for w in words)


def profile_column(name: str, values: pd.Series) -> ColumnProfile:
    v = values.fillna("").astype(str).str.strip()
    filled = v[v != ""]
    step = max(1, len(filled) // SAMPLE)
    sample = filled.iloc[::step].head(SAMPLE)
    dt = sample.str.match(_DATETIME)
    has = len(sample) > 0
    return ColumnProfile(
        name=name,
        rows=len(v),
        filled=len(filled),
        distinct=int(filled.nunique()),
        avg_len=float(sample.str.len().mean()) if has else 0.0,
        space_share=float(sample.str.contains(" ").mean()) if has else 0.0,
        numeric_share=_share(sample, _NUMBER),
        datetime_share=float(dt.mean()) if has else 0.0,
        time_share=float(sample[dt].str.contains(_HAS_TIME).mean()) if dt.any() else 0.0,
        person_name_share=float(sample.map(lambda x: _name_words(x, 2)).mean()) if has else 0.0,
        name_word_share=float(sample.map(lambda x: _name_words(x, 1)).mean()) if has else 0.0,
        sample=tuple(sample.drop_duplicates().head(10)),
        format_rates={val.name: match_rate(sample, val) for val in VALIDATORS} if has else {},
    )
