"""Risk scan of raw data, before any protection: what is exposed, how tables connect, what one person reveals.

Built from the detection report and the data alone, so it shows the problem on a company's own files:
  links       columns that join tables (a visit id in lab results, a patient code in visits)
  exposure    per table: identifiers, facts an outsider may know, sensitive columns, people singled out
  person      everything the files say about one person, gathered across linked tables (the mosaic effect)
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

import pandas as pd

from pets_transformer.assess.lookalikes import lookalikes
from pets_transformer.contracts import ColumnDetection, DetectionReport, PrivacyRole, Subtype

R, S = PrivacyRole, Subtype
PERSON_KEYS = frozenset({S.NATIONAL_ID, S.PATIENT_ID, S.STUDENT_ID, S.CUSTOMER_ID})
# identifiers that also exist in public registers, leaked lists and social media: they link to outside data
OUTSIDE = frozenset({S.PERSON_NAME, S.PHONE, S.EMAIL, S.STREET_ADDRESS, S.NATIONAL_ID, S.IBAN, S.LICENSE_PLATE})
MIN_OVERLAP = 0.5  # share of a column's values found in the other table's key to call it a link
MAX_ROWS_PER_TABLE = 5


@dataclass(frozen=True)
class TableLink:
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    overlap: float  # share of distinct values in from_column that exist in to_column
    meaning: str  # "same record" or "same person"


@dataclass(frozen=True)
class TableExposure:
    table: str
    rows: int
    direct_identifiers: list[str]
    outside_links: list[str]  # columns that match public or leaked sources
    quasi_identifiers: list[str]
    sensitive: list[str]
    free_text: list[str]
    unique_share: float  # people nobody else resembles on the quasi-identifiers
    special_category: bool  # GDPR Art. 9 data (health, ...)


@dataclass(frozen=True)
class RiskScan:
    links: list[TableLink]
    tables: list[TableExposure]
    person: dict[str, list[dict[str, str]]] = field(default_factory=dict)  # table -> rows about one person

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _keys(det: DetectionReport) -> list[ColumnDetection]:
    return [c for c in det.columns if c.privacy_role is R.RECORD_KEY or c.subtype in PERSON_KEYS]


def find_links(det: DetectionReport, frames: Mapping[str, pd.DataFrame]) -> list[TableLink]:
    """Columns whose values are another table's key: same column name, or both person identifiers."""
    links = []
    for key in _keys(det):
        target = set(frames[key.table][key.column].dropna().astype(str)) - {""}
        if not target:
            continue
        for c in det.columns:
            same_kind = c.column == key.column or (c.subtype in PERSON_KEYS and c.subtype == key.subtype)
            if c.table == key.table or not same_kind:
                continue
            values = set(frames[c.table][c.column].dropna().astype(str)) - {""}
            overlap = len(values & target) / len(values) if values else 0.0
            if overlap >= MIN_OVERLAP:
                meaning = "same person" if key.subtype in PERSON_KEYS else "same record"
                links.append(TableLink(c.table, c.column, key.table, key.column, round(overlap, 3), meaning))
    return links


def exposure(det: DetectionReport, frames: Mapping[str, pd.DataFrame]) -> list[TableExposure]:
    out = []
    for table, frame in frames.items():
        cols = [c for c in det.columns if c.table == table]

        def named(pred: object, cols: list[ColumnDetection] = cols) -> list[str]:
            return [c.column for c in cols if pred(c)]  # type: ignore[operator]

        qis = named(lambda c: c.privacy_role is R.QUASI_IDENTIFIER)
        out.append(
            TableExposure(
                table=table, rows=len(frame),
                direct_identifiers=named(lambda c: c.privacy_role is R.DIRECT_IDENTIFIER),
                outside_links=named(lambda c: c.subtype in OUTSIDE),
                quasi_identifiers=qis,
                sensitive=named(lambda c: c.privacy_role is R.SENSITIVE_ATTRIBUTE),
                free_text=named(lambda c: c.privacy_role is R.FREE_TEXT),
                unique_share=round(lookalikes(frame, qis).unique_share, 4) if qis else 0.0,
                special_category=any(c.special_category for c in cols),
            )
        )  # fmt: skip
    return out


def _rows(frame: pd.DataFrame, column: str, value: str) -> list[dict[str, str]]:
    hits = frame[frame[column].astype(str) == value].head(MAX_ROWS_PER_TABLE)
    return [{str(k): str(v) for k, v in row.items() if str(v) not in ("", "nan")} for row in hits.to_dict("records")]


def person_card(
    det: DetectionReport, frames: Mapping[str, pd.DataFrame], links: list[TableLink]
) -> dict[str, list[dict[str, str]]]:
    """Everything about one person across linked tables. Picks someone with several records, as attackers do."""
    person_key = next((c for c in det.columns if c.subtype in PERSON_KEYS), None)
    if person_key is None:
        return {}
    ids = frames[person_key.table][person_key.column].astype(str)
    counts = ids[ids != ""].value_counts()
    if counts.empty:
        return {}
    value = str(
        counts[counts <= MAX_ROWS_PER_TABLE].index[0] if (counts <= MAX_ROWS_PER_TABLE).any() else counts.index[0]
    )
    card = {person_key.table: _rows(frames[person_key.table], person_key.column, value)}
    for link in links:  # tables that point at a key column of the rows already found
        if link.to_table in card and link.from_table not in card:
            keys = {r.get(link.to_column, "") for r in card[link.to_table]} - {""}
            rows = [r for k in sorted(keys) for r in _rows(frames[link.from_table], link.from_column, k)]
            if rows:
                card[link.from_table] = rows[:MAX_ROWS_PER_TABLE]
    return card


def scan(det: DetectionReport, frames: Mapping[str, pd.DataFrame]) -> RiskScan:
    links = find_links(det, frames)
    return RiskScan(links, exposure(det, frames), person_card(det, frames, links))
