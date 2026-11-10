"""Stand-in for the project 1 /chat API, for demos and page tests when project 1 (and its GPU) is not running.

    python scripts/fake_agent.py           # serves on http://localhost:8099
    AGENT_URL=http://localhost:8099 python -m uvicorn app.main:app --port 8200

Same request and response shape as project 1 (session_id, message, confirm -> text, citations, tool_calls,
pending_action, escalated, usage) and the same rule: the pending action lives on the server, per session.
It answers from canned rules, not a model. Not used by the evals.
"""

from __future__ import annotations

import re

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Stand-in support agent")
_pending: dict[str, dict] = {}
_ORDER = re.compile(r"\bLC-(\d{4})\b")


class Chat(BaseModel):
    session_id: str
    message: str
    confirm: bool | None = None


def reply(text: str, **kw) -> dict:
    return {"text": text, "citations": kw.get("citations", []), "tool_calls": kw.get("tool_calls", []),
            "pending_action": kw.get("pending_action"), "escalated": kw.get("escalated", False), "usage": {}}


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "stand_in": True}


@app.post("/chat")
def chat(req: Chat) -> dict:
    msg = req.message.strip()
    pending = _pending.get(req.session_id)
    answer = req.confirm
    if pending and answer is None:
        if re.match(r"(?i)^\W*(yes|yeah|yep|sure|haan|confirm|go ahead|do it)\b", msg):
            answer = True
        elif re.match(r"(?i)^\W*(no|nope|nahi|cancel|never ?mind)\b", msg):
            answer = False
    if pending and answer is not None:
        _pending.pop(req.session_id)
        if answer:
            call = {"name": pending["tool"], "args": pending["args"], "result": {"ok": True, "ref": "R-9001"}}
            return reply("Done. Your return is booked and the pickup will be scheduled within 2 business days.", tool_calls=[call])
        return reply("Okay, I've cancelled that request; nothing was changed.")
    order = _ORDER.search(msg)
    if order and re.search(r"(?i)return|send back|damaged", msg):
        action = {"tool": "start_return", "args": {"order_id": order.group(0), "skus": ["GR-007"], "reason": msg[:80]}}
        _pending[req.session_id] = action
        return reply(f"I can start a return for order {order.group(0)}. The refund estimate is INR 1,900 after the INR 99 "
                     "pickup fee. Please confirm to go ahead, or cancel.", pending_action=action)
    if order:
        call = {"name": "lookup_order", "args": {"order_id": order.group(0)}, "result": {"status": "shipped"}}
        return reply(f"Order {order.group(0)} shipped on 2026-11-02 via BlueDart and arrives by 6 November. [KB-003]",
                     citations=["KB-003"], tool_calls=[call])
    if re.search(r"(?i)person|human|unhappy", msg):
        return reply("I'm sorry about that. A person will call you back within one business day.", escalated=True)
    return reply("Standard shipping takes 3 to 5 business days. Support hours are 9:00-19:00 IST, Mon-Sat. [KB-001]",
                 citations=["KB-001"])


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="warning")
