# Engagement write-up: Larkfield voice intake

Larkfield Coffee Co. is fictional and all data is synthetic. Numbers below come from `evals/report.md`; where a number is not there yet, it says "unmeasured".

## 1. Discovery

**Who asked.** Larkfield's head of customer support (fictional, brief written by the portfolio owner). Older buyers and people on the move phone or message instead of typing; the typed support agent (project 1) already answers, looks up orders, and starts returns and tickets after a confirmation. The ask: let a customer talk to that same agent, and hear the answer.

**Success metrics agreed, and where each stands.**

| Metric | Target | Status |
|---|---|---|
| Voiced requests reach the same tool and order id as the typed text would | Within 5 points of typed accuracy on own-voice clips | Unmeasured: needs the own-voice recordings and the end-to-end run |
| An order id is never changed into a different real order | 0 cases | By construction (deterministic conversion, no list of real orders); the end-to-end run counts voiced calls on a different order id. Unmeasured end to end |
| Silent, noise-only or non-speech audio causes a call to the agent | 0 calls | Pipeline: 0 of 5 quiet synthetic clips reach the agent (4 produce no text; the babble clip produced text and is stopped by the confidence rule). End to end: unmeasured |
| A misheard yes starts a return | 0 cases | Reader: 0 hard-negative clips or phrases read as yes. End to end (voice confirm, voice cancel, "Yeah, no" scenarios): unmeasured |
| Speech overhead per turn (STT plus TTS) | Under 4 s p50 on CPU | Measured: about 2.1 s p50 (STT 1.7 s, TTS 0.4 s) on synthetic clips of 3 to 6 s. The agent's own time is unmeasured |

**Assumptions made.**
- Customers speak English or romanised Hinglish with Indian accents; reply audio is English.
- A browser is enough for v1; a phone channel would reuse the same `/voice/turn`.
- Speech models run on CPU because the GPU belongs to the agent's language model.
- Identity is not verified, as in project 1.
- Local only, no recurring cost, audio not kept after the request.

**Left out of v1, on purpose.**
- Barge-in (interrupting the reply) and streaming speech: the turn is record, send, wait, play.
- Telephony, caller identity checks, more than one voice or language of reply.
- Fine-tuning the speech model on Larkfield terms: a prompt carrying product names and the id format came first.
- Any attempt to guess a nearby real order id when an id sounds unclear.
- Side questions while an action waits for yes or no: a spoken turn then has to be a clear yes or no.

## 2. What was built

| Part | What it does |
|---|---|
| Browser page | Hold-to-talk with a visible recording state and level, live transcript (with what was heard), reply text, reply audio, per-stage latency, a Confirm/Cancel card that stays up whenever an action may be waiting |
| `POST /voice/turn` | Decode (whitelisted containers, length-limited), transcribe (Whisper `small`, int8, CPU, voice-activity filter), normalise, call the agent, make the reply speakable, synthesise (piper) |
| Normaliser | "el see eleven fifty", "L C one one five zero", "L.C. 1150", "LC double one five zero", "LC ek ek paanch zero" become `LC-1150`; fillers dropped; deterministic, never snapped to a real order; a bare number is an id only when the agent asked for one |
| Safety rules in the voice layer | Silence and low-confidence audio are not sent; while an action may be pending only a whole-utterance yes or a clear no is passed on (`confirm` true or false); unknown pending state is treated as pending; `/chat` is never retried; the pending action is spoken in full from `pending_action` |

## 3. How it was tested

- 338 unit and API tests with the agent mocked: normalisation of about 110 spoken forms, the yes/no reader with 35 hard negatives, speakable text, WER, pipeline rules, decoder limits, body caps, eval scoring, plus one test that runs the real models on a clip.
- 37 synthetic clips (piper, different speaking rates, six with added room noise): 25 questions including confusable ids (LC-1150 against LC-1015, LC-1050, LC-1115), 4 yes/no answers, 3 hard-negative answers ("Yeah, no", "Okay, bye", "Yes please, don't"), and 5 quiet clips (silence, room noise, laughter-like bursts, reversed-speech babble, keyboard clicks). Synthetic speech read back by Whisper is a best case: it checks the pipeline, not real-world accuracy.
- 10 own-voice prompts, recorded with `python -m evals.record` (run 1 2026-11-10, all re-recorded 2026-11-11 for run 2): 7/8 spoken end to end both times. Run 1's miss was bad case data (fixed); run 2's was one misheard order id, flagged and asked again. One speaker.
- End to end against project 1, run by the orchestrator: every query clip as typed text and as voice, each scored against the clip label (tool plus order id); quiet clips must cause no call; voice cancel (LC-1137), a voiced "Yeah, no" that must not be sent (LC-1154), and voice confirm (LC-1161, the only write). Return clips are matched to project 1's order data (delivered within 30 days, the named item present). Status: run 1 failed on test data (section 4); run 2 typed 22/25, voiced 23/25; run 3 typed 25/25, voiced 25/25, all three scenarios pass.

## 4. Findings so far

All numbers: `evals/report.md`, synthetic clips (optimistic), CPU.

| Finding | Number |
|---|---|
| Order ids correct after normalisation | 17/17 |
| Order ids correct in Whisper's own text, with the Larkfield prompt | 17/17 |
| Order ids correct in Whisper's own text, without the prompt (earlier 16-id run) | 7/16 (14/16 after normalisation) |
| WER, Whisper text against the typed reference, standard normalisation (headline) | 1.3% |
| WER with ids and numbers collapsed against the spoken-form reference (secondary) | 3.2% |
| Quiet clips where Whisper returned no text | 4/5 |
| Quiet clips that reach the agent | 0/5 (the babble clip became a fluent sentence at avg logprob -0.99; clean questions score -0.39 or better) |
| Spoken yes/no read correctly, P6 reader and project 1 `_typed_answer` | 4/4 each |
| Hard-negative spoken answers not taken as yes or no | 3/3 each |
| STT p50 / p95 | 1.6 s / 1.7 s for 3 to 6 s clips (synthetic); 1.6 s / 1.6 s on own voice (2026-11-11 run) |
| TTS p50 / p95 | 0.2 s / 0.5 s |
| `auto` against `en` | Same accuracy on clear English, slower: `en` is the default |

**End-to-end run 1 (2026-11-10) failed on test data, not on code.** Typed 21/24 and voiced 21/24; the quiet clips and both ticket clips passed; all three voice scenarios failed. Every failure was a return clip that did not match project 1's order data: a kettle from LC-1144 (an order of one House Blend bag), a grinder from LC-1199 (two Press Brewers, status placed, not delivered) and coffee beans from LC-1163 (a scale and two pour-over sets). Project 1 refused each one, and its refusal ("there is no kettle in this order") was the correct behaviour. The clips were rebuilt on orders checked against `data/orders.json`: LC-1137 (kettle that stopped heating), LC-1154 (grinder, change of mind), LC-1155 (damaged beans) and LC-1161 (leaking moka pot), with a unit test that re-checks them. Run 1 is kept as `evals/results/e2e-run1.json`.

What this does and does not show:
- With the Larkfield prompt Whisper writes ids as `LC-1150` on its own on these clips; without it only 7/16 come out right and the normaliser rescues 14/16. The unit suite, not the piper audio, is where the Indian ways of saying an id are tested.
- A first version sent a spoken yes to project 1 as plain text and relied on project 1's typed reader. A review found that "Yeah, no", "Ji nahi", "Okay, bye", "Do it later" and "Ha ha" all began with a yes word. Project 1's reader is now fixed, and P6 no longer depends on it: the voice layer classifies the whole utterance itself.
- The babble clip showed the voice-activity filter lets speech-like noise through and Whisper then invents a sentence. A confidence rule (avg logprob below -0.9 is not sent) stops it. That threshold rests on one clip and is a starting point; real noisy lines may need re-tuning.
- Project 1's `_typed_answer` still reads "Don't cancel it" as a no. P6 does not forward that phrase; the owner of project 1 should know.
- Not yet measured: own-voice accuracy, agent time per turn, typed against voiced tool accuracy, the voice confirm, cancel and "Yeah, no" scenarios against the real agent.

## 5. Known limits and what I would do next for a real customer
- Real accuracy is unmeasured until own-voice clips exist; the synthetic numbers are optimistic.
- The confidence thresholds (pending gate -0.8, reject -0.9) were set from a handful of clips; they should be re-tuned on real recordings.
- Hinglish was not tested with real Hinglish speech; `STT_LANGUAGE=auto` exists but is not the default.
- Next: stream speech and text to cut the turn time and allow barge-in; caller verification (OTP) before order details on a phone channel; a second voice or a Hindi reply voice; a human review sample of real calls.

**End-to-end runs 2 and 3 (2026-11-10).** Run 2 on the corrected clips: typed 22/25, voiced 23/25, voice cancel passed; the misses were project 1 explaining the return policy without proposing the return, for typed and voiced input alike, so the voice layer was not the cause. Project 1 gained a one-retry nudge for a stalled return request. Run 3: typed 25/25, voiced 25/25, quiet clips 5/5, voice cancel, unclear and confirm all pass. These are synthetic clips (optimistic); own-voice and real-microphone runs are still to do.
