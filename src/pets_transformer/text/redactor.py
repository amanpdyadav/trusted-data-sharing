"""The redactor: runs every span detector, keeps the labels asked for, replaces them with typed tags.

Stateless detectors are registered in SPAN_DETECTORS (plug-ins can add more); detectors that need the
organisation's known names are built per release from its own person-name columns.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.text.base import SPAN_DETECTORS, SpanDetector, merge_spans, redact
from pets_transformer.text.cues import CueNameDetector, SecretCueDetector
from pets_transformer.text.known import KnownNameDetector, KnownNames
from pets_transformer.text.patterns import PatternDetector
from pets_transformer.text.spoken import SpelledEmailDetector, SpokenNumberDetector

L = SpanLabel
# Labels that identify a person or unlock an account. Context (dates, places, organisations, health) is kept by
# default: it carries the meaning analysts need. A plan can ask for more labels.
IDENTIFYING = frozenset({
    L.PERSON, L.NATIONAL_ID, L.EMAIL, L.PHONE, L.ADDRESS, L.IBAN, L.PAYMENT_CARD, L.ACCOUNT_NUMBER,
    L.IP_ADDRESS, L.LICENSE_PLATE, L.USERNAME, L.SECRET, L.DEVICE_ID, L.PROPERTY_ID, L.URL,
})  # fmt: skip

for _d in (PatternDetector(), SpokenNumberDetector(), SpelledEmailDetector(), SecretCueDetector()):
    SPAN_DETECTORS.register(_d.name, _d)


@dataclass(frozen=True)
class Redactor:
    detectors: Sequence[SpanDetector]
    labels: frozenset[SpanLabel] = IDENTIFYING

    def spans(self, text: str) -> list[Span]:
        if not text:
            return []
        found = [s for d in self.detectors for s in d.find(text) if s.label in self.labels]
        return merge_spans(found)

    def redact(self, text: str) -> str:
        return redact(text, self.spans(text))


def build_redactor(known_names: Iterable[str] = (), labels: Iterable[SpanLabel] | None = None) -> Redactor:
    """All registered detectors, plus name detectors that know the release's own names."""
    known = KnownNames.from_values(known_names)
    detectors: list[SpanDetector] = [*SPAN_DETECTORS, KnownNameDetector(known), CueNameDetector(known)]
    return Redactor(detectors, frozenset(labels) if labels is not None else IDENTIFYING)
