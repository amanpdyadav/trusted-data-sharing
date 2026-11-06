"""Numbers and e-mail addresses read aloud (speech-to-text) in Finnish, Swedish and English.

"nolla neljä viisi, neljä kahdeksan kaksi", "070889 streck 965 2", "nataliia dot boiko at mailbox dot example".
A run of digit words, digits and spoken separators is one span; the label comes from cue words just before it.
"""

import re
from dataclasses import dataclass

from pets_transformer.contracts import Span, SpanLabel
from pets_transformer.text.base import words

L = SpanLabel

DIGIT_WORDS = {
    # Finnish
    "nolla": "0", "yksi": "1", "kaksi": "2", "kolme": "3", "neljä": "4", "viisi": "5", "kuusi": "6",
    "seitsemän": "7", "kahdeksan": "8", "yhdeksän": "9",
    # Swedish
    "noll": "0", "ett": "1", "en": "1", "två": "2", "tre": "3", "fyra": "4", "fem": "5", "sex": "6",
    "sju": "7", "åtta": "8", "nio": "9",
    # English
    "zero": "0", "oh": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9",
}  # fmt: skip
SEPARATOR_WORDS = frozenset(("viiva", "väliviiva", "dash", "hyphen", "streck", "bindestreck", "plus", "plussa"))
# spelled letters that end a Finnish ID code: "pee", "aa", "ex" ... and single letters
LETTER_WORDS = words("aa bee see dee ee äf gee hoo ii jii koo äl äm än oo pee kuu är äs tee uu vee äks yy ex")
_TOKEN = re.compile(r"[\wåäöÅÄÖ]+|[,\-+]")
MIN_DIGITS = 4

CUES: tuple[tuple[SpanLabel, re.Pattern[str]], ...] = (  # checked in order: most specific first
    (L.NATIONAL_ID, re.compile(r"hetu|henkilötunnu|personbeteckning|personnummer|id code|identity code|"
                               r"personal id|social security", re.I)),
    (L.ACCOUNT_NUMBER, re.compile(r"asiakas\w*numer|kundnummer|customer (?:number|no)|sopimus|avtal|contract|"
                                  r"laskun? numero|fakturanummer|invoice|tilaus|order|viite|referens|reference", re.I)),
    (L.DEVICE_ID, re.compile(r"imei|sarjanumero|serienummer|serial|iccid|\bsim\b", re.I)),
    (L.SECRET, re.compile(r"\bpin\b|\bpuk\b|salasana|lösenord|password|passcode|tunnusluku", re.I)),
    (L.IBAN, re.compile(r"\biban\b|tilinumero|kontonummer|account number|bank account", re.I)),
    (L.PHONE, re.compile(r"puhelin|numero|nummer|number|soit|ring|call|phone|gsm|mobiili", re.I)),
)  # fmt: skip
CUE_WINDOW = 60


def cue_label(text: str, start: int, default: SpanLabel) -> SpanLabel:
    """The label named by cue words just before `start` ("hetu on ...", "imei ..."), else `default`."""
    before = text[max(0, start - CUE_WINDOW) : start]
    return next((label for label, cue in CUES if cue.search(before)), default)


def _label(text: str, start: int, digits: str) -> SpanLabel:
    default = L.PHONE if digits.startswith("0") and 9 <= len(digits) <= 11 else L.ACCOUNT_NUMBER
    return cue_label(text, start, default)


@dataclass(frozen=True)
class SpokenNumberDetector:
    """Implements SpanDetector: runs of spoken or typed digits, possibly ending in a spelled letter."""

    name: str = "spoken_numbers"

    def find(self, text: str) -> list[Span]:
        spans: list[Span] = []
        run: list[re.Match[str]] = []
        digits = ""
        spoken = False

        def close() -> None:
            nonlocal run, digits, spoken
            while run and not _is_digit_token(run[-1].group(0)) and run[-1].group(0).lower() not in LETTER_WORDS:
                run.pop()  # never end on a separator
            if run and spoken and len(digits) >= MIN_DIGITS:
                s, e = run[0].start(), run[-1].end()
                spans.append(Span(start=s, end=e, label=_label(text, s, digits), text=text[s:e], source=self.name))
            run, digits, spoken = [], "", False

        for m in _TOKEN.finditer(text):
            tok = m.group(0)
            low = tok.lower()
            if low in DIGIT_WORDS:
                run.append(m)
                digits += DIGIT_WORDS[low]
                spoken = True
            elif tok.isdigit():
                run.append(m)
                digits += tok
            elif run and (low in SEPARATOR_WORDS or tok in ",-+"):
                run.append(m)
                spoken = spoken or low in SEPARATOR_WORDS  # "140379 dash 910 6" is speech too
            elif run and low in LETTER_WORDS | set("abcdefhjklmnprstuvwxy") and len(digits) >= 6:
                run.append(m)  # the check letter of an ID code read aloud
                close()
            else:
                close()
        close()
        return spans


def _is_digit_token(tok: str) -> bool:
    return tok.isdigit() or tok.lower() in DIGIT_WORDS


# ---------------------------------------------------------------- e-mail spelled out
_AT = r"(?:at|ät|ätt|snabel-a|snabela|at-merkki|miukumauku)"
_DOT = r"(?:dot|piste|punkt|pist)"
_UNDERSCORE = r"(?:underscore|alaviiva|understreck)"
_PART = r"[a-zåäö0-9]+"
_SPELLED_EMAIL = re.compile(
    rf"\b{_PART}(?:\s+(?:{_DOT}|{_UNDERSCORE}|-)\s+{_PART}|\d+)*\s+{_AT}\s+{_PART}(?:\s+{_DOT}\s+{_PART})+\b", re.I
)


@dataclass(frozen=True)
class SpelledEmailDetector:
    """Implements SpanDetector: 'hilkka alaviiva aalto ät aurapost piste example'."""

    name: str = "spelled_email"

    def find(self, text: str) -> list[Span]:
        return [
            Span(start=m.start(), end=m.end(), label=L.EMAIL, text=m.group(0), source=self.name)
            for m in _SPELLED_EMAIL.finditer(text)
        ]
