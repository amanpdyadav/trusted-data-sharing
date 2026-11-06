"""Interfaces for the text step. Detectors find spans; one redactor applies them (separation of concerns)."""

from collections.abc import Sequence
from typing import Protocol

from pets_transformer.contracts import Span
from pets_transformer.registry import Registry


class SpanDetector(Protocol):
    """Finds personal data in one text: rules, a name finder (NER) or the local AI all fit this shape.

    A detector that needs the local AI must catch `LlmUnavailableError` and return [] so text redaction
    still works on rules alone.
    """

    @property
    def name(self) -> str: ...

    def find(self, text: str) -> list[Span]: ...


SPAN_DETECTORS: Registry[str, SpanDetector] = Registry("span detector")


def merge_spans(spans: Sequence[Span]) -> list[Span]:
    """Sort by position and drop spans fully covered by an earlier, longer one (labels never overlap)."""
    out: list[Span] = []
    for s in sorted(spans, key=lambda s: (s.start, -(s.end - s.start))):
        if out and s.end <= out[-1].end:
            continue
        out.append(s)
    return out


def redact(text: str, spans: Sequence[Span]) -> str:
    """Replace each span with a typed tag like [PHONE]; keeps the rest of the sentence for meaning."""
    parts: list[str] = []
    cursor = 0
    for s in merge_spans(spans):
        start = max(s.start, cursor)
        parts.append(text[cursor:start])
        parts.append(f"[{s.label.value}]")
        cursor = max(cursor, s.end)
    parts.append(text[cursor:])
    return "".join(parts)
