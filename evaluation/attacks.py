"""Replay the problem-demo attacks on any version of the ED-visits table: raw, starter-protected or ours.

An attack is a list of clues from a public scrap (a post, a news clip). Each clue narrows the candidate rows.
Clues understand generalised values (age bands, ISO weeks, rounded hours, value ranges) the way an attacker would:
a row stays a candidate if its value *could* match. A clue whose column was removed is skipped, not failed.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd
from pets_eval import parse as pz

_WEEK = re.compile(r"^\d{4}-?W\d{1,2}$")
_MONTH = re.compile(r"^\d{4}-\d{2}$")
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_YEAR = re.compile(r"^\d{4}$")
_RANGE = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*[-\u2013]\s*(\d+(?:[.,]\d+)?)\s*$")
_PLUS = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*\+\s*$")
OPEN_TOP = 130.0


class Clue(Protocol):
    @property
    def label(self) -> str: ...

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        """Boolean mask of rows that could match, or None when the release has no column for this clue."""
        ...


# ---------------------------------------------------------------- value helpers
def time_intervals(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Start and end of the period each (possibly generalised) timestamp stands for."""
    raw = values.fillna("").astype(str).str.strip()
    start = pz.to_datetime(values)
    width = pd.Series(pd.Timedelta(0), index=values.index)
    width[raw.str.match(_YEAR)] = pd.Timedelta(days=366)
    width[raw.str.match(_MONTH)] = pd.Timedelta(days=31)
    width[raw.str.match(_WEEK)] = pd.Timedelta(days=7)
    width[raw.str.match(_DAY)] = pd.Timedelta(days=1)
    timed = raw.str.contains(r"\d{1,2}:\d{2}", regex=True)
    if timed.any() and (start[timed].dt.minute == 0).all() and (start[timed].dt.second == 0).all():
        width[timed] = pd.Timedelta(hours=1)  # every time is on the hour: the column was rounded to hours
    return start, start + width


def number_intervals(values: pd.Series) -> tuple[pd.Series, pd.Series]:
    """[low, high) for numbers ('37' -> [37, 38) when integer-like), bands ('30-39' -> [30, 40)), '90+'."""
    lo = np.full(len(values), np.nan)
    hi = np.full(len(values), np.nan)
    for i, v in enumerate(values.fillna("").astype(str).str.strip()):
        if m := _RANGE.match(v):
            lo[i], hi[i] = float(m[1].replace(",", ".")), float(m[2].replace(",", ".")) + 1
        elif m := _PLUS.match(v):
            lo[i], hi[i] = float(m[1].replace(",", ".")), OPEN_TOP
        else:
            try:
                x = float(v.replace(",", "."))
            except ValueError:
                continue
            lo[i], hi[i] = x, x
    return pd.Series(lo, index=values.index), pd.Series(hi, index=values.index)


def _overlaps(lo: pd.Series, hi: pd.Series, a: float, b: float) -> pd.Series:
    """Does the value overlap the attacker's range [a, b]? Bands are half-open [lo, hi); exact values are points.

    Unknown values (NaN) stay candidates: the attacker cannot rule them out.
    """
    known = lo.notna() & hi.notna()
    point = known & (lo == hi)
    hit_point = (lo >= a) & (lo <= b)
    hit_band = (lo <= b) & (hi > a)
    return ~known | (point & hit_point) | (~point & hit_band)


# ---------------------------------------------------------------- clues
@dataclass(frozen=True)
class ArrivedBetween:
    start: pd.Timestamp
    end: pd.Timestamp
    label: str
    column: str = "arrival_ts"

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        if self.column not in frame.columns:
            return None
        s, e = time_intervals(frame[self.column])
        return s.isna() | ((s <= self.end) & (e >= self.start))


@dataclass(frozen=True)
class Equals:
    column: str
    value: str
    label: str

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        if self.column not in frame.columns:
            return None
        v = frame[self.column].fillna("").astype(str).str.strip().str.lower()
        return (v == self.value.lower()) | (v == "")


@dataclass(frozen=True)
class AgedBetween:
    low: float
    high: float
    at: pd.Timestamp
    label: str
    columns: tuple[str, ...] = ("age", "age_band", "date_of_birth")

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        col = next((c for c in self.columns if c in frame.columns), None)
        if col is None:
            return None
        if col == "date_of_birth":
            born_start, born_end = time_intervals(frame[col])
            lo = (self.at - born_end).dt.days / 365.25
            hi = (self.at - born_start).dt.days / 365.25
        else:
            lo, hi = number_intervals(frame[col])
        return _overlaps(lo, hi, self.low, self.high)


@dataclass(frozen=True)
class StayedBetween:
    low_min: float
    high_min: float
    label: str
    column: str = "los_minutes"

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        if self.column not in frame.columns:
            return None
        lo, hi = number_intervals(frame[self.column])
        return _overlaps(lo, hi, self.low_min, self.high_min)


@dataclass(frozen=True)
class Injured:
    label: str = "injury diagnosis"

    def matches(self, frame: pd.DataFrame) -> pd.Series | None:
        if "icd10_primary" in frame.columns:
            return frame["icd10_primary"].fillna("").astype(str).str.strip().str.upper().str[:1].isin(["S", "T", ""])
        if "diagnosis_group" in frame.columns:
            return frame["diagnosis_group"].fillna("").astype(str).str.lower().isin(["injury", ""])
        return None


# ---------------------------------------------------------------- running an attack
@dataclass(frozen=True)
class AttackCase:
    id: str
    scrap: str
    description: str
    target_record_id: str  # the visit the scrap is about; used only to report whether the target survived
    clues: tuple[Clue, ...]
    table: str = "ed_visits"


@dataclass(frozen=True)
class FunnelStep:
    label: str
    candidates: int
    applied: bool


@dataclass(frozen=True)
class ReplayResult:
    case_id: str
    funnel: list[FunnelStep] = field(default_factory=list)
    candidates_left: int = 0
    target_among_candidates: bool | None = None


def replay(case: AttackCase, frame: pd.DataFrame, record_ids: Sequence[str] | None = None) -> ReplayResult:
    """Apply the clues in order. `record_ids` (original id per row, from a row map) lets us check the target."""
    mask = pd.Series(True, index=frame.index)
    steps = [FunnelStep("all rows in the release", len(frame), True)]
    for clue in case.clues:
        m = clue.matches(frame)
        if m is None:
            steps.append(FunnelStep(f"{clue.label} (column not released)", int(mask.sum()), False))
            continue
        mask &= m.fillna(True).astype(bool)
        steps.append(FunnelStep(clue.label, int(mask.sum()), True))
    target: bool | None = None
    if record_ids is not None:
        ids = pd.Series(list(record_ids), index=frame.index).astype(str)
        target = bool((ids[mask] == case.target_record_id).any())
    return ReplayResult(case.id, steps, int(mask.sum()), target)
