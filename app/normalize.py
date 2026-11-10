"""Spoken-form normalisation for transcripts.

Turns the ways people actually say Larkfield order ids ("el see eleven fifty", "L C one one five zero",
"L.C. 1150", "double one five zero", "LC ek ek paanch zero") into "LC-1150", and drops filler sounds that
carry no meaning. Pure code, no models.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------- vocabulary

_DIGIT_WORDS = {
    "zero": 0, "nought": 0, "naught": 0, "shunya": 0, "sifar": 0,
    "one": 1, "ek": 1,
    "two": 2,
    "three": 3, "teen": 3,
    "four": 4, "char": 4, "chaar": 4,
    "five": 5, "paanch": 5, "panch": 5,
    "six": 6, "chhe": 6, "chhah": 6, "chheh": 6,
    "seven": 7, "saat": 7,
    "eight": 8, "aath": 8,
    "nine": 9, "nau": 9,
}
# Words that are also ordinary words: only read as digits between other digits.
_AMBIGUOUS = {"to": 2, "too": 2, "tu": 2, "do": 2, "for": 4, "fore": 4, "ate": 8, "won": 1}
_TEENS = {
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "dus": 10, "gyarah": 11, "gyaarah": 11, "barah": 12, "terah": 13, "chaudah": 14, "pandrah": 15,
    "solah": 16, "satrah": 17, "atharah": 18, "unnis": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50, "sixty": 60, "seventy": 70,
    "eighty": 80, "ninety": 90,
    "bees": 20, "tees": 30, "chalis": 40, "pachas": 50, "pachaas": 50, "saath": 60, "sattar": 70,
    "assi": 80, "nabbe": 90,
}
_HUNDRED = {"hundred", "sau", "sao"}
_THOUSAND = {"thousand", "hazaar", "hazar"}
_MULT = {"double": 2, "dabal": 2, "dubble": 2, "triple": 3, "tripple": 3}

# Spoken or mis-heard forms of the order-id prefix "LC" (word sequences, punctuation ignored).
_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("lc",), ("l", "c"), ("el", "c"), ("el", "see"), ("el", "sea"), ("el", "si"), ("el", "cee"),
    ("ell", "see"), ("ell", "c"), ("l", "see"), ("l", "sea"), ("l", "si"), ("l", "cee"),
    ("al", "see"), ("elsie",), ("elsey",), ("elsy",), ("elcy",), ("elc",), ("elsee",), ("elcee",),
    ("ellsie",),
)
_PREFIX_MAX = max(len(p) for p in _PREFIXES)
_AFTER_PREFIX = {"number", "no", "id", "is", "dash", "hyphen", "hash", "pound", "num"}
_ORDER_FILLERS = {"number", "no", "id", "is", "hash", "dash", "num"}
_SEPS = {",", "-", ".", ":", "/", "–", "—", "#", "_"}
# A bare four-digit number after "order" is not an order id when it is a quantity.
_QUANTITY_WORDS = {
    "g", "gm", "gms", "gram", "grams", "kg", "kgs", "ml", "rupees", "rs", "inr", "bags", "bag", "pieces",
    "units", "items", "cups", "packs", "pack", "rupee", "dollars", "percent",
}

_FILLER_RE = re.compile(
    r"\b(?:u+m+|u+h+|u+hm+|e+r+m?|h+m+|m{2,}|a+h+|arre+|arrey|arey|yaar|matlab)\b[,.]?\s*",
    re.IGNORECASE,
)

_TOKEN_RE = re.compile(r"[^\W\d_]+|\d+(?:[.,:]\d+)*|\S")


@dataclass(frozen=True)
class _Tok:
    kind: str  # "word" | "num" | "punct"
    text: str  # lower-cased for words
    start: int
    end: int


@dataclass(frozen=True)
class OrderIdMatch:
    start: int
    end: int
    raw: str
    digits: str

    @property
    def order_id(self) -> str:
        return f"LC-{self.digits}"

    @property
    def valid(self) -> bool:
        return len(self.digits) == 4


@dataclass
class Normalized:
    text: str
    order_ids: list[str] = field(default_factory=list)  # well-formed LC-dddd
    suspect_ids: list[str] = field(default_factory=list)  # an id was heard but not 4 digits


def _tokenize(text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    for m in _TOKEN_RE.finditer(text):
        s = m.group()
        if s[0].isdigit():
            toks.append(_Tok("num", s, m.start(), m.end()))
        elif s[0].isalpha():
            toks.append(_Tok("word", s.lower(), m.start(), m.end()))
        else:
            toks.append(_Tok("punct", s, m.start(), m.end()))
    return toks


def _num_digits(s: str) -> str:
    return "".join(str(unicodedata.digit(c)) for c in s if c.isdigit())


# ---------------------------------------------------------------- digit reading

def _word_digit(tok: _Tok | None) -> int | None:
    """A single digit 0-9 from a digit word or a one-digit number, else None."""
    if tok is None:
        return None
    if tok.kind == "num":
        d = _num_digits(tok.text)
        return int(d) if len(d) == 1 else None
    if tok.kind == "word" and tok.text in _DIGIT_WORDS:
        return _DIGIT_WORDS[tok.text]
    if tok.kind == "word" and tok.text == "oh":
        return 0
    return None


def _is_number_like(tok: _Tok | None) -> bool:
    if tok is None:
        return False
    if tok.kind == "num":
        return True
    if tok.kind != "word":
        return False
    w = tok.text
    return (
        w in _DIGIT_WORDS or w in _TEENS or w in _TENS or w in _HUNDRED or w in _THOUSAND
        or w in _MULT or w == "oh"
    )


def _next_number_like(toks: list[_Tok], k: int) -> bool:
    """Is the next token (skipping separators) a number?"""
    n = len(toks)
    while k < n and toks[k].kind == "punct" and toks[k].text in _SEPS:
        k += 1
    return k < n and (_is_number_like(toks[k]) or toks[k].text in _AMBIGUOUS)


def _cardinal_run_has_big(toks: list[_Tok], k: int) -> bool:
    n = len(toks)
    j = k
    while j < n and j < k + 12:
        if toks[j].kind == "punct" and toks[j].text in {",", "-"}:
            j += 1
            continue
        if toks[j].kind != "word":
            return False
        w = toks[j].text
        if w in _HUNDRED or w in _THOUSAND:
            return True
        if not (w in _DIGIT_WORDS or w in _TEENS or w in _TENS or w == "and"):
            return False
        j += 1
    return False


def _read_cardinal(toks: list[_Tok], k: int) -> tuple[str, int] | None:
    """Standard English cardinal ("eleven hundred fifty", "one thousand and fifty") -> (digits, next)."""
    n = len(toks)
    total = cur = 0
    last = "start"
    used_thousand = False
    j = k
    while j < n:
        if toks[j].kind == "punct":
            # "twenty-five", "one thousand, one hundred": a joiner inside one cardinal
            joiner = (toks[j].text == "-" and last == "tens") or (
                toks[j].text == "," and last in ("hundred", "thousand")
            )
            if joiner and j + 1 < n and toks[j + 1].kind == "word" and _is_number_like(toks[j + 1]):
                j += 1
                continue
            break
        if toks[j].kind != "word":
            break
        w = toks[j].text
        if w in _DIGIT_WORDS and _DIGIT_WORDS[w] > 0:
            if last in ("digit", "teen", "tens_unit"):
                break
            cur += _DIGIT_WORDS[w]
            last = "tens_unit" if last == "tens" else "digit"
        elif w in _TEENS:
            if last in ("digit", "teen", "tens", "tens_unit"):
                break
            cur += _TEENS[w]
            last = "teen"
        elif w in _TENS:
            if last in ("digit", "teen", "tens", "tens_unit"):
                break
            cur += _TENS[w]
            last = "tens"
        elif w in _HUNDRED:
            if last == "hundred":
                break
            cur = (cur or 1) * 100
            last = "hundred"
        elif w in _THOUSAND:
            if used_thousand or last == "start":
                break
            total += (cur or 1) * 1000
            cur = 0
            used_thousand = True
            last = "thousand"
        elif w == "and" and last in ("hundred", "thousand") and j + 1 < n and _is_number_like(toks[j + 1]):
            pass
        else:
            break
        j += 1
    if j == k:
        return None
    return str(total + cur), j


def _read_unit(toks: list[_Tok], k: int, so_far: str) -> tuple[str, int] | None:
    """One spoken or written chunk of an id's digits starting at token k: (digits, next token index)."""
    n = len(toks)
    t = toks[k]
    if t.kind == "num":
        d = _num_digits(t.text)
        return (d, k + 1) if d else None
    if t.kind != "word":
        return None
    w = t.text
    if w in _MULT:
        nxt = toks[k + 1] if k + 1 < n else None
        d = _word_digit(nxt)
        if d is None:
            return None
        return str(d) * _MULT[w], k + 2
    if _cardinal_run_has_big(toks, k):
        card = _read_cardinal(toks, k)
        if card:
            return card
    if w in _DIGIT_WORDS:
        return str(_DIGIT_WORDS[w]), k + 1
    if w == "oh":
        return ("0", k + 1) if so_far else None
    if w in _TEENS:
        return str(_TEENS[w]), k + 1
    if w in _TENS:
        m = k + 1
        if m + 1 < n and toks[m].kind == "punct" and toks[m].text == "-":
            m += 1  # "forty-two"
        nxt = toks[m] if m < n else None
        if nxt is not None and nxt.kind == "word" and _DIGIT_WORDS.get(nxt.text, 0) > 0:
            return str(_TENS[w] + _DIGIT_WORDS[nxt.text]), m + 1
        return str(_TENS[w]), k + 1
    if w in _AMBIGUOUS and so_far and _next_number_like(toks, k + 1):
        # "to", "too", "for", "do" are digits only BETWEEN digits, never as the last one: "LC 115 to arrive"
        # must not become LC-1152.
        return str(_AMBIGUOUS[w]), k + 1
    return None


def _read_digits(toks: list[_Tok], i: int) -> tuple[str, int]:
    """Collect up to four id digits from token i. Returns (digits, index after the last used token)."""
    n = len(toks)
    digits = ""
    j = end = i
    while j < n and len(digits) < 4:
        k = j
        while digits and k < n and toks[k].kind == "punct" and toks[k].text in _SEPS:
            k += 1
        if k >= n:
            break
        unit = _read_unit(toks, k, digits)
        if unit is None:
            break
        s, nxt = unit
        if digits and len(digits) + len(s) > 4:
            break
        digits += s
        j = end = nxt
    return digits, end


# ---------------------------------------------------------------- order ids

_NAME_LIKE = {("elsie",), ("elsey",), ("elsy",), ("elcy",), ("elc",), ("elsee",), ("elcee",), ("ellsie",)}


def _match_prefix(toks: list[_Tok], i: int) -> tuple[int, tuple[str, ...]] | None:
    """If an LC prefix starts at token i, return (index after it, the words matched)."""
    n = len(toks)
    if toks[i].kind != "word":
        return None
    for size in range(_PREFIX_MAX, 0, -1):
        words: list[str] = []
        j = i
        while j < n and len(words) < size:
            if toks[j].kind == "word":
                words.append(toks[j].text)
            elif not (toks[j].kind == "punct" and toks[j].text in {".", "-", "_"} and words):
                break
            j += 1
        if len(words) == size and tuple(words) in _PREFIXES:
            return j, tuple(words)
    return None


def _skip_after_prefix(toks: list[_Tok], j: int, fillers: set[str]) -> int:
    n = len(toks)
    while j < n and (
        (toks[j].kind == "punct" and toks[j].text in _SEPS) or (toks[j].kind == "word" and toks[j].text in fillers)
    ):
        j += 1
    return j


_WEAK_PREFIX = {"c", "l", "el", "ell"}
_ORDER_BRIDGE = {"id", "ids", "number", "no", "num", "is", "numbered", "the", "my"}


def _order_nearby(toks: list[_Tok], i: int) -> bool:
    """Is token i right after "order" (allowing "ids", "number", "is", "no" in between)?"""
    for t in reversed(toks[max(0, i - 5):i]):
        if t.kind == "punct":
            continue
        if t.text in {"order", "orders"}:
            return True
        if t.text not in _ORDER_BRIDGE:
            return False
    return False


def _extend_digits(toks: list[_Tok], digits: str, end: int) -> tuple[str, int]:
    """A spoken or typed 5th digit directly after four ("LC one one five zero five") makes the id longer, so it
    is reported as a suspect id instead of silently dropping the extra digit. Only digits that follow with no
    punctuation between count, and "oh", "to", "for" and similar never extend."""
    n = len(toks)
    while len(digits) >= 4 and end < n and len(digits) < 8:
        unit = _read_unit(toks, end, "")
        if unit is None or unit[0] == "":
            break
        digits += unit[0]
        end = unit[1]
    return digits, end


def find_order_ids(text: str, expect_order_id: bool = False) -> list[OrderIdMatch]:
    toks = _tokenize(text)
    n = len(toks)
    found: list[OrderIdMatch] = []
    i = 0
    while i < n:
        matched = _match_prefix(toks, i)
        if matched is not None:
            nxt, words = matched
            if words in _NAME_LIKE:
                # "Elsie" is a first name: only an id when the digits come right after it
                j = nxt
                if not (j < n and (toks[j].kind == "num" or _is_number_like(toks[j]))):
                    i += 1
                    continue
            else:
                j = _skip_after_prefix(toks, nxt, _AFTER_PREFIX)
            digits, end = _read_digits(toks, j)
            digits, end = _extend_digits(toks, digits, end)
            if digits:
                found.append(OrderIdMatch(toks[i].start, toks[end - 1].end, text[toks[i].start:toks[end - 1].end], digits))
                i = end
                continue
        elif toks[i].kind == "word" and toks[i].text == "order":
            j = _skip_after_prefix(toks, i + 1, _ORDER_FILLERS)
            digits, end = _read_digits(toks, j)
            after = toks[end].text if end < n else ""
            if len(digits) == 4 and after not in _QUANTITY_WORDS and end > j:
                found.append(OrderIdMatch(toks[j].start, toks[end - 1].end, text[toks[j].start:toks[end - 1].end], digits))
                i = end
                continue
        elif toks[i].kind == "word" and toks[i].text in _WEAK_PREFIX and _order_nearby(toks, i):
            # "my order ids C-1151": the L was swallowed. Accepted only close after the word "order" and
            # only when exactly four digits follow, so it cannot fire on ordinary sentences.
            j = _skip_after_prefix(toks, i + 1, set())
            digits, end = _read_digits(toks, j)
            if len(digits) == 4 and (toks[end].text if end < n else "") not in _QUANTITY_WORDS:
                found.append(OrderIdMatch(toks[i].start, toks[end - 1].end, text[toks[i].start:toks[end - 1].end], digits))
                i = end
                continue
        i += 1
    if not found and expect_order_id:
        found = _bare_answer(text, toks)
    return found


def _bare_answer(text: str, toks: list[_Tok]) -> list[OrderIdMatch]:
    """The whole utterance is just an id ("double one five zero", "eleven fifty"): the answer to "what is
    your order id?". Only accepted when it is exactly four digits."""
    words = [i for i, t in enumerate(toks) if t.kind != "punct"]
    if not words or not _is_number_like(toks[words[0]]):
        return []
    digits, end = _read_digits(toks, words[0])
    if len(digits) != 4 or any(i >= end for i in words):
        return []
    return [OrderIdMatch(toks[words[0]].start, toks[end - 1].end, text[toks[words[0]].start:toks[end - 1].end], digits)]


def normalize_order_ids(text: str, expect_order_id: bool = False) -> Normalized:
    """Rewrite every spoken or garbled order id in the text as LC-dddd.

    expect_order_id: the agent's last reply asked for an order id. Only then is an utterance that is just four
    digits ("eleven fifty") read as an id; otherwise it is left alone.
    """
    matches = find_order_ids(text, expect_order_id)
    out = text
    for m in reversed(matches):
        out = out[: m.start] + m.order_id + out[m.end :]
    return Normalized(
        text=out,
        order_ids=[m.order_id for m in matches if m.valid],
        suspect_ids=[m.order_id for m in matches if not m.valid],
    )


# ---------------------------------------------------------------- fillers

def strip_fillers(text: str) -> str:
    """Drop sounds with no meaning (um, uh, hmm, arre, yaar, matlab). Yes/no words are never touched."""
    cleaned = _FILLER_RE.sub("", text)
    if cleaned == text:
        return text.strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.!?])", r"\1", cleaned)
    cleaned = re.sub(r"^[\s,.\-]+", "", cleaned).strip()
    if cleaned and text[:1].isupper():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def prepare_transcript(raw: str, expect_order_id: bool = False) -> Normalized:
    """Everything done to a raw transcript before it goes to the agent."""
    return normalize_order_ids(strip_fillers(raw), expect_order_id)
