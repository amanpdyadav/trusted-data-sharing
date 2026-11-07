"""Typed identifiers inside free text. A regex proposes a candidate; the shared format check confirms it (DRY)."""

import re
from dataclasses import dataclass

from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.detect.base import Validator
from pets_transformer.detect.validators import VALIDATORS
from pets_transformer.text.spoken import cue_for, cue_label

L = SpanLabel
RELABEL = frozenset({L.PAYMENT_CARD, L.ACCOUNT_NUMBER})  # long numbers: the words before say what they are


@dataclass(frozen=True)
class TextPattern:
    label: SpanLabel
    regex: re.Pattern[str]
    check: str | None = None  # name of a registered validator that must accept the match
    group: int = 0  # the regex group that is the value (the rest is context, e.g. "ending in")
    cue_overrides: bool = False  # a matching cue before it ("hetu ...") is enough even if the check fails

    def validator(self) -> Validator | None:
        return VALIDATORS.get(self.check) if self.check else None


_STREET = (
    r"(?:katu|tie|kuja|polku|rinne|puistikko|kaari|mäki|väylä|ranta|tori|aukio|piha|kangas|niitty|"
    r"gatan|gata|vägen|väg|stigen|road|street|st)"
)

_CARD_END = (
    r"(?:päättyy|päättyvä|loppuu|slutar på|slutar med|ending in|ends in|ending|last four digits are|"
    r"neljä viimeistä numeroa ovat|loppunumerot)\s"
)
_POSTCODE = r"(?:, ?\d{5} [A-ZÅÄÖ][a-zåäö]+)"

PATTERNS: tuple[TextPattern, ...] = (
    TextPattern(L.URL, re.compile(r"https?://\S+[^\s.,;:!?)\]]")),
    TextPattern(L.EMAIL, re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), "email"),
    TextPattern(L.IBAN, re.compile(r"\b[A-Z]{2}\d{2}(?: ?[A-Z0-9]{4}){2,7}(?: ?[A-Z0-9]{1,4})?\b", re.I), "iban"),
    TextPattern(
        L.NATIONAL_ID, re.compile(r"\b\d{6} ?[-+A-FU-Y] ?\d{3}[0-9A-Y]\b", re.I), "fi_hetu", cue_overrides=True
    ),
    TextPattern(L.PAYMENT_CARD, re.compile(r"\b(?:\d[ -]?){12,18}\d\b"), "payment_card"),
    TextPattern(L.PAYMENT_CARD, re.compile(r"(?:\b\d{4,6}|[*xX]{4})[ *xX]{4,}\d{4}\b")),
    TextPattern(L.PAYMENT_CARD, re.compile(rf"{_CARD_END}(\d{{4}})\b", re.I), group=1),  # "card ending in 4242"
    TextPattern(L.IP_ADDRESS, re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b"), "ipv4"),
    TextPattern(L.PHONE, re.compile(r"(?<![\w+])(?:\+358|00358|0)[ -]*\d(?:[ -]{0,2}\d){5,10}(?!\w)"), "phone"),
    TextPattern(L.LICENSE_PLATE, re.compile(r"\b[A-ZÅÄÖ]{2,3}-\d{1,3}\b", re.I)),
    TextPattern(L.PROPERTY_ID, re.compile(r"\b\d{1,3}-\d{1,3}-\d{1,4}-\d{1,4}\b")),
    TextPattern(L.DEVICE_ID, re.compile(r"\b[A-Z]{2,4}-[A-ZÅÄÖ]{3,10}-\d{2,6}\b")),  # host names, LT-JESKUL-8415
    TextPattern(L.ACCOUNT_NUMBER, re.compile(r"\b[A-Z]{2,4}-\d{5,}\b")),  # contract and order numbers, AT-4590407
    TextPattern(
        L.ADDRESS,
        re.compile(rf"\b[A-ZÅÄÖ][a-zåäö]+{_STREET} \d{{1,4}}(?: ?[A-Z])?(?: \d{{1,3}})?{_POSTCODE}?\b", re.I),
    ),
    TextPattern(L.ACCOUNT_NUMBER, re.compile(r"(?<![\w.,:/-])\d(?: ?\d){6,15}(?![\w/-]|[.,:]\d)")),  # long bare numbers
)


@dataclass(frozen=True)
class PatternDetector:
    """Implements SpanDetector for typed formats."""

    name: str = "patterns"

    def find(self, text: str) -> list[Span]:
        spans: list[Span] = []
        for p in PATTERNS:
            v = p.validator()
            for m in p.regex.finditer(text):
                value, start, end = m.group(p.group), m.start(p.group), m.end(p.group)
                if v is not None and not v.is_valid(value) and not _cued(p, text, start):
                    continue
                label = cue_label(text, start, p.label) if p.label in RELABEL else p.label
                spans.append(Span(start=start, end=end, label=label, text=value, source=self.name))
        return spans


def _cued(p: TextPattern, text: str, start: int) -> bool:
    """Typos and test data break check digits; the words before still say what the value is."""
    return p.cue_overrides and cue_for(text, start) is p.label
