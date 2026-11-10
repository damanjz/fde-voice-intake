"""The 30 synthetic clips: what is spoken, the typed equivalent, and the label (order id, tool).

`spoken` is what piper reads aloud and the WER reference. `typed` is what a customer would type, sent to the
agent as the typed baseline. `expected_tool` is one of lookup_order, check_stock, start_return, create_ticket,
or None (no tool needed). kind: query | yes | no | hardneg | silent | noise | nonspeech. hardneg clips are
spoken answers that must NOT be taken as yes or no; silent, noise and nonspeech clips must produce no agent call.
"""

from __future__ import annotations

# (id, spoken, typed, expected_order_id, expected_tool, length_scale, snr_db, group)
_Q = [
    ("S01", "Where is my order L C one one five zero?", "Where is my order LC-1150?", "LC-1150", "lookup_order", 1.0, None, "confusable"),
    ("S02", "Where is my order L C one zero one five?", "Where is my order LC-1015?", "LC-1015", "lookup_order", 1.0, None, "confusable"),
    ("S03", "Can you check el see eleven fifty for me please", "Can you check LC-1150 for me please", "LC-1150", "lookup_order", 1.15, None, "confusable"),
    ("S04", "What is the status of L C ten fifty", "What is the status of LC-1050", "LC-1050", "lookup_order", 0.9, None, "confusable"),
    ("S05", "Has el see eleven fifteen been shipped yet?", "Has LC-1115 been shipped yet?", "LC-1115", "lookup_order", 1.0, None, "confusable"),
    ("S06", "I placed order L C ten fifteen last week and nothing has come", "I placed order LC-1015 last week and nothing has come", "LC-1015", "lookup_order", 1.0, None, "confusable"),
    ("S07", "Please track L C double one six seven", "Please track LC-1167", "LC-1167", "lookup_order", 0.85, None, "order"),
    ("S08", "Order el see ten oh one, when will it be delivered?", "Order LC-1001, when will it be delivered?", "LC-1001", "lookup_order", 1.1, None, "order"),
    ("S09", "My order number is L C one thousand one hundred twenty five", "My order number is LC-1125", "LC-1125", "lookup_order", 1.0, None, "order"),
    ("S10", "L C twelve hundred, where is the parcel?", "LC-1200, where is the parcel?", "LC-1200", "lookup_order", 1.3, None, "order"),
    ("S11", "Please look up el see one one zero seven", "Please look up LC-1107", "LC-1107", "lookup_order", 1.0, 15, "noisy"),
    ("S12", "Is order L C eleven oh nine delivered?", "Is order LC-1109 delivered?", "LC-1109", "lookup_order", 1.0, 10, "noisy"),
    ("S13", "Order L C one one eight eight has not arrived", "Order LC-1188 has not arrived", "LC-1188", "lookup_order", 1.25, 20, "noisy"),
    ("S14", "I want to return the kettle from order L C eleven thirty seven, it stopped heating", "I want to return the kettle from order LC-1137, it stopped heating", "LC-1137", "start_return", 1.0, None, "return"),
    ("S15", "The coffee beans from order el see eleven fifty five arrived damaged, I want to return them", "The coffee beans from order LC-1155 arrived damaged, I want to return them", "LC-1155", "start_return", 1.0, 15, "return"),
    ("S16", "Please start a return for order L C eleven sixty one, the moka pot is leaking", "Please start a return for order LC-1161, the moka pot is leaking", "LC-1161", "start_return", 1.0, None, "return"),
    ("S37", "I want to return the grinder from order L C eleven fifty four, I changed my mind", "I want to return the grinder from order LC-1154, I changed my mind", "LC-1154", "start_return", 1.0, None, "return"),
    ("S17", "Do you have the Larkfield Hand Burr Grinder Pro in stock?", "Do you have the Larkfield Hand Burr Grinder Pro in stock?", None, "check_stock", 1.0, None, "stock"),
    ("S18", "Is the Espresso Grinder sixty four millimetre available?", "Is the Espresso Grinder 64mm available?", None, "check_stock", 0.9, None, "stock"),
    ("S19", "How long does shipping take to Hyderabad?", "How long does shipping take to Hyderabad?", None, None, 1.0, None, "answer"),
    ("S20", "What is your return policy for coffee beans?", "What is your return policy for coffee beans?", None, None, 1.0, 10, "answer"),
    ("S21", "How long is the warranty on the electric burr grinder?", "How long is the warranty on the electric burr grinder?", None, None, 1.2, None, "answer"),
    ("S22", "How do I cancel my coffee subscription?", "How do I cancel my coffee subscription?", None, None, 1.0, None, "answer"),
    ("S23", "I am very unhappy and I want to speak to a person", "I am very unhappy and I want to speak to a person", None, "create_ticket", 1.0, None, "ticket"),
    ("S24", "Please raise a ticket, my invoice has the wrong address", "Please raise a ticket, my invoice has the wrong address", None, "create_ticket", 1.0, None, "ticket"),
]

# yes/no answers to a pending action
_YN = [
    ("S25", "yes", "Yes, please go ahead.", 1.0, None),
    ("S26", "yes", "Yeah sure, do it.", 1.1, 15),
    ("S27", "no", "No, cancel that.", 1.0, None),
    ("S28", "no", "No thanks, I will keep it.", 0.9, 15),
]


# a yes or no word followed by a negation, delay, laugh or goodbye: never a clear answer
_HARDNEG = [
    ("S31", "Yeah, no.", 1.0),
    ("S32", "Okay, bye.", 1.0),
    ("S33", "Yes please, don't.", 1.0),
]
# non-speech sounds that a voice-activity filter may let through (generated in make_clips.py)
_NONSPEECH = [("S34", "laughter"), ("S35", "babble"), ("S36", "keyboard")]

# Text-only hard negatives for the yes/no readers (no audio): (phrase, what a careful reader must do)
HARD_NEGATIVE_PHRASES = [
    "Yeah, no", "Ji nahi", "Haan nahi", "Okay, bye", "Ha ha", "Do it later", "Yes, no, wait", "Yeah, cancel it",
    "Yes please don't", "Yes but", "Ok so what is the fee?", "Yes tomorrow", "Don't cancel it",
]


# Return clips must match project 1's order data (data/orders.json): delivered within the 30-day window, holding
# the item the clip names, no open return. Run 1 of the end-to-end eval used clips that did not match
# (a kettle from an order holding coffee beans, a grinder from an order that was not delivered, beans from an
# order with no beans) and project 1 correctly refused them. Orders now used: LC-1137 (Variable Temperature
# Kettle Pro, delivered 2026-10-24), LC-1154 (Electric Burr Grinder Precision, 2026-10-31), LC-1155 (Ethiopia
# Yirgacheffe 250g, 2026-10-31), LC-1161 (Moka Pot 3-Cup, 2026-10-30). None appears in project 1's own evals.
_NOTE_FIXED = "(orchestrator 2026-11-10, after e2e run 1: clip did not match P1 order data)"
_NOTE_ADDED = "(orchestrator 2026-11-10, after e2e run 1: added so the unclear scenario has its own matching order)"
_NOTES = {"S14": _NOTE_FIXED, "S15": _NOTE_FIXED, "S16": _NOTE_FIXED, "S37": _NOTE_ADDED}


def build() -> list[dict]:
    clips: list[dict] = []
    for cid, spoken, typed, oid, tool, rate, snr, group in _Q:
        clips.append({
            "id": cid, "kind": "query", "group": group, "spoken": spoken, "typed": typed,
            "expected_order_id": oid, "expected_tool": tool, "length_scale": rate, "snr_db": snr,
        })
    for cid, polarity, spoken, rate, snr in _YN:
        clips.append({
            "id": cid, "kind": polarity, "group": "answer_to_pending", "spoken": spoken, "typed": spoken,
            "expected_order_id": None, "expected_tool": None, "length_scale": rate, "snr_db": snr,
        })
    for cid, spoken, rate in _HARDNEG:
        clips.append({
            "id": cid, "kind": "hardneg", "group": "answer_to_pending", "spoken": spoken, "typed": spoken,
            "expected_order_id": None, "expected_tool": None, "length_scale": rate, "snr_db": None,
        })
    clips.append({"id": "S29", "kind": "silent", "group": "silent", "spoken": "", "typed": "",
                  "expected_order_id": None, "expected_tool": None, "length_scale": 1.0, "snr_db": None})
    clips.append({"id": "S30", "kind": "noise", "group": "silent", "spoken": "", "typed": "",
                  "expected_order_id": None, "expected_tool": None, "length_scale": 1.0, "snr_db": None})
    for cid, sound in _NONSPEECH:
        clips.append({"id": cid, "kind": "nonspeech", "group": sound, "spoken": "", "typed": "",
                      "expected_order_id": None, "expected_tool": None, "length_scale": 1.0, "snr_db": None})
    for c in clips:
        if c["id"] in _NOTES:
            c["note"] = _NOTES[c["id"]]
        c["file"] = f"{c['id']}.wav"
        c["source"] = "synthetic"
    return clips
