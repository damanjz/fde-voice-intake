"""Strict yes/no reading of a spoken answer to a pending action (returns, tickets).

A wrong "yes" starts a return, so this is deliberately narrow: the WHOLE utterance must be made of yes
words (or of no words). A yes word followed by anything else, such as a negation, a delay, a laugh or a
goodbye ("Yeah, no", "Ji nahi", "Okay, bye", "Do it later", "Ha ha", "Yes please don't"), is not an answer:
the caller asks the customer to say yes or no again. Pure code, no models.
"""

from __future__ import annotations

import re
from typing import Literal

Answer = Literal["yes", "no"]

MAX_WORDS = 8

_YES_ANCHORS = {
    "yes", "yeah", "yep", "yup", "sure", "haan", "han", "ji", "confirm", "confirmed", "ok", "okay",
    "absolutely", "definitely", "correct",
}
_YES_FILLER = {
    "please", "go", "ahead", "do", "it", "thanks", "thank", "you", "kindly", "that", "right", "is", "of", "course",
    "bana", "dijiye", "kar", "karo", "kijiye", "theek", "hai", "the", "return", "ticket", "start", "open", "i",
}
_NO_ANCHORS = {"no", "nope", "nah", "nahi", "nahin", "cancel", "cancelled", "stop", "nevermind"}
_NO_FILLER = {
    "please", "thanks", "thank", "you", "it", "that", "this", "them", "keep", "i", "will", "ill", "want", "to", "the",
    "return", "ticket", "request", "dont", "do", "not", "never", "mind", "karo", "mat", "hai", "need", "wont",
}
_NEGATORS = {"dont", "not", "never", "wont", "mat"}
_YES_FORM = re.compile(r"^(?:ye+s+|ye+a+h?|ye+p+|yu+p+)$")
_PHRASES_YES = {"go ahead", "please go ahead", "go ahead please", "do it", "please do", "please do it"}


def _tokens(text: str) -> list[str]:
    out = []
    for w in re.findall(r"[a-z]+(?:'[a-z]+)?", text.lower()):
        w = w.replace("'", "")
        out.append("yes" if _YES_FORM.match(w) else w)
    return " ".join(out).replace("never mind", "nevermind").split()


def classify(text: str) -> Answer | None:
    """'yes' only for a whole-utterance yes, 'no' only for a clear whole-utterance no, else None."""
    toks = _tokens(text)
    if not toks or len(toks) > MAX_WORDS:
        return None
    if " ".join(toks) in _PHRASES_YES:
        return "yes"
    if all(t in _YES_ANCHORS or t in _YES_FILLER for t in toks) and any(t in _YES_ANCHORS for t in toks):
        return "yes"
    if all(t in _NO_ANCHORS or t in _NO_FILLER for t in toks) and any(t in _NO_ANCHORS for t in toks):
        if any(t in _NEGATORS for t in toks) and any(t in {"cancel", "cancelled", "stop"} for t in toks):
            return None  # "don't cancel it": a negated no
        return "no"
    return None
