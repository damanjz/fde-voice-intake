# FDE Project 6: Voice intake agent

Spec v1, 2026-11-10. Part of the FDE Portfolio (vault: `Projects/In progress/FDE Portfolio`). Same fictional customer: Larkfield Coffee Co. (disclose as simulated).

## The customer problem
Many Larkfield customers (older buyers, people on the move) would rather talk than type. Goal: a voice front end for the project 1 support agent: the customer speaks, the agent answers out loud, and the same safety rules apply (confirmation before returns or tickets, hand-off when unsure). Built so a call-centre integration could replace the browser later.

## Stack (local only)
- New venv `.venv`. Installs approved by the owner on 2026-11-10: fastapi, uvicorn, httpx, pydantic, pytest, ruff, python-multipart, `faster-whisper` (speech model `small`, int8 on CPU), `piper-tts` with one English voice (about 70 MB). Models stored under `models\` (whisper and piper subfolders). Nothing else.
- The brain is the existing project 1 API (`POST http://localhost:8000/chat`, fields session_id, message, confirm). Do not copy its logic; call it.
  - (audit 2026-11-10) Contract, from P1 `app/main.py` and `app/agent.py`: request `{session_id: str, message: str, confirm: bool | null}`; response `{text, citations, tool_calls, pending_action, escalated, usage}`. P1 keeps the pending action per `session_id` on the server; P6 never sends `pending_action` back. Buttons send `confirm: true/false` with message "confirm"/"cancel" (as P1's own page does). A spoken answer is sent as a normal message with `confirm: null`: P1 already reads typed yes/no, including Hinglish, so P6 does not parse yes/no itself. Session ids start with `voice-`. P1 URL from env (default above).
  - (audit 2026-11-10) P1 takes about 15 s p50 per reply: client timeout 180 s, the page shows "working". If P1 is down or times out, speak a fixed "I can't reach support right now, please try again" and never auto-retry a `/chat` call (a retry repeats the turn).
- (audit 2026-11-10) P6 service on port 8200 (8000/8100/8300/8400/9000 are taken).
- Browser page (local HTML/JS, no CDN): hold-to-talk button (MediaRecorder), shows the live transcript, the agent's text and plays the reply audio; a Confirm/Cancel pair appears when the agent proposes an action, and saying "yes"/"no" also works.

## Pipeline (`app/`)
1. `POST /voice/turn` (audio upload, webm or wav) -> decode to 16 kHz mono (use what faster-whisper's bundled decoder supports; no system ffmpeg) -> faster-whisper `small`, language auto (English and Hinglish), with an initial prompt that biases toward Larkfield terms (order ids like "LC-1150", product names).
   - (audit 2026-11-10) Default `language="en"`: auto-detect on short clips can pick Hindi and return Devanagari or an English translation, and P1 handles romanised Hinglish, not Devanagari. Keep `auto` as an option and measure both on the eval set; the README states which won and by how much.
   - (audit 2026-11-10) `vad_filter=True` (bundled with faster-whisper). Whisper invents text on silence ("Thank you."), so an empty or no-speech transcript is never sent to P1: the page says "I didn't catch that".
2. Spoken-form normalisation in code: "el see eleven fifty" / "L C one one five zero" -> "LC-1150"; numbers in words to digits where they form an order id. (audit 2026-11-10) Deterministic conversion only: never snap a heard id to the nearest real order id (that would open another customer's order).
3. Send text to the project 1 API; pass through pending_action and confirm. (audit 2026-11-10) See the contract above: only `confirm` is passed. While an action is pending, a spoken turn goes to P1 only if the transcript is confident (thresholds on `avg_logprob` and `no_speech_prob`, set from the eval clips); otherwise the page asks the customer to repeat or press Confirm/Cancel. A misheard "yes" must not start a return.
4. Reply text made speakable in code: drop citation brackets, read "LC-1150" as "L C one one five zero", INR amounts as "rupees", shorten long lists.
5. piper synthesis -> wav -> returned with the text.
- Latency budget per turn shown on the page: STT ms, agent ms, TTS ms.
- Barge-in and streaming are out of scope v1 (document as next step).
- (audit 2026-11-10) Uploaded audio is deleted after transcription unless a debug flag is set; transcripts reach P1's logs, which mask PII. Identity is not verified (P1 known limit); the README says a phone channel would need verification before order details.

## Eval (`evals/`)
- Test audio: synthesise 30 customer utterances with piper (different speaking rates; a few with added background noise via numpy if available through faster-whisper deps, else plain), plus a script to record your own voice for 10 more later.
  - (audit 2026-11-10) A manifest per clip: reference text, expected order id (or none), expected tool (or none). Include confusable ids (LC-1150 vs LC-1015, "fifteen" vs "fifty"), spoken yes/no answers to a pending action, and 2 silent or noise-only clips that must produce no P1 call.
- Word error rate per utterance (implement WER in code) and order-id exact-match rate after normalisation.
- Intent check: the transcript sent to the agent leads to the same tool call as the typed text would (compare against project 1 replies for the typed version, run by the orchestrator). (audit 2026-11-10) Score both the typed reference text and the voiced transcript against the manifest label (tool name plus order id), not against each other: P1 is not deterministic, so typed-vs-voiced agreement mixes STT errors with model noise. Typed accuracy is the ceiling; the gap is the cost of voice.
- (audit 2026-11-10) Piper-generated clips read back by Whisper are a best case (clean synthetic speech). Report synthetic and own-voice clips in separate rows; the README labels the synthetic numbers as optimistic and makes no real-world accuracy claim from them.
- Latency p50/p95 for STT and TTS on this machine.
- Unit tests: normalisation (order ids, numbers, Hinglish fillers), speakable-text conversion, WER.
- GPU is shared: STT/TTS run on CPU. Do not call Ollama or the project 1 API during the build; the orchestrator runs the end-to-end eval.

## Deliverables
README (numbers table on top), `docs/runbook.md`, `docs/engagement.md` (audit 2026-11-10: it opens with discovery: who asked, the success metric agreed, assumptions made, what was left out). No emoji. No git commit by the builder.

## Done when
ruff clean, pytest green, WER and order-id accuracy measured on the 30 synthetic clips, end-to-end turn works against the project 1 API (orchestrator run), README matches `evals/report.md`. (audit 2026-11-10) The end-to-end run includes one return confirmed by voice and one cancelled by voice, and the silent clips produce no P1 call.
