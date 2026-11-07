"""Columns without a real name: find them, suggest names, and apply the names a person confirmed.

A column has no real name when its header is blank (pandas reads it as "Unnamed: 3"), a generic code (c01, col5,
field_7, V12, X) or when the file has no header row at all (the session then reads it as col_01, col_02 ...).
Columns with a real name are never renamed, by the suggestions or by a request.

Suggestions come from the rules first: a column whose values pass a strict format check (Finnish ID code with its
check digit, IBAN, email, phone ...) is named from that check. Only the rest go to the local AI, and only as a small
summary per column: a profile, at most 8 short sample values and the names around it, a few columns per call and a
capped prompt size. The AI never sees the table, never names a column that has a name, and a person confirms every
name before it is used. The names are recorded in the plan (and so in the release manifest) with who suggested them.
"""

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from pets_transformer.contracts import ColumnName
from pets_transformer.detect import checks
from pets_transformer.llm import LlmClient, LlmUnavailableError
from pets_transformer.sources import TableSource

# A blank header, or a letter code with a number and nothing else. "age", "sex", "v2x_score" are names.
UNNAMED = re.compile(r"^\s*$|^unnamed: ?\d+$|^(?:c|col|column|field|var|v|x|f)[ _\-]?\d{1,4}$|^x$", re.IGNORECASE)
NAME = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

PROFILE_ROWS = 5_000  # the profile reads a random sample of this many rows, never the whole of a big table
SAMPLES = 8  # distinct example values per column sent to the AI
SAMPLE_CHARS = 40  # each example value is cut to this length
BATCH = 8  # columns per AI call
PROMPT_TOKENS = 2_000  # a batch whose prompt would be longer is split
STRONG = 0.9  # share of values that must pass a format check for the rules to name a column

# Format checks that say what a column is on their own. Weaker shapes (dates, numbers, codes) go to the AI.
RULE_NAMES = {
    "hetu": ("national_id", "Finnish personal identity code (check digit valid)"),
    "iban": ("iban", "Bank account number (IBAN, check digits valid)"),
    "payment_card": ("card_number", "Payment card number (Luhn check valid)"),
    "business_id": ("business_id", "Finnish business ID (check digit valid)"),
    "email": ("email", "Email address"),
    "phone": ("phone", "Phone number"),
    "ipv4": ("ip_address", "IPv4 address"),
    "ipv6": ("ip_address", "IPv6 address"),
    "mac": ("mac_address", "Network card (MAC) address"),
    "plate": ("license_plate", "Finnish licence plate"),
    "gsrn": ("metering_point_id", "Electricity metering point ID (GSRN)"),
    "coordinate": ("coordinates", "GPS coordinates"),
    "user_agent": ("user_agent", "Browser user agent"),
    "icd10": ("diagnosis_code", "ICD-10 diagnosis code"),
    "street_address": ("street_address", "Street address"),
}


def is_unnamed(header: str) -> bool:
    return bool(UNNAMED.match(str(header)))


def looks_headerless(headers: list[str]) -> bool:
    """True when most of the header row looks like data (IDs, numbers, dates, emails), not like column names."""

    def data_like(h: str) -> bool:
        h = h.strip()
        if not h or is_unnamed(h):
            return False
        digits = sum(ch.isdigit() for ch in h)
        return "@" in h or digits / len(h) >= 0.5 or bool(re.fullmatch(r"[\d\s.,:+\-/]+", h))

    return len(headers) > 0 and sum(data_like(h) for h in headers) * 2 >= len(headers)


def renames_by_table(names: Iterable[ColumnName]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for n in names:
        out.setdefault(n.table, {})[n.original] = n.name
    return out


class NamedSource:
    """A table source whose unnamed columns carry the names a person confirmed. Renaming twice changes nothing."""

    def __init__(self, source: TableSource, names: Iterable[ColumnName]) -> None:
        self._source = source
        self._renames = renames_by_table(names)
        self.name = source.name

    def table_names(self) -> list[str]:
        return self._source.table_names()

    def read(self, table: str) -> pd.DataFrame:
        frame = self._source.read(table)
        renames = self._renames.get(table)
        return frame.rename(columns=renames) if renames else frame


class NamingError(ValueError):
    """A requested name breaks a rule (renames a named column, clashes, bad characters)."""


def check_names(columns: list[str], names: list[ColumnName]) -> None:
    """`columns` are the table's headers as read. Only unnamed ones may be renamed; names are unique in the table."""
    seen: set[str] = set()
    renamed = {n.original for n in names}
    for n in names:
        if n.original not in columns:
            raise NamingError(f"no column {n.original!r} in {n.table}")
        if not is_unnamed(n.original):
            raise NamingError(f"{n.table}.{n.original} already has a name; only unnamed columns can be renamed")
        if not NAME.match(n.name):
            raise NamingError(f"{n.name!r}: use lower-case letters, digits and '_', starting with a letter")
        if is_unnamed(n.name):
            raise NamingError(f"{n.name!r} is not a descriptive name; say what the column holds")
        if n.name in seen:
            raise NamingError(f"two columns of {n.table} would be called {n.name!r}")
        if n.name in columns and n.name not in renamed:
            raise NamingError(f"{n.table} already has a column called {n.name!r}")
        seen.add(n.name)


def snake(text: str) -> str:
    s = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(text)).lower()
    s = re.sub(r"[^a-z0-9]+", "_", s).strip("_")
    if s and not s[0].isalpha():
        s = f"col_{s}"
    return s[:63]


# ---------------------------------------------------------------- suggestions
@dataclass
class Suggestion:
    column: str
    name: str = ""  # empty: no suggestion, the person types one
    meaning: str = ""
    source: str = "none"  # rules | ai | none
    confidence: float = 0.0
    samples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "column": self.column, "name": self.name, "meaning": self.meaning, "source": self.source,
            "confidence": round(self.confidence, 2), "samples": self.samples,
        }  # fmt: skip


@dataclass(frozen=True)
class ColumnSummary:
    """What the AI may see of one column: a profile and a few short values, never the column itself."""

    column: str
    position: int
    before: str | None  # the nearest column names on each side (only real names)
    after: str | None
    profile: dict[str, Any]
    samples: list[str]
    shapes: list[str]

    def as_prompt(self) -> dict[str, Any]:
        p = self.profile
        out = {
            "column": self.column, "position": self.position, "filled": round(1 - p.get("empty", 0.0), 2),
            "unique_share": p.get("unique_ratio", 0.0), "average_length": p.get("avg_len", 0.0),
            "shapes": self.shapes, "examples": self.samples,
        }  # fmt: skip
        if self.before:
            out["column_before"] = self.before
        if self.after:
            out["column_after"] = self.after
        return out


def _shape(value: str) -> str:
    s = re.sub(r"[A-Za-zÅÄÖåäö]", "A", value)
    s = re.sub(r"\d", "9", s)
    return re.sub(r"(.)\1{3,}", r"\1\1\1+", s)[:SAMPLE_CHARS]


def _cut(value: str) -> str:
    return value if len(value) <= SAMPLE_CHARS else value[: SAMPLE_CHARS - 1] + "…"


def summarise(frame: pd.DataFrame, column: str, seed: int = 0) -> ColumnSummary:
    cols = list(frame.columns)
    i = cols.index(column)
    named = [c for c in cols if not is_unnamed(c)]
    before = next((c for c in reversed(cols[:i]) if c in named), None)
    after = next((c for c in cols[i + 1 :] if c in named), None)
    values = frame[column] if len(frame) <= PROFILE_ROWS else frame[column].sample(PROFILE_ROWS, random_state=seed)
    values = values.astype(str).str.strip()
    filled = values[(values != "") & (values.str.lower() != "nan")]
    distinct = filled.drop_duplicates()
    picked = distinct.sample(min(SAMPLES, len(distinct)), random_state=seed) if len(distinct) else distinct
    shapes = filled.map(_shape).value_counts().head(3).index.tolist() if len(filled) else []
    return ColumnSummary(column, i + 1, before, after, checks.profile(values), [_cut(v) for v in picked], shapes)


def rule_name(summary: ColumnSummary) -> tuple[str, str, float] | None:
    """A name from a strict format check that passes on nearly every value, or None."""
    passes = summary.profile.get("pass", {})
    best = max(RULE_NAMES, key=lambda k: passes.get(k, 0.0))
    share = float(passes.get(best, 0.0))
    if share < STRONG:
        return None
    name, meaning = RULE_NAMES[best]
    return name, meaning, share


def _hint(summary: ColumnSummary) -> str:
    """The strongest format the rules saw, as a hint for the AI (it may still disagree)."""
    passes = {k: v for k, v in summary.profile.get("pass", {}).items() if v >= 0.5}
    return ", ".join(f"{k} {v:.0%}" for k, v in sorted(passes.items(), key=lambda kv: -kv[1])[:3])


SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "columns": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "name": {"type": "string"},
                    "meaning": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["column", "name", "meaning", "confidence"],
            },
        }
    },
    "required": ["columns"],
}


def prompt_for(table: str, named: list[str], batch: list[ColumnSummary], avoid: Mapping[str, list[str]]) -> str:
    items = []
    for s in batch:
        item = s.as_prompt()
        if hint := _hint(s):
            item["format_checks"] = hint
        if avoid.get(s.column):
            item["not_these_names"] = avoid[s.column]
        items.append(item)
    return (
        "You name the columns of a data table that have no real header. For each column below, give a short "
        "snake_case column name (lower case, words joined by _, at most 4 words) that says what the values are, a "
        "one-sentence meaning, and your confidence from 0 to 1. Base it on the examples, their shapes and the "
        "neighbouring column names. Values may be Finnish or Swedish. Do not reuse an existing column name and do "
        "not give two columns the same name. If a column is unclear, give your best guess with low confidence.\n"
        f"Table: {table}\n"
        f"Existing column names: {json.dumps(named[:40], ensure_ascii=False)}\n"
        f"Columns to name: {json.dumps(items, ensure_ascii=False)}\n"
        'Reply as JSON: {"columns": [{"column": ..., "name": ..., "meaning": ..., "confidence": ...}]}'
    )


def _batches(table: str, named: list[str], todo: list[ColumnSummary], avoid: Mapping[str, list[str]]) -> list[str]:
    """Prompts of at most BATCH columns and about PROMPT_TOKENS tokens each (4 characters per token)."""
    out: list[str] = []
    pending = [todo[i : i + BATCH] for i in range(0, len(todo), BATCH)]
    while pending:
        batch = pending.pop(0)
        text = prompt_for(table, named, batch, avoid)
        if len(text) / 4 > PROMPT_TOKENS and len(batch) > 1:
            half = len(batch) // 2
            pending[:0] = [batch[:half], batch[half:]]
        else:
            out.append(text)
    return out


@dataclass
class SuggestResult:
    suggestions: list[Suggestion]
    ai_calls: int = 0
    ai_error: str | None = None
    model: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "suggestions": [s.as_dict() for s in self.suggestions], "ai_calls": self.ai_calls,
            "ai_error": self.ai_error, "model": self.model,
        }  # fmt: skip


def suggest(
    frame: pd.DataFrame,
    table: str,
    columns: list[str],
    llm: LlmClient,
    avoid: Mapping[str, list[str]] | None = None,
) -> SuggestResult:
    """Names for unnamed `columns` of `frame`: rules first, then the local AI for the rest (when it is on)."""
    avoid = avoid or {}
    named = [c for c in frame.columns if not is_unnamed(c)]
    out: dict[str, Suggestion] = {}
    todo: list[ColumnSummary] = []
    for col in columns:
        if col not in frame.columns or not is_unnamed(col):
            raise NamingError(f"{table}.{col} is not an unnamed column")
        s = summarise(frame, col)
        out[col] = Suggestion(col, samples=s.samples)
        if not s.samples:
            out[col].name, out[col].meaning, out[col].source, out[col].confidence = (
                snake(f"empty_{col}"), "Empty in every row", "rules", 1.0,
            )  # fmt: skip
        elif (rule := rule_name(s)) and rule[0] not in avoid.get(col, []):
            out[col].name, out[col].meaning, out[col].confidence = rule
            out[col].source = "rules"
        else:
            todo.append(s)
    result = SuggestResult(list(out.values()), model=llm.model)
    if todo:
        _ask(llm, _batches(table, named, todo, avoid), out, result)
    _make_unique(out, set(named))
    return result


def _ask(llm: LlmClient, prompts: list[str], out: dict[str, Suggestion], result: SuggestResult) -> None:
    if not llm.available:
        result.ai_error = "the local AI is off (set PETS_LLM_ENABLED=true); type the names yourself"
        return
    for text in prompts:
        try:
            answer = llm.ask_json(text, SCHEMA)
            result.ai_calls += 1
        except LlmUnavailableError as exc:
            result.ai_error = f"the local AI did not answer ({exc}); type the remaining names yourself"
            continue
        for item in answer.get("columns", []) if isinstance(answer, dict) else []:
            col = str(item.get("column", ""))
            name = snake(item.get("name", ""))
            if col in out and out[col].source == "none" and name and not is_unnamed(name):
                out[col].name, out[col].source = name, "ai"
                out[col].meaning = str(item.get("meaning", ""))[:200]
                try:
                    out[col].confidence = min(1.0, max(0.0, float(item.get("confidence", 0.0))))
                except (TypeError, ValueError):
                    out[col].confidence = 0.0


def _make_unique(out: dict[str, Suggestion], taken: set[str]) -> None:
    """Two suggestions with the same name (two phone columns) become phone, phone_2."""
    for s in out.values():
        if not s.name:
            continue
        base, n = s.name, 2
        while s.name in taken:
            s.name = f"{base}_{n}"[:63]
            n += 1
        taken.add(s.name)
