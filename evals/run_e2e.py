"""End-to-end eval against the project 1 agent. Run by the orchestrator when the GPU is free.

    python -m evals.run_e2e                    # synthetic clips (P1 at AGENT_URL, default http://localhost:8000)
    python -m evals.run_e2e --own              # also the recorded own-voice clips
    python -m evals.run_e2e --limit 5          # first 5 query clips only
    python -m evals.run_e2e --no-confirm       # skip the voice scenarios (they write to P1's database)

What it does, per query clip, each in a fresh session:
  typed   the clip's typed text sent to P1 (the ceiling)
  voiced  the clip's audio through the whole pipeline (STT, normalisation, P1, speakable text, TTS)
Both are scored against the manifest label (tool name plus order id), not against each other: P1 is not
deterministic, so typed-vs-voiced agreement would mix STT errors with model noise. The gap is the cost of voice.
A create_ticket label counts only a real create_ticket call (proposed or run); a hand-off (escalated=true)
without one is counted separately.

Then, in this order:
  1. silent, noise-only and non-speech clips must produce no P1 call;
  2. voice-cancel: a voiced return request for LC-1137, a kettle that stopped heating (clip S14), then a voiced
     "no" (S27): nothing is written;
  3. voice-unclear: a voiced return request for LC-1154, a grinder, change of mind (clip S37), then a voiced
     "Yeah, no" (S31): not sent to P1, the action stays pending (the scenario then presses Cancel to clean up);
  4. voice-confirm: a voiced return request for LC-1161, a leaking moka pot (clip S16), then a voiced "yes"
     (S25): ONE RETURN IS CREATED in P1's database.

TEST DATA MUST MATCH P1's ORDER DATA. Run 1 failed on mismatched clips (a kettle from an order that held coffee
beans, a grinder from an order not yet delivered, beans from an order with no beans): P1 correctly refused them.
Return clips now use three different delivered orders, each inside the 30-day window and holding the item the
clip names: LC-1137 (cancel), LC-1154 (unclear), LC-1161 (confirm); the other return rows use LC-1155.

DATABASE PRECONDITION (recorded in e2e.json): P1's `returns` table holds no open return for LC-1137, LC-1154,
LC-1155 or LC-1161, and one extra return for LC-1161 is acceptable (the confirm creates it). The typed and
voiced rows only reach "pending", never execute, so they cannot collide with the scenarios. To run again,
delete the LC-1161 return or point CONFIRM_REQUEST at another matching delivered order. --no-confirm skips 2-4.

Takes about 15 s per P1 call: roughly 20 minutes in all. Writes evals/results/e2e.json (or --out).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

from app.agent_client import AgentClient, AgentUnavailable
from app.config import settings
from app.pipeline import VoicePipeline
from evals.common import RESULTS_DIR, clip_path, load_manifest

WRITE_TOOLS = {"start_return", "create_ticket"}
QUIET_KINDS = ("silent", "noise", "nonspeech")
CANCEL_REQUEST, UNCLEAR_REQUEST, CONFIRM_REQUEST = "S14", "S37", "S16"  # three different orders; only S16 is confirmed
YES_CLIP, NO_CLIP, UNCLEAR_CLIP = "S25", "S27", "S31"
PRECONDITION = (
    "Return clips match P1's order data (delivered within 30 days, item present): LC-1137 (voice-cancel, clip S14), "
    "LC-1154 (voice-unclear, clip S37), LC-1155 (clip S15, pending only), LC-1161 (voice-confirm, clip S16). "
    "P1's returns table has no open return for any of them. voice-confirm creates one return for LC-1161, so a second "
    "run needs that return removed or another matching order."
)


def calls_of(reply: dict) -> list[dict]:
    """Every tool the agent used or proposed in this reply: executed tool calls plus the pending action."""
    calls = [{"name": c.get("name"), "args": c.get("args") or {}} for c in reply.get("tool_calls") or []]
    pending = reply.get("pending_action")
    if pending:
        calls.append({"name": pending.get("tool"), "args": pending.get("args") or {}})
    return calls


def score_reply(clip: dict, reply: dict) -> dict:
    """Does the reply match the clip's label? Tool name plus order id; never compares typed with voiced."""
    calls = calls_of(reply)
    tool, order = clip.get("expected_tool"), clip.get("expected_order_id")
    seen_orders = {str(c["args"].get("order_id", "")).upper() for c in calls if c["args"].get("order_id")}
    wrong_order = bool(order and seen_orders - {order})
    ticket_call = any(c["name"] == "create_ticket" for c in calls)
    if tool is None:
        ok = not any(c["name"] in WRITE_TOOLS for c in calls)
    elif tool == "create_ticket":
        ok = ticket_call  # a hand-off with no ticket call does not count
    else:
        ok = any(
            c["name"] == tool and (order is None or str(c["args"].get("order_id", "")).upper() == order)
            for c in calls
        )
    escalated = bool(reply.get("escalated"))
    return {"ok": ok, "wrong_order": wrong_order, "tools": [c["name"] for c in calls],
            "order_ids": sorted(seen_orders), "pending": bool(reply.get("pending_action")),
            "escalated": escalated, "handoff_only": escalated and not ticket_call}


class CountingAgent(AgentClient):
    """AgentClient that counts /chat calls, so quiet and unclear clips can be shown to make none."""

    def __init__(self) -> None:
        super().__init__(settings)
        self.calls = 0

    def chat(self, session_id: str, message: str, confirm: bool | None = None) -> dict:
        self.calls += 1
        return super().chat(session_id, message, confirm)


def run_query(clip: dict, pipe: VoicePipeline, typed_agent: AgentClient) -> dict:
    row: dict = {"id": clip["id"], "source": clip.get("source", "synthetic"), "group": clip.get("group"),
                 "expected_tool": clip["expected_tool"], "expected_order_id": clip["expected_order_id"]}
    t0 = time.perf_counter()
    try:
        typed = typed_agent.chat(f"eval-typed-{clip['id']}-{int(t0)}", clip["typed"])
        row["typed"] = score_reply(clip, typed) | {"agent_ms": round((time.perf_counter() - t0) * 1000)}
    except AgentUnavailable as exc:
        row["typed"] = {"ok": False, "error": str(exc)}
    result = pipe.voice_turn(f"voice-eval-{clip['id']}-{int(t0)}", clip_path(clip).read_bytes())
    reply = {"tool_calls": result.tool_calls, "pending_action": result.pending_action, "escalated": result.escalated}
    row["voiced"] = score_reply(clip, reply) | {
        "status": result.status, "transcript": result.transcript, "timings": result.timings,
        "session_id": result.session_id, "text": result.reply_text[:300],
    }
    if result.status != "ok":
        row["voiced"]["ok"] = False
    return row


def run_quiet(clip: dict, pipe: VoicePipeline, counter) -> dict:
    before = counter.calls
    result = pipe.voice_turn(f"voice-eval-{clip['id']}", clip_path(clip).read_bytes())
    return {"id": clip["id"], "kind": clip["kind"], "status": result.status, "transcript_raw": result.transcript_raw,
            "agent_calls": counter.calls - before,
            "ok": result.status in ("no_speech", "low_confidence") and counter.calls == before}


def run_scenario(name: str, request_clip: dict, answer_clip: dict, pipe: VoicePipeline, expect: str, counter=None) -> dict:
    """A voiced request that makes P1 propose an action, then a voiced answer.

    expect: "execute" (a write ran), "cancel" (nothing written, nothing pending) or "unclear" (the answer is not
    a clear yes or no: not sent to P1, the action stays pending; the scenario then presses Cancel).
    """
    sid = f"voice-eval-{name}-{int(time.time())}"
    first = pipe.voice_turn(sid, clip_path(request_clip).read_bytes())
    out: dict = {"name": name, "expect": expect, "request_clip": request_clip["id"], "answer_clip": answer_clip["id"],
                 "request_transcript": first.transcript, "pending_after_request": bool(first.pending_action),
                 "request_order": (first.pending_action or {}).get("args", {}).get("order_id")}
    if not first.pending_action:
        out |= {"ok": False, "reason": "P1 did not propose an action for the request", "request_text": first.reply_text[:200]}
        return out
    before = counter.calls if counter is not None else None
    second = pipe.voice_turn(sid, clip_path(answer_clip).read_bytes())
    executed = [c for c in second.tool_calls if c.get("name") in WRITE_TOOLS and "error" not in (c.get("result") or {})]
    out |= {"answer_status": second.status, "answer_transcript": second.transcript, "answer_confidence": second.stt_confidence,
            "pending_after_answer": second.pending, "executed": [c["name"] for c in executed], "reply": second.reply_text[:300]}
    if expect == "execute":
        out["ok"] = second.status == "ok" and bool(executed) and not second.pending_action
    elif expect == "cancel":
        out["ok"] = second.status == "ok" and not executed and not second.pending_action
    else:
        sent = None if before is None else counter.calls - before
        out["agent_calls_for_answer"] = sent
        out["ok"] = second.status == "unclear_answer" and not executed and second.pending and sent in (0, None)
        pipe.press_button(sid, False)  # clean up: leave nothing pending in P1
    return out


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    ids = [r for r in rows if r["expected_order_id"]]
    tickets = [r for r in rows if r["expected_tool"] == "create_ticket"]
    return {
        "n": n,
        "typed_ok": sum(r["typed"].get("ok", False) for r in rows),
        "voiced_ok": sum(r["voiced"].get("ok", False) for r in rows),
        "id_n": len(ids), "id_typed_ok": sum(r["typed"].get("ok", False) for r in ids),
        "id_voiced_ok": sum(r["voiced"].get("ok", False) for r in ids),
        "ticket_n": len(tickets), "ticket_typed_ok": sum(r["typed"].get("ok", False) for r in tickets),
        "ticket_voiced_ok": sum(r["voiced"].get("ok", False) for r in tickets),
        "handoff_only_typed": sum(r["typed"].get("handoff_only", False) for r in rows),
        "handoff_only_voiced": sum(r["voiced"].get("handoff_only", False) for r in rows),
        "wrong_order_voiced": sum(r["voiced"].get("wrong_order", False) for r in rows),
        "wrong_order_typed": sum(r["typed"].get("wrong_order", False) for r in rows),
        "agent_ms_voiced": [r["voiced"]["timings"].get("agent_ms") for r in rows if r["voiced"].get("timings")],
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--own", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-confirm", action="store_true")
    ap.add_argument("--out", default=str(RESULTS_DIR / "e2e.json"), help="results file (default evals/results/e2e.json)")
    args = ap.parse_args()
    clips = load_manifest() + (load_manifest(own=True) if args.own else [])
    by_id = {c["id"]: c for c in clips if c.get("source") != "own"}
    queries = [c for c in clips if c["kind"] == "query"]
    if args.limit:
        queries = queries[: args.limit]
    counter = CountingAgent()
    pipe = VoicePipeline(agent=counter)
    pipe.preload()
    typed_agent = AgentClient(settings)
    if not typed_agent.healthy():
        raise SystemExit(f"P1 not reachable at {settings.agent_url}/health")
    started = time.time()
    result: dict = {"date": datetime.now().isoformat(timespec="seconds"), "agent_url": settings.agent_url,
                    "stt_language": settings.stt_language, "precondition": PRECONDITION,
                    "rows": [], "silent": [], "scenarios": []}
    for clip in queries:
        row = run_query(clip, pipe, typed_agent)
        result["rows"].append(row)
        print(f"{clip['id']} typed={row['typed'].get('ok')} voiced={row['voiced']['ok']} "
              f"{row['voiced'].get('transcript')!r} tools={row['voiced'].get('tools')}", flush=True)
    result["summary"] = {}
    for source in sorted({r["source"] for r in result["rows"]}):
        result["summary"][source] = summarize([r for r in result["rows"] if r["source"] == source])
    for clip in [c for c in clips if c["kind"] in QUIET_KINDS]:
        result["silent"].append(run_quiet(clip, pipe, counter))
        print("quiet", result["silent"][-1], flush=True)
    if not args.no_confirm:
        plan = [("voice-cancel", CANCEL_REQUEST, NO_CLIP, "cancel"), ("voice-unclear", UNCLEAR_REQUEST, UNCLEAR_CLIP, "unclear"),
                ("voice-confirm", CONFIRM_REQUEST, YES_CLIP, "execute")]  # confirm last: it is the only write
        for name, req, ans, expect in plan:
            if req in by_id and ans in by_id:
                result["scenarios"].append(run_scenario(name, by_id[req], by_id[ans], pipe, expect, counter))
            else:
                result["scenarios"].append({"name": name, "expect": expect, "ok": False, "reason": f"clip {req} or {ans} missing"})
            print("scenario", json.dumps(result["scenarios"][-1], ensure_ascii=False), flush=True)
    result["elapsed_s"] = round(time.time() - started)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result["summary"], indent=1))
    print("done: now run `python -m evals.report`")


if __name__ == "__main__":
    main()
