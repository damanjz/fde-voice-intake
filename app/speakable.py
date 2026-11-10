"""Make agent reply text speakable: no citations or markdown, ids read letter by letter, rupees, short lists."""

from __future__ import annotations

import re

MAX_LIST_ITEMS = 3
MAX_SENTENCES = 6

_DIGIT_NAMES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
_MONTHS = [
    "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December",
]
_DAYS = {
    "mon": "Monday", "tue": "Tuesday", "tues": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
    "thur": "Thursday", "thurs": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday",
}
_DAY_RE = "|".join(sorted(_DAYS, key=len, reverse=True))
_ABBREV = {"IST": "I S T", "SKU": "S K U", "FAQ": "F A Q", "FAQs": "F A Qs", "OTP": "O T P", "UPI": "U P I",
           "COD": "C O D", "PIN": "pin"}

_CITE_BRACKET = re.compile(r"\s*[\[(]\s*(?:source[s]?:?\s*)?KB-\d+(?:\s*[,;&]\s*(?:and\s+)?KB-\d+)*\s*[\])]")
_CITE_BARE = re.compile(r"\bKB-\d+\b")
_LIST_LINE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.*\S)\s*$")
_MONEY_PREFIX = re.compile(r"(?:\b(?:INR|Rs)\.?|₹)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_MONEY_SUFFIX = re.compile(r"\b([\d,]+(?:\.\d+)?)\s*(?:INR|rupees)\b", re.IGNORECASE)
_ID_CODE = re.compile(r"\b([A-Z]{1,4})-(\d{2,6})\b")
_ALNUM_CODE = re.compile(r"\b([A-Z]{1,4})(\d{5,})\b")
_PHONE = re.compile(r"(?<![\w.])\+?\d[\d \-]{8,}\d(?![\w])")
_EMAIL = re.compile(r"\b([\w.+-]+)@([\w-]+(?:\.[\w-]+)+)\b")
_URL = re.compile(r"https?://\S+")
_ISO_DATE = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_TIME_RANGE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(?:-|–|to)\s*(\d{1,2}):(\d{2})\b")
_TIME = re.compile(r"\b(\d{1,2}):(\d{2})\b")
_DAY_RANGE = re.compile(rf"\b({_DAY_RE})\.?\s*(?:-|–|to)\s*({_DAY_RE})\b", re.IGNORECASE)


def spell(value: str) -> str:
    """'LC1150' -> 'L C one one five zero' (letters and digits read one by one)."""
    out = []
    for ch in value:
        if ch.isdigit():
            out.append(_DIGIT_NAMES[int(ch)])
        elif ch.isalpha():
            out.append(ch.upper())
    return " ".join(out)


def _money(m: re.Match) -> str:
    amount = m.group(1).replace(",", "")
    whole, _, frac = amount.partition(".")
    frac = frac.ljust(2, "0")[:2]
    text = f"{whole or '0'} rupees" if whole != "1" else "1 rupee"
    if frac != "00":
        text += f" {int(frac)} paise"
    return text


def _clock(h: int, mi: int) -> str:
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {suffix}" if mi == 0 else f"{h12} {mi:02d} {suffix}"


def _iso_date(m: re.Match) -> str:
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 1 <= mo <= 12:
        return m.group(0)
    return f"{d} {_MONTHS[mo - 1]} {y}"


def _compress_lists(text: str) -> str:
    """Bullet lines become one sentence; past MAX_LIST_ITEMS the rest is left for the screen."""
    out: list[str] = []
    items: list[str] = []

    def flush() -> None:
        if not items:
            return
        shown = [i.rstrip(".;, ") for i in items[:MAX_LIST_ITEMS]]
        sentence = "; ".join(shown) + "."
        if len(items) > MAX_LIST_ITEMS:
            more = len(items) - MAX_LIST_ITEMS
            sentence += f" And {more} more, which you can see on screen."
        out.append(sentence)
        items.clear()

    for line in text.splitlines():
        m = _LIST_LINE.match(line)
        if m:
            items.append(m.group(1))
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def _cap_sentences(text: str) -> str:
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if len(sentences) <= MAX_SENTENCES:
        return text
    tail = next((s for s in reversed(sentences) if re.search(r"confirm|cancel", s, re.IGNORECASE)), None)
    head = sentences[: MAX_SENTENCES - 1 if tail else MAX_SENTENCES]
    head.append("The rest is on your screen.")
    if tail and tail not in head:
        head.append(tail)
    return " ".join(head)


def make_speakable(text: str, cap: bool = True) -> str:
    t = text
    t = _CITE_BRACKET.sub("", t)
    t = _CITE_BARE.sub("the help article", t)
    t = re.sub(r"```.*?```", " ", t, flags=re.DOTALL)
    t = re.sub(r"\[([^\]]+)\]\((?:[^)]+)\)", r"\1", t)  # [text](url)
    t = _URL.sub("the link on screen", t)
    t = re.sub(r"^\s{0,3}#{1,6}\s*", "", t, flags=re.MULTILINE)
    t = re.sub(r"(\*\*|__|\*|`)", "", t)
    t = _compress_lists(t)
    t = _EMAIL.sub(lambda m: f"{m.group(1)} at {m.group(2).replace('.', ' dot ')}", t)
    t = _ISO_DATE.sub(_iso_date, t)
    t = _TIME_RANGE.sub(lambda m: f"{_clock(int(m[1]), int(m[2]))} to {_clock(int(m[3]), int(m[4]))}", t)
    t = _TIME.sub(lambda m: _clock(int(m[1]), int(m[2])), t)
    t = _DAY_RANGE.sub(lambda m: f"{_DAYS[m[1].lower()]} to {_DAYS[m[2].lower()]}", t)
    t = _MONEY_PREFIX.sub(_money, t)
    t = _MONEY_SUFFIX.sub(_money, t)
    t = re.sub(r"\bINR\b", "rupees", t)
    t = _PHONE.sub(lambda m: spell(re.sub(r"\D", "", m.group(0))), t)
    t = _ID_CODE.sub(lambda m: spell(m.group(1) + m.group(2)), t)
    t = _ALNUM_CODE.sub(lambda m: spell(m.group(1) + m.group(2)), t)
    for abbr, spoken in _ABBREV.items():
        t = re.sub(rf"\b{abbr}\b", spoken, t)
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)
    t = re.sub(r"(\d)\s*%", r"\1 percent", t)
    t = re.sub(r"\be\.g\.", "for example", t, flags=re.IGNORECASE)
    t = re.sub(r"\bi\.e\.", "that is", t, flags=re.IGNORECASE)
    t = t.replace("&", " and ").replace("~", "about ")
    t = re.sub(r"[ \t]*\n+[ \t]*", ". ", t)
    t = re.sub(r"\.\s*\.", ".", t)
    t = re.sub(r"([:;,])\s*\.", ".", t)
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return _cap_sentences(t) if cap else t


PENDING_SUFFIX = "Say yes or no, or press Confirm or Cancel."
_REFUND_RE = re.compile(r"refund[^.\d]{0,40}(?:INR|Rs\.?|₹)\s*([\d,]+(?:\.\d+)?)", re.IGNORECASE)


def _sku_words(skus: object) -> str:
    if isinstance(skus, dict):
        return ", ".join(f"{n} of {k}" for k, n in skus.items())
    if isinstance(skus, (list, tuple)):
        return ", ".join(str(x) for x in skus)
    return str(skus or "")


def speak_pending(pending: dict, reply_text: str) -> str:
    """Spoken form of an action waiting for yes or no, built from pending_action itself (never cut short).

    The reply text is only used for the refund estimate, which is not part of the structured action. Anything
    unrecognised falls back to the full reply text, uncapped, with the yes/no instruction added.
    """
    args = pending.get("args") or {}
    tool = pending.get("tool")
    if tool == "start_return":
        parts = [f"I can start a return for order {args.get('order_id')}"]
        items = _sku_words(args.get("skus"))
        if items:
            parts.append(f"items {items}")
        if args.get("reason"):
            parts.append(f"reason: {str(args['reason']).strip().rstrip('.')}")
        m = _REFUND_RE.search(reply_text or "")
        if m:
            parts.append(f"estimated refund INR {m.group(1)}")
        sentence = ", ".join(parts) + "."
    elif tool == "create_ticket":
        sentence = (f"I can open a {args.get('priority', 'normal')} priority support ticket: "
                    f"{str(args.get('summary', '')).strip().rstrip('.')}.")
    else:
        return make_speakable(f"{reply_text} {PENDING_SUFFIX}", cap=False)
    return make_speakable(f"{sentence} {PENDING_SUFFIX}", cap=False)
