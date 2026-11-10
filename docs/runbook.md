# Runbook: Larkfield voice intake

For the person operating the voice front end. Larkfield Coffee Co. is fictional. Everything runs locally; speech models run on CPU, so the GPU stays free for the support agent (project 1).

## Start
1. Project 1 is running (`docker compose up -d` in `fde-support-agent`, Ollama up): `curl http://localhost:8000/health`.
2. From the repo root:
   `python -m uvicorn app.main:app --port 8200`
   Models load at start (about 5 s).
3. Open http://localhost:8200, allow the microphone, hold the button and speak. Space also works.
4. Check: `curl http://localhost:8200/health` shows both models loaded and `agent_reachable: true`.

## Stop
Ctrl+C in the uvicorn window. Audio is not kept after the request (unless `VOICE_KEEP_AUDIO_DIR` is set for debugging).

## Settings (environment variables, see `.env.example`)
| Variable | Default | Meaning |
|---|---|---|
| `AGENT_URL` | `http://localhost:8000` | Project 1 base URL |
| `AGENT_TIMEOUT_S` | 180 | `/chat` timeout; P1 takes about 15 s p50 |
| `STT_LANGUAGE` | `en` | `en` forces English; `auto` picks English or Hindi (adds about 1 s) |
| `STT_BEAM_SIZE`, `STT_THREADS` | 5, 8 | Speed versus accuracy on CPU |
| `STT_MIN_LOGPROB`, `STT_MAX_NO_SPEECH` | -0.8, 0.5 | Confidence gate while an action is pending |
| `TTS_LENGTH_SCALE` | 1.0 | Speaking rate (higher is slower) |
| `VOICE_KEEP_AUDIO_DIR` | empty | Debug only: keep uploaded audio in this folder |

## Evals
```
python -m evals.make_clips      # one time: 30 synthetic clips (piper, CPU)
python -m evals.run_stt         # WER, order-id accuracy, silence, STT and TTS latency (CPU, about 3 min)
python -m evals.record          # own voice: open http://localhost:8201, record 10 prompts, Ctrl+C
python -m evals.run_stt --own
python -m evals.report          # evals/report.md and the README numbers table
python -m ruff check . ; python -m pytest -q
```

### End-to-end (needs project 1 and a free GPU, about 15 minutes)
```
set HF_HOME=models\hf
python -m evals.run_e2e
python -m evals.report
```
Add `--own` for recorded clips, `--limit N` for a short run, `--no-confirm` to skip the three voice scenarios. Scenario order: cancel (LC-1137, clip S14), unclear (LC-1154, clip S37), confirm (LC-1161, clip S16). Only the confirm scenario writes, and it creates one real return for LC-1161 in project 1's database.

Database precondition (also written to `e2e.json`): project 1's `returns` table has no open return for LC-1137, LC-1154, LC-1155 or LC-1161, and each of those orders is still delivered within 30 days (project 1 uses the real clock). To run twice, delete the LC-1161 return first. If P1 refuses a return clip, check the clip against `data/orders.json` before suspecting the code: run 1 failed only on mismatched clips. The run needs P1 on `AGENT_URL`; run one eval at a time (the GPU is shared).

## Changing things
| Change | Then |
|---|---|
| Normalisation or speakable rules | Add a test in `tests/test_normalize.py` or `tests/test_speakable.py`; `evals.run_stt` |
| Whisper prompt or language | `python -m evals.run_stt`; compare `en` and `auto` rows; rerun the end-to-end |
| Confidence thresholds | Look at the calibration table in `evals/report.md`; re-tune on own-voice clips |
| Piper voice | Download another voice into `models\piper\`, set `PIPER_VOICE`, rerun `evals.make_clips` and `evals.run_stt` |

## When something goes wrong
| Symptom | Check | Fix |
|---|---|---|
| Page says "Microphone not available" | Browser permission for localhost; another app holding the mic | Allow the mic, reload |
| Every reply is "I can't reach support right now" | `curl %AGENT_URL%/health`; P1 logs | Start P1 and Ollama; the call is never retried automatically, so speak again |
| "I couldn't check whether that went through" | A confirm or cancel timed out or P1 was down | Do not repeat it: ask for the order status, or check the confirmation email, then decide |
| "I didn't catch that" on real speech | Hold the button for the whole sentence; room noise; `/health` models loaded | Speak closer; check `stt_confidence` in the response JSON |
| "I wasn't sure what you said" or "Please say yes or no" | A return or ticket may be waiting and the answer was low confidence or not a clear whole-utterance yes or no | Say just "yes" or "no", or press Confirm or Cancel. After a restart or a timeout the service assumes an action is waiting; Cancel clears that |
| An order id is heard wrong | `transcript_raw` versus `transcript` in the response; the page flags ids that are not four digits | Say the id slowly, or press and say it as digits; the system never guesses a nearby real id |
| First turn is slow | Models load lazily if `--reload` is used | Start without `--reload` |
| `could not decode audio` (HTTP 400) | The upload is not wav or webm/opus/ogg/mp4 | Check the client's MediaRecorder type |
| Slow replies (over 30 s) | `ollama ps` shows the agent model on CPU, or another eval holds the GPU | Wait for the other job; see the P1 runbook |
