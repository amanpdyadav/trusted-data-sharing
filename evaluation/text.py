"""Score free-text redaction against the package's gold spans (evaluation only: uses the answer key).

The redactor is built exactly as a release builds it: known names come from the person-name columns our own
detector finds in the dataset, never from the answer files. Every row of the table is redacted, so extra tags
on rows without gold spans count against precision.

Development columns were looked at while writing the rules; held-out columns were not. The 'before' is the
package quickstart's regex. Gold files do not label every identifier in every record (many real phone numbers and
names in customer_service turns are unlabelled), so precision here is a lower bound.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from pets_eval.text import IDENTIFYING, redaction_leakage, span_scores

from pets_transformer.contracts import Subtype
from pets_transformer.detect.source import detect_source
from pets_transformer.io import read_table
from pets_transformer.sources import open_source
from pets_transformer.text.redactor import Redactor, build_redactor

QUICKSTART = re.compile(r"\b\d{6}[-+A]\d{3}[0-9A-Y]\b|\+?\d[\d\s-]{7,}\d")  # examples/quickstart.py, verbatim


@dataclass(frozen=True)
class TextColumn:
    dataset: str
    table: str
    column: str

    @property
    def ref(self) -> str:
        return f"{self.dataset}.{self.table}.{self.column}"

    @property
    def span_file(self) -> str:
        return f"{self.dataset}__{self.table}__{self.column}.jsonl"


# Looked at while writing the rules (agent notes and cyber tickets after a first held-out run exposed misses).
DEV = (
    TextColumn("health", "clinical_notes", "note_text"),
    TextColumn("health", "ed_visits", "chief_complaint"),
    TextColumn("customer_service", "turns", "text"),
    TextColumn("customer_service", "conversations", "agent_note"),
    TextColumn("cyber", "incident_tickets", "description"),
)
# Never inspected: the honest estimate for unseen company text.
HELD_OUT = (
    TextColumn("education", "counsellor_notes", "note_text"),
    TextColumn("energy", "customers", "dso_notes"),
    TextColumn("finance", "transfers", "message"),
    TextColumn("public_admin", "service_requests", "description"),
    TextColumn("public_admin", "service_requests", "response_text"),
)


@dataclass(frozen=True)
class TextScore:
    column: TextColumn
    split: str  # "dev" or "held-out"
    method: str  # "quickstart" or "ours"
    records: int
    gold_values: int
    leakage: float  # share of identifying gold values still readable in the protected text
    recall: float  # identifying gold spans overlapped by a tag (any label)
    precision: float
    f2: float

    def row(self) -> dict[str, Any]:
        return {
            "column": self.column.ref, "split": self.split, "method": self.method, "records": self.records,
            "gold_values": self.gold_values, "leakage": self.leakage, "recall": self.recall,
            "precision": self.precision, "f2": self.f2,
        }  # fmt: skip


def load_gold(path: Path) -> dict[str, list[dict[str, Any]]]:
    with path.open(encoding="utf-8") as f:
        return {r["record_id"]: r["spans"] for r in map(json.loads, f) if r.get("spans")}


def known_names(package_root: Path, dataset: str) -> list[str]:
    """Values of the person-name columns our detector finds: what a release would pass as known_from."""
    return _detected_names(package_root / "data" / dataset, dataset)


def _detected_names(folder: Path, dataset: str) -> list[str]:
    source = open_source(f"csv:{folder}")
    report = detect_source(source, dataset)
    return [v for c in report.columns if c.subtype is Subtype.PERSON_NAME for v in source.read(c.table)[c.column] if v]


def _quickstart_spans(text: str) -> list[dict[str, Any]]:
    return [{"start": m.start(), "end": m.end(), "label": "ANY"} for m in QUICKSTART.finditer(text)]


def _our_spans(redactor: Redactor) -> Callable[[str], list[dict[str, Any]]]:
    return lambda text: [{"start": s.start, "end": s.end, "label": s.label.value} for s in redactor.spans(text)]


@dataclass(frozen=True)
class _Case:
    column: TextColumn
    split: str
    texts: dict[str, str]  # record id -> original text, every row of the table
    gold: dict[str, Any]


def _score(case: _Case, method: str, find: Callable[[str], list[dict[str, Any]]]) -> TextScore:
    pred = {rid: find(t) for rid, t in case.texts.items()}
    protected = {rid: _apply(t, pred[rid]) for rid, t in case.texts.items()}
    leak = redaction_leakage(case.gold, protected, labels=IDENTIFYING)
    spans = span_scores(case.gold, pred, mode="overlap", label_agnostic=True, labels=IDENTIFYING)["micro"]
    return TextScore(
        case.column, case.split, method, len(case.texts), int(leak["n_values"]), float(leak["leakage_rate"]),
        float(spans["recall"]), float(spans["precision"]), float(spans["f2"]),
    )  # fmt: skip


def _apply(text: str, spans: list[dict[str, Any]]) -> str:
    for s in sorted(spans, key=lambda s: s["start"], reverse=True):
        text = text[: s["start"]] + "[X]" + text[s["end"] :]
    return text


def score_column(package_root: Path, col: TextColumn, split: str, names: list[str]) -> list[TextScore]:
    frame = read_table(package_root / "data" / col.dataset / f"{col.table}.csv")
    id_column = frame.columns[0]
    texts = dict(zip(frame[id_column], frame[col.column], strict=True))
    gold = load_gold(package_root / "metadata" / "pii_spans" / col.span_file)
    missing = set(gold) - set(texts)
    if missing:
        raise ValueError(f"{col.ref}: {len(missing)} gold records are not in {id_column}")
    case = _Case(col, split, texts, gold)
    return [_score(case, "quickstart", _quickstart_spans), _score(case, "ours", _our_spans(build_redactor(names)))]


def score_all(package_root: Path) -> list[TextScore]:
    names: dict[str, list[str]] = {}
    out: list[TextScore] = []
    for split, cols in (("dev", DEV), ("held-out", HELD_OUT)):
        for col in cols:
            if col.dataset not in names:
                names[col.dataset] = known_names(package_root, col.dataset)
            out += score_column(package_root, col, split, names[col.dataset])
    return out


def write_scores(scores: list[TextScore], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([s.row() for s in scores]).to_csv(path, index=False, lineterminator="\n")


def redact_eval_split(package_root: Path, out: Path) -> int:
    """The organisers' hidden-gold check: redact holdout/customer_service turns to turn_id,text.

    Known names come from the person-name columns our detector finds in the holdout folder itself.
    """
    folder = package_root / "holdout" / "customer_service"
    turns = read_table(folder / "turns.csv")
    redactor = build_redactor(_detected_names(folder, "customer_service"))
    out.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"turn_id": turns["turn_id"], "text": turns["text"].map(redactor.redact)}).to_csv(
        out, index=False, lineterminator="\n"
    )
    return len(turns)


def summary(scores: list[TextScore]) -> pd.DataFrame:
    """Value-weighted leakage and recall per split and method."""
    df = pd.DataFrame([s.row() for s in scores])
    df["leaked"] = df["leakage"] * df["gold_values"]
    df["hit"] = df["recall"] * df["gold_values"]
    g = df.groupby(["split", "method"], sort=False)[["gold_values", "leaked", "hit"]].sum()
    return pd.DataFrame({
        "gold_values": g["gold_values"],
        "leakage": (g["leaked"] / g["gold_values"]).round(4),
        "recall": (g["hit"] / g["gold_values"]).round(4),
    }).reset_index()  # fmt: skip
