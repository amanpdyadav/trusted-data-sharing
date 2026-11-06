"""Free-text redaction: find PII spans and replace them with typed placeholders like [PERSON].

Owner: Free text. Span labels and rules are in metadata/pii_span_guidelines.md.
Text is Finnish, English and Swedish, including speech-recognition output with spoken numbers.
Scored with `pets-eval text` (F2: recall matters more than precision).
"""


def find_spans(text: str) -> list[dict]:
    """Return [{"start": int, "end": int, "label": str}, ...], non-overlapping."""
    raise NotImplementedError("Free text: rules + LLM span finder")


def redact(text: str, spans: list[dict]) -> str:
    """Replace each span with [LABEL], working from the end so offsets stay valid."""
    for s in sorted(spans, key=lambda s: s["start"], reverse=True):
        text = text[:s["start"]] + f"[{s['label']}]" + text[s["end"]:]
    return text
