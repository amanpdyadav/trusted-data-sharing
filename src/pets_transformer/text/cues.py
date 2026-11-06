"""Values announced by cue words: "salasana on Kesä2024", "username ainov85", "this is tarmo", "jag heter Saga".

Names after a cue are taken when they are known name words or capitalised, so "kiitos paljon" stays untouched.
"""

import re
from dataclasses import dataclass, field

from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.text.known import KnownNames

L = SpanLabel
_LINK = r"(?:\s*(?:on|is|är|:|=)\s*|\s+)"

SECRET_CUE = re.compile(
    rf"(?:salasana(?:ni)?|password|lösenord(?:et)?|tunnusluku|pin(?:-koodi)?|puk(?:-koodi)?){_LINK}", re.I
)
USERNAME_CUE = re.compile(
    rf"(?:käyttäjätunnu(?:s|kseni)|käyttäjänimi|username|user name|användarnamn(?:et)?){_LINK}", re.I
)
_VALUE = re.compile(r"[^\s,;]+")

NAME_CUE = re.compile(
    r"\b(?:nimeni on|minun nimeni on|nimi on|olen|tässä on|tässä|täällä on|puhelimessa|nimellä|kiitos|hei|moi|terve|"
    r"jag heter|mitt namn är|det är|här är|tack|hej|"
    r"my name is|this is|i'm|i am|thanks|thank you|hello|hi|dear|"
    r"dr\.?|tohtori|lääkäri|hoitaja|naapuri|naapurini|tytär|tyttäreni|tyttärelleni|poika|poikani|pojalleni|äiti|äitini|"
    r"isä|isäni|vaimo|vaimoni|mieheni|puoliso|puolisoni|veli|veljeni|sisko|siskoni|omainen|asiakas|potilas|"
    r"dotter|son|mamma|pappa|fru|make|granne|customer|patient|neighbour|daughter|wife|husband|mother|father)\s+",
    re.I,
)
_NAME_WORD = re.compile(r"[A-Za-zÅÄÖåäöÜüÉé'\-]{2,}")
MAX_NAME_WORDS = 3


def _value_span(text: str, cue: re.Match[str], label: SpanLabel, source: str) -> Span | None:
    m = _VALUE.match(text, cue.end())
    if not m:
        return None
    value = m.group(0).rstrip(".!?)")
    if len(value) < 2:
        return None
    return Span(start=m.start(), end=m.start() + len(value), label=label, text=value, source=source)


@dataclass(frozen=True)
class SecretCueDetector:
    """Implements SpanDetector: the value right after a password, PIN or username cue."""

    name: str = "secret_cues"

    def find(self, text: str) -> list[Span]:
        spans = []
        for cue, label in ((SECRET_CUE, L.SECRET), (USERNAME_CUE, L.USERNAME)):
            for m in cue.finditer(text):
                if (s := _value_span(text, m, label, self.name)) is not None:
                    spans.append(s)
        return spans


@dataclass(frozen=True)
class CueNameDetector:
    """Implements SpanDetector: up to three name words after a cue, if known names or capitalised."""

    known: KnownNames = field(default_factory=lambda: KnownNames(frozenset()))
    name: str = "cue_names"

    def find(self, text: str) -> list[Span]:
        spans = []
        for cue in NAME_CUE.finditer(text):
            pos, words = cue.end(), list[re.Match[str]]()
            while len(words) < MAX_NAME_WORDS and (m := _NAME_WORD.match(text, pos)):
                word = m.group(0)
                if not (word in self.known or (word[0].isupper() and len(word) > 2)):
                    break
                words.append(m)
                pos = m.end() + 1 if text[m.end() : m.end() + 1] == " " else len(text) + 1
            if words:
                s, e = words[0].start(), words[-1].end()
                spans.append(Span(start=s, end=e, label=L.PERSON, text=text[s:e], source=self.name))
        return spans
