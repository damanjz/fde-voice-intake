"""Word error rate, implemented here (no jiwer): word-level Levenshtein over normalised text."""

from __future__ import annotations

import re

from app.normalize import normalize_order_ids

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
         "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]


def number_to_words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    if n < 1000:
        rest = n % 100
        return _ONES[n // 100] + " hundred" + ("" if rest == 0 else " " + number_to_words(rest))
    if n < 1_000_000:
        rest = n % 1000
        return number_to_words(n // 1000) + " thousand" + ("" if rest == 0 else " " + number_to_words(rest))
    return " ".join(_ONES[int(c)] for c in str(n))


def wer_tokens(text: str, normalise_ids: bool) -> list[str]:
    """Lower-case, no punctuation, digits spoken out. With normalise_ids, an order id is one token."""
    if normalise_ids:
        text = re.sub(r"LC-(\d{4})", r"lcid\1", normalize_order_ids(text).text)
    text = text.lower().replace("-", " ")
    text = text.replace("'", "")
    text = re.sub(r"(?<=\d),(?=\d)", "", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\b(\d+)\b", lambda m: number_to_words(int(m.group(1))), text)
    return text.split()


def edit_distance(ref: list[str], hyp: list[str]) -> int:
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        cur = [i]
        for j, h in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = cur
    return prev[-1]


def wer(reference: str, hypothesis: str, normalise_ids: bool = False) -> float:
    """Edits / reference words. Empty reference: 0.0 if the hypothesis is empty too, else 1.0."""
    ref = wer_tokens(reference, normalise_ids)
    hyp = wer_tokens(hypothesis, normalise_ids)
    if not ref:
        return 0.0 if not hyp else 1.0
    return edit_distance(ref, hyp) / len(ref)


def corpus_wer(pairs: list[tuple[str, str]], normalise_ids: bool = False) -> float:
    """Total edits over total reference words (not the mean of per-clip rates)."""
    edits = words = 0
    for ref, hyp in pairs:
        r, h = wer_tokens(ref, normalise_ids), wer_tokens(hyp, normalise_ids)
        edits += edit_distance(r, h)
        words += len(r)
    return edits / words if words else 0.0
