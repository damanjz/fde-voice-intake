"""Record your own voice for the 10 own-voice eval clips, in the browser (no extra Python audio packages).

    python -m evals.record          # then open http://localhost:8201 and record each prompt

Read the text on screen in your normal voice and your normal way of saying order ids ("el see eleven fifty",
"L C one one five zero", "double one five zero"). Clips are saved to evals/own/ with a manifest; then run
`python -m evals.run_stt --own` and `python -m evals.run_e2e --own`. Nothing leaves this machine.
"""

from __future__ import annotations

import json
import re
from typing import Annotated

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse

from evals.common import OWN_DIR, OWN_MANIFEST

PORT = 8201

# (id, text to read, expected order id, expected tool, kind)
PROMPTS = [
    ("O01", "Where is my order LC-1150?", "LC-1150", "lookup_order", "query"),
    ("O02", "Can you check order LC-1015 for me?", "LC-1015", "lookup_order", "query"),
    ("O03", "Has order LC-1050 shipped yet?", "LC-1050", "lookup_order", "query"),
    # O04 changed 2026-11-10 after own-voice run 1: LC-1144 holds only coffee beans, so "return the grinder" could never
    # start a return (the agent was right to refuse; typed text failed too). LC-1153 is a grinder delivered within 30 days.
    ("O04", "I want to return the grinder from order LC-1153.", "LC-1153", "start_return", "query"),
    ("O05", "My order LC-1163 arrived damaged, please start a return.", "LC-1163", "start_return", "query"),
    ("O06", "Is the Hand Burr Grinder Pro in stock?", None, "check_stock", "query"),
    ("O07", "I am not happy, I want to speak to a person.", None, "create_ticket", "query"),
    ("O08", "How long does shipping take to Hyderabad?", None, None, "query"),
    ("O09", "Yes, please go ahead.", None, None, "yes"),
    ("O10", "No, cancel that.", None, None, "no"),
]

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Record own-voice clips</title>
<style>body{font:16px/1.5 system-ui,sans-serif;max-width:640px;margin:24px auto;padding:0 16px;background:#f6f3ee;color:#231c17}
.row{background:#fff;border:1px solid #e2dbd2;border-radius:12px;padding:12px 14px;margin:10px 0;display:flex;gap:12px;align-items:center;justify-content:space-between}
.row small{color:#6f655c}button{border:0;border-radius:10px;padding:8px 16px;font:inherit;font-weight:600;background:#5a3a28;color:#fff;cursor:pointer}
button.rec{background:#c0392b}.ok{color:#2f6f4f;font-weight:600}</style></head><body>
<h1>Record own-voice clips</h1><p>Say each line your normal way, including how you say the order id. Click Record, speak, click Stop.</p>
<div id="list"></div>
<script>
const prompts = __PROMPTS__;
const list = document.getElementById("list"); let stream = null;
for (const p of prompts) {
  const row = document.createElement("div"); row.className = "row";
  row.innerHTML = `<div><b>${p.id}</b> ${p.text}<br><small id="s-${p.id}">not recorded</small></div><button id="b-${p.id}">Record</button>`;
  list.appendChild(row);
  const btn = row.querySelector("button"); let rec = null, chunks = [];
  btn.onclick = async () => {
    if (rec && rec.state === "recording") { rec.stop(); return; }
    stream = stream || await navigator.mediaDevices.getUserMedia({audio: true});
    chunks = []; rec = new MediaRecorder(stream);
    rec.ondataavailable = e => chunks.push(e.data);
    rec.onstop = async () => {
      btn.textContent = "Record"; btn.className = "";
      const f = new FormData(); f.append("audio", new Blob(chunks, {type: rec.mimeType}), p.id + ".webm");
      const r = await fetch("/save/" + p.id, {method: "POST", body: f});
      document.getElementById("s-" + p.id).innerHTML = r.ok ? '<span class="ok">saved</span>' : "save failed";
    };
    rec.start(); btn.textContent = "Stop"; btn.className = "rec";
  };
}
</script></body></html>"""


def manifest_entry(p: tuple) -> dict:
    cid, text, order, tool, kind = p
    return {"id": cid, "kind": kind, "group": "own_voice", "spoken": text, "typed": text,
            "expected_order_id": order, "expected_tool": tool, "length_scale": None, "snr_db": None,
            "file": f"{cid}.webm", "source": "own"}


def write_manifest() -> list[dict]:
    """Manifest of the prompts that have a saved recording."""
    entries = [manifest_entry(p) for p in PROMPTS if (OWN_DIR / f"{p[0]}.webm").exists()]
    OWN_MANIFEST.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    return entries


def create_app() -> FastAPI:
    app = FastAPI(title="Record own-voice clips")
    ids = {p[0] for p in PROMPTS}

    @app.get("/", response_class=HTMLResponse)
    def page() -> str:
        prompts = [{"id": p[0], "text": p[1]} for p in PROMPTS]
        return PAGE.replace("__PROMPTS__", json.dumps(prompts))

    @app.post("/save/{clip_id}")
    def save(clip_id: str, audio: Annotated[UploadFile, File()]) -> dict:
        if clip_id not in ids or not re.fullmatch(r"O\d\d", clip_id):
            raise HTTPException(404, "unknown clip id")
        data = audio.file.read(20 * 1024 * 1024)
        if len(data) < 500:
            raise HTTPException(400, "recording is empty")
        OWN_DIR.mkdir(parents=True, exist_ok=True)
        (OWN_DIR / f"{clip_id}.webm").write_bytes(data)
        return {"saved": clip_id, "clips_recorded": len(write_manifest())}

    return app


def main() -> None:
    import uvicorn

    OWN_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Open http://localhost:{PORT} and record the {len(PROMPTS)} prompts. Ctrl+C when done.")
    uvicorn.run(create_app(), host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
