"""Names the organisation already holds (customers, patients, staff) found again inside free text.

Built from the release's own person-name columns, so it works the same on company data. Lowercase
speech-to-text output is matched too. To avoid tagging ordinary words that are also names ("Mäki" = hill),
a single name word must be capitalised; lowercase single names are left to the cue detector.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.text.base import words

_WORD = re.compile(r"[A-Za-zÅÄÖåäöÜüÉéÆæØø'\-]+")
_NAME_TOKEN = re.compile(r"^[A-ZÅÄÖÜÉ][A-Za-zÅÄÖåäöÜüÉé'\-]{2,}$")
MIN_NAME_LEN = 3
# Capitalised words that are not people even if someone carries them as a name
NOT_PEOPLE = words(
    "maanantai tiistai keskiviikko torstai perjantai lauantai sunnuntai",
    "tammikuu helmikuu maaliskuu huhtikuu toukokuu kesäkuu heinäkuu elokuu syyskuu lokakuu marraskuu joulukuu",
    "monday tuesday wednesday thursday friday saturday sunday",
    "january february march april may june july august september october november december",
    "måndag tisdag onsdag torsdag fredag lördag söndag",
    "hei moi kiitos hello thanks hej tack dear dr tohtori asiakas potilas customer patient",
)


@dataclass(frozen=True)
class KnownNames:
    tokens: frozenset[str]  # lowercased name words, e.g. {"riitta", "lipponen", "emilia"}

    @classmethod
    def from_values(cls, names: Iterable[str]) -> "KnownNames":
        words = {
            w.lower()
            for n in names
            for w in str(n).split()
            if _NAME_TOKEN.match(w.capitalize()) and len(w) >= MIN_NAME_LEN
        }
        return cls(frozenset(words - NOT_PEOPLE))

    def __contains__(self, word: object) -> bool:
        return isinstance(word, str) and word.lower() in self.tokens


@dataclass(frozen=True)
class KnownNameDetector:
    """Implements SpanDetector: runs of known name words; a single word only when capitalised."""

    known: KnownNames
    name: str = "known_names"

    def find(self, text: str) -> list[Span]:
        spans: list[Span] = []
        run: list[re.Match[str]] = []

        def close() -> None:
            if run and (len(run) >= 2 or run[0].group(0)[0].isupper()):
                s, e = run[0].start(), run[-1].end()
                spans.append(Span(start=s, end=e, label=SpanLabel.PERSON, text=text[s:e], source=self.name))
            run.clear()

        prev_end = -1
        for m in _WORD.finditer(text):
            gap = text[prev_end : m.start()] if prev_end >= 0 else ""
            if m.group(0) in self.known:
                if run and gap.strip():  # punctuation between words ends a name
                    close()
                run.append(m)
            else:
                close()
            prev_end = m.end()
        close()
        return spans
