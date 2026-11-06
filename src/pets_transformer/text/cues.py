"""Values announced by cue words: "salasana on Kesä2024", "username ainov85", "this is tarmo", "jag heter Saga".

Names after a cue are taken when they are known name words or capitalised, so "kiitos paljon" stays untouched.
"""

import re
from dataclasses import dataclass, field

from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.text.known import KnownNames

L = SpanLabel
# hesitation and hedge words people put between a cue and its value: "salasana on varmaan X", "det alltså är Johan"
_FILLER = r"(?:(?:niinku|tota|siis|nyt|varmaan|ehkä|öö|ää|liksom|alltså|typ|kanske|erm|um|uh|like|probably|there)\s+)*"
_LINK = rf"(?=[\s:=])\s*{_FILLER}(?:(?:on|is|was|är|var|:|=)\s*)?{_FILLER}"

SECRET_CUE = re.compile(
    rf"\b(?:salasana(?:ni|ksi|n)?|password|lösenord(?:et)?|tunnusluku|pin(?:-koodi)?|puk(?:-koodi)?){_LINK}", re.I
)
USERNAME_CUE = re.compile(
    rf"\b(?:käyttäjätunnu(?:s|kseni)|tunnus|käyttäjä(?:lle|n)?|käyttäjänimi|username|user name|"
    rf"användarnamn(?:et)?|användare){_LINK}",
    re.I,
)
_VALUE = re.compile(r"[^\s,;]+")
_USERNAME = re.compile(r"[\w.\-]*[\d.][\w.\-]*")  # a login has a digit or a dot: ainov85, susanna.jarvinen
_SECRET = re.compile(r".*[\d\W_].*|.+[A-ZÅÄÖ].*")  # not a plain word: "salasana on med ..." is no password

_CUE_END = rf"[,:]?\s+{_FILLER}"
# the speaker names someone: a capitalised word after these is a name
NAME_CUE = re.compile(
    r"\b(?:nimeni on|minun nimeni on|nimi on|nimellä|täällä puhuu|terveisin|t\.|kollegalle|yhteyshenkilö|esihenkilö|"
    r"jag heter|mitt namn är|hälsningar|kontaktperson|my name is|regards|contact person|"
    r"dr\.?|tohtori|lääkäri|hoitaja|naapuri|naapurini|tytär|tyttäreni|tyttärelleni|poika|poikani|pojalleni|äiti|äitini|"
    r"isä|isäni|vaimo|vaimoni|mieheni|puoliso|puolisoni|veli|veljeni|sisko|siskoni|omainen|asiakas|potilas|"
    rf"dotter|son|mamma|pappa|fru|make|granne|customer|patient|neighbour|daughter|wife|husband|mother|father){_CUE_END}",
    re.I,
)
# greetings and introductions are often followed by an ordinary sentence ("Kiitos Aallokolle"), so a new capitalised
# word counts only when it stands alone ("Kiitos Matti," / "Hei Liisa!"); known names always count
WEAK_NAME_CUE = re.compile(
    r"\b(?:olen|tässä on|tässä|täällä on|kiitos|hei|moi|terve|asiakaspalvelu|"
    rf"det(?:\s+{_FILLER})?\s*är|här är|tack|hej|kundtjänst|"
    rf"this is|i'm|i am|thanks|thank you|hello|hi|dear|customer service){_CUE_END}",
    re.I,
)
_ALONE = re.compile(r"\s*(?:[,.!?;:]|$)")
# the name comes first: "asiakaspalvelu joel puhelimessa", "Johan here"
NAME_BEFORE_CUE = re.compile(r"\b([A-Za-zÅÄÖåäö]{3,})\s+(?:puhelimessa|täällä|speaking|here|här)\b")
# a signature closing a note: "... Ei jatkotoimia. /KLAI", "... soitonsiirron? -Ville"
SIGNATURE = re.compile(r"(?:^|\s)[/\-\u2013]\s?([A-ZÅÄÖ][A-ZÅÄÖa-zåäö]{1,15})\s*$")
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
                s = _value_span(text, m, label, self.name)
                shape = _USERNAME if label is L.USERNAME else _SECRET
                if s is not None and shape.fullmatch(s.text):
                    spans.append(s)
        return spans


@dataclass(frozen=True)
class CueNameDetector:
    """Implements SpanDetector: up to three name words after a cue, if known names or capitalised."""

    known: KnownNames = field(default_factory=lambda: KnownNames(frozenset()))
    name: str = "cue_names"

    def find(self, text: str) -> list[Span]:
        spans = []
        for weak, cues in ((False, NAME_CUE), (True, WEAK_NAME_CUE)):
            for cue in cues.finditer(text):
                if (span := self._name_after(text, cue.end(), weak)) is not None:
                    spans.append(span)
        for before in NAME_BEFORE_CUE.finditer(text):
            if before.group(1) in self.known:
                spans.append(self._span(text, before.start(1), before.end(1)))
        if sign := SIGNATURE.search(text):
            spans.append(self._span(text, sign.start(1), sign.end(1)))
        return spans

    def _name_after(self, text: str, pos: int, weak: bool) -> Span | None:
        words: list[re.Match[str]] = []
        while len(words) < MAX_NAME_WORDS and (m := _NAME_WORD.match(text, pos)):
            word = m.group(0)
            if not (word in self.known or (word[0].isupper() and len(word) > 2 and "'" not in word)):
                break
            words.append(m)
            pos = m.end() + 1 if text[m.end() : m.end() + 1] == " " else len(text) + 1
        if not words:
            return None
        start, end = words[0].start(), words[-1].end()
        if weak and not all(w.group(0) in self.known for w in words) and not _ALONE.match(text, end):
            return None
        return self._span(text, start, end)

    def _span(self, text: str, start: int, end: int) -> Span:
        return Span(start=start, end=end, label=L.PERSON, text=text[start:end], source=self.name)
