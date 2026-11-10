# Voice intake eval report

STT run 2026-11-11T00:01:25 (276 s). All speech models run on CPU. Fictional customer, synthetic clips.

## Numbers

STT language setting: `en`. Synthetic clips are piper speech read back by Whisper: a best case, optimistic, and no real-world accuracy claim is made from them.

| Measure | Synthetic clips (optimistic) | Own voice |
|---|---|---|
| Clips | 37 | 10 |
| WER, Whisper text vs the typed reference (standard normalisation) | 1.3% | 12.1% |
| WER with ids and numbers collapsed, vs the spoken-form reference (secondary) | 3.2% | 8.8% |
| Order-id exact match (after normalisation) | 17/17 (100%) | 4/5 (80%) |
| Order-id exact match, Whisper text alone (before normalisation) | 17/17 (100%) | 4/5 (80%) |
| Spoken yes/no read correctly, P6 strict reader | 4/4 (100%) | 2/2 (100%) |
| Spoken yes/no read correctly, P1 `_typed_answer` | 4/4 (100%) | 2/2 (100%) |
| Hard-negative spoken answers not taken as yes or no, P6 / P1 | 3/3 (100%) / 3/3 (100%) | - / - |
| Quiet clips (silence, noise, laughter, babble, keyboard) where Whisper returned no text | 4/5 (80%) | - |
| Quiet clips producing no agent call (no text, or blocked by the confidence rule) | 5/5 (100%) | - |
| STT latency p50 / p95 (CPU, int8) | 1.6 s / 1.7 s | 1.6 s / 1.6 s |
| TTS latency p50 / p95 (piper, CPU, 12 sample replies) | 211 ms / 493 ms | same voice |
| End-to-end tool + order id correct, typed text (ceiling) | 25/25 (100%) | not run |
| End-to-end tool + order id correct, voiced | 25/25 (100%) | not run |
| Real create_ticket calls (typed / voiced), of 2 ticket clips | 2 / 2 | not run |
| Hand-offs with no ticket call (typed / voiced), counted separately | 0 / 0 | not run |
| Silent, noise and non-speech clips causing no agent call | 5/5 (100%) | not run |
| Scenario voice-cancel | pass | not run |
| Scenario voice-unclear | pass | not run |
| Scenario voice-confirm | pass | not run |

`en` against `auto` on the synthetic clips: `en` wins on speed: same accuracy, `auto` is 1154 ms slower at p50. Order-id matches 17 (`en`) vs 17 (`auto`); `auto` chose: en. All synthetic speech is clear English, so this says nothing about real Hinglish speakers. The default stays `en` because Hindi detection can return Devanagari or a translation, which the agent does not read.

## STT language setting: en vs auto (synthetic clips)

| Setting | WER vs typed ref | Order-id exact | Order-id, Whisper text alone | STT p50 | STT p95 | Quiet clips, no agent call |
|---|---|---|---|---|---|---|
| `en` | 1.3% | 17/17 (100%) | 17/17 (100%) | 1.6 s | 1.7 s | 5/5 (100%) |
| `auto` | 1.3% | 17/17 (100%) | 17/17 (100%) | 2.7 s | 3.0 s | 5/5 (100%) |
| `en-noprompt` | 9.4% | 15/17 (88%) | 9/17 (53%) | 1.3 s | 1.5 s | 5/5 (100%) |

`en` against `auto` on the synthetic clips: `en` wins on speed: same accuracy, `auto` is 1154 ms slower at p50. Order-id matches 17 (`en`) vs 17 (`auto`); `auto` chose: en. All synthetic speech is clear English, so this says nothing about real Hinglish speakers. The default stays `en` because Hindi detection can return Devanagari or a translation, which the agent does not read.

## Latency

| Stage | p50 | p95 | Note |
|---|---|---|---|
| STT (`en`, small int8, CPU) | 1.6 s | 1.7 s | real-time factor 0.41 (decode, VAD and decode included) |
| TTS (piper, CPU) | 211 ms | 493 ms | 12 sample replies, real-time factor 0.025 |
| Agent (P1, GPU) | 12.9 s | 18.0 s | measured in the end-to-end run |

## Per-clip transcripts (synthetic clips)

Language `en`. Raw = what Whisper returned; sent = after normalisation (what the agent receives).

| Clip | Kind | SNR | Spoken | Raw transcript | Sent to agent | WER vs typed | Order id | Answer read (P6 / P1) | avg logprob |
|---|---|---|---|---|---|---|---|---|---|
| S01 | query | - | Where is my order L C one one five zero? | Where is my order LC-1150? | Where is my order LC-1150? | 0% | ok | - | -0.34 |
| S02 | query | - | Where is my order L C one zero one five? | Where is my order LC-1015? | Where is my order LC-1015? | 0% | ok | - | -0.29 |
| S03 | query | - | Can you check el see eleven fifty for me please | Can you check LC-1150 for me please? | Can you check LC-1150 for me please? | 0% | ok | - | -0.30 |
| S04 | query | - | What is the status of L C ten fifty | What is the status of LC-1050? | What is the status of LC-1050? | 0% | ok | - | -0.15 |
| S05 | query | - | Has el see eleven fifteen been shipped yet? | Has LC-1115 been shipped yet? | Has LC-1115 been shipped yet? | 0% | ok | - | -0.28 |
| S06 | query | - | I placed order L C ten fifteen last week and nothing has come | I placed order LC-1015 last week and nothing has come. | I placed order LC-1015 last week and nothing has come. | 0% | ok | - | -0.20 |
| S07 | query | - | Please track L C double one six seven | Please track LC-1167. | Please track LC-1167. | 0% | ok | - | -0.35 |
| S08 | query | - | Order el see ten oh one, when will it be delivered? | Order LC-1001, when will it be delivered? | Order LC-1001, when will it be delivered? | 0% | ok | - | -0.29 |
| S09 | query | - | My order number is L C one thousand one hundred twenty five | My order number is LC-1125. | My order number is LC-1125. | 0% | ok | - | -0.32 |
| S10 | query | - | L C twelve hundred, where is the parcel? | LC-1200, where is the parcel? | LC-1200, where is the parcel? | 0% | ok | - | -0.37 |
| S11 | query | 15 | Please look up el see one one zero seven | Please look up LC-1107. | Please look up LC-1107. | 0% | ok | - | -0.34 |
| S12 | query | 10 | Is order L C eleven oh nine delivered? | Is Order LC-1109 delivered? | Is Order LC-1109 delivered? | 0% | ok | - | -0.38 |
| S13 | query | 20 | Order L C one one eight eight has not arrived | Order LC-1188 has not arrived. | Order LC-1188 has not arrived. | 0% | ok | - | -0.32 |
| S14 | query | - | I want to return the kettle from order L C eleven thirty seven, it stopped heating | I want to return the kettle from Order LC-1137, it stopped heating. | I want to return the kettle from Order LC-1137, it stopped heating. | 0% | ok | - | -0.19 |
| S15 | query | 15 | The coffee beans from order el see eleven fifty five arrived damaged, I want to return them | The coffee beans from order LC-1155 arrive damaged. I want to return them. | The coffee beans from order LC-1155 arrive damaged. I want to return them. | 5% | ok | - | -0.30 |
| S16 | query | - | Please start a return for order L C eleven sixty one, the moka pot is leaking | Please start a return for order LC-1161. The Moka Pot is leaking. | Please start a return for order LC-1161. The Moka Pot is leaking. | 0% | ok | - | -0.21 |
| S37 | query | - | I want to return the grinder from order L C eleven fifty four, I changed my mind | I want to return the Grinder from Order LC-1154, I changed my mind. | I want to return the Grinder from Order LC-1154, I changed my mind. | 0% | ok | - | -0.30 |
| S17 | query | - | Do you have the Larkfield Hand Burr Grinder Pro in stock? | Do you have the Larkfield Hand Burr Grinder Pro in stock? | Do you have the Larkfield Hand Burr Grinder Pro in stock? | 0% | - | - | -0.23 |
| S18 | query | - | Is the Espresso Grinder sixty four millimetre available? | Is the Espresso Grinder 64mm available? | Is the Espresso Grinder 64mm available? | 0% | - | - | -0.32 |
| S19 | query | - | How long does shipping take to Hyderabad? | How long does shipping take to Hyderabad? | How long does shipping take to Hyderabad? | 0% | - | - | -0.29 |
| S20 | query | 10 | What is your return policy for coffee beans? | What is your return policy for coffee beans? | What is your return policy for coffee beans? | 0% | - | - | -0.31 |
| S21 | query | - | How long is the warranty on the electric burr grinder? | How long is the warranty on the Electric Burr Grinder? | How long is the warranty on the Electric Burr Grinder? | 0% | - | - | -0.26 |
| S22 | query | - | How do I cancel my coffee subscription? | How do I cancel my coffee subscription? | How do I cancel my coffee subscription? | 0% | - | - | -0.35 |
| S23 | query | - | I am very unhappy and I want to speak to a person | I'm very unhappy and I want to speak to a person. | I'm very unhappy and I want to speak to a person. | 17% | - | - | -0.25 |
| S24 | query | - | Please raise a ticket, my invoice has the wrong address | Please raise a ticket, my invoice has the wrong address. | Please raise a ticket, my invoice has the wrong address. | 0% | - | - | -0.34 |
| S25 | yes | - | Yes, please go ahead. | Yes, please go ahead. | Yes, please go ahead. | 0% | - | yes / yes | -0.30 |
| S26 | yes | 15 | Yeah sure, do it. | Yeah, sure, do it. | Yeah, sure, do it. | 0% | - | yes / yes | -0.40 |
| S27 | no | - | No, cancel that. | No, cancel that. | No, cancel that. | 0% | - | no / no | -0.25 |
| S28 | no | 15 | No thanks, I will keep it. | No thanks. I will keep it. | No thanks. I will keep it. | 0% | - | no / no | -0.26 |
| S31 | hardneg | - | Yeah, no. | Yo, no. | Yo, no. | 50% | - | None / None | -0.76 |
| S32 | hardneg | - | Okay, bye. | Okay, bye. | Okay, bye. | 0% | - | None / None | -0.60 |
| S33 | hardneg | - | Yes please, don't. | Yes please, don't. | Yes please, don't. | 0% | - | None / None | -0.32 |
| S29 | silent | - |  |  |  | - | - | - | - |
| S30 | noise | - |  |  |  | - | - | - | - |
| S34 | nonspeech | - |  |  |  | - | - | - | - |
| S35 | nonspeech | - |  | They are worth living up to the number of girls around the world at home. | They are worth living up to the number of girls around the world at home. | - | - | - | -0.99 |
| S36 | nonspeech | - |  |  |  | - | - | - | - |
| O01 | query | - | Where is my order LC-1150? | Where is my order? LC-1150. | Where is my order? LC-1150. | 0% | ok | - | -0.38 |
| O02 | query | - | Can you check order LC-1015 for me? | Can you check order LC-1015 for me? | Can you check order LC-1015 for me? | 0% | ok | - | -0.36 |
| O03 | query | - | Has order LC-1050 shipped yet? | Has the order LC-1011050 shipped yet? | Has the order LC-1011050 shipped yet? | 88% | WRONG | - | -0.30 |
| O04 | query | - | I want to return the grinder from order LC-1153. | I want to return the grinder from order LC-1153. | I want to return the grinder from order LC-1153. | 0% | ok | - | -0.31 |
| O05 | query | - | My order LC-1163 arrived damaged, please start a return. | My order LC-1163 arrived damaged. Please start a return. | My order LC-1163 arrived damaged. Please start a return. | 0% | ok | - | -0.41 |
| O06 | query | - | Is the Hand Burr Grinder Pro in stock? | Is the Hand Burr Grinder Pro in stock? | Is the Hand Burr Grinder Pro in stock? | 0% | - | - | -0.41 |
| O07 | query | - | I am not happy, I want to speak to a person. | I'm not happy. I want to speak to a person. | I'm not happy. I want to speak to a person. | 18% | - | - | -0.31 |
| O08 | query | - | How long does shipping take to Hyderabad? | How long does shipping take to Hyderabad usually? | How long does shipping take to Hyderabad usually? | 14% | - | - | -0.35 |
| O09 | yes | - | Yes, please go ahead. | Yeah, please go ahead. | Yeah, please go ahead. | 25% | - | yes / yes | -0.32 |
| O10 | no | - | No, cancel that. | No. Cancel that. | No. Cancel that. | 0% | - | no / no | -0.39 |

## Yes/no readers

Text-only hard negatives: a yes or no word followed by a negation, delay, laugh or goodbye. A careful reader returns nothing (an unclear answer), never yes.

| Phrase | P6 strict reader | P1 `_typed_answer` |
|---|---|---|
| Yeah, no | not an answer | not an answer |
| Ji nahi | not an answer | not an answer |
| Haan nahi | not an answer | not an answer |
| Okay, bye | not an answer | not an answer |
| Ha ha | not an answer | not an answer |
| Do it later | not an answer | not an answer |
| Yes, no, wait | not an answer | not an answer |
| Yeah, cancel it | not an answer | not an answer |
| Yes please don't | not an answer | not an answer |
| Yes but | not an answer | not an answer |
| Ok so what is the fee? | not an answer | not an answer |
| Yes tomorrow | not an answer | not an answer |
| Don't cancel it | not an answer | no |

P1 reader: available (loaded read-only from the project 1 agent file, only in the eval).

## Confidence gate calibration

Extra noisy copies of the four yes/no clips (not part of the 30). The gate blocks a spoken answer while an action is pending when avg logprob is below -0.8 or no-speech probability is above 0.5.

| Clip | SNR dB | Heard | Right answer | avg logprob | no-speech | Gate |
|---|---|---|---|---|---|---|
| S25 (yes) | 5 | Yes, please go ahead. | yes | -0.30 | 0.05 | passes |
| S25 (yes) | 0 | Yes, please go ahead. | yes | -0.29 | 0.05 | passes |
| S25 (yes) | -5 | Yes, please go ahead. | yes | -0.27 | 0.14 | passes |
| S26 (yes) | 5 | Yeah, sure, do it. | yes | -0.37 | 0.06 | passes |
| S26 (yes) | 0 | Yeah, sure, do it. | yes | -0.55 | 0.09 | passes |
| S26 (yes) | -5 | Yes, sure. | yes | -0.67 | 0.16 | passes |
| S27 (no) | 5 | No, cancel that. | yes | -0.34 | 0.02 | passes |
| S27 (no) | 0 | No, cancel that. | yes | -0.40 | 0.07 | passes |
| S27 (no) | -5 | No, cancel that. | yes | -0.31 | 0.07 | passes |
| S28 (no) | 5 | No thanks, I will keep it. | yes | -0.24 | 0.03 | passes |
| S28 (no) | 0 | No thanks. I will keep it. | yes | -0.23 | 0.04 | passes |
| S28 (no) | -5 | No thanks, I will keep. | yes | -0.44 | 0.12 | passes |

Wrong answers that passed the gate: 0 of 12. Right answers blocked: 0 of 12. Twelve clips is a small sample: the thresholds are a starting point to re-tune on own-voice clips.

## End-to-end against the support agent

Run 2026-11-10T14:45:50 against http://localhost:8000 (STT language `en`, 722 s).

Run 1 (2026-11-10T04:02:11, kept as `evals/results/e2e-run1.json`): typed 21/24, voiced 21/24, all three voice scenarios failed. All six failures were bad test data, not code: the return clips named an item the order did not hold (a kettle from an order of coffee beans, beans from an order of a scale and glassware) or an order that was not delivered. Project 1's refusals (for example "there is no kettle in this order") were the correct behaviour. The clips were then changed to match project 1's order data (see the manifest notes).

Database precondition: Return clips match P1's order data (delivered within 30 days, item present): LC-1137 (voice-cancel, clip S14), LC-1154 (voice-unclear, clip S37), LC-1155 (clip S15, pending only), LC-1161 (voice-confirm, clip S16). P1's returns table has no open return for any of them. voice-confirm creates one return for LC-1161, so a second run needs that return removed or another matching order.

| Clip | Label | Typed ok | Voiced ok | Voiced transcript | Voiced tools | Agent ms (voiced) |
|---|---|---|---|---|---|---|
| S01 (synthetic) | lookup_order LC-1150 | True | True | Where is my order LC-1150? | lookup_order | 13384 |
| S02 (synthetic) | lookup_order LC-1015 | True | True | Where is my order LC-1015? | lookup_order | 11709 |
| S03 (synthetic) | lookup_order LC-1150 | True | True | Can you check LC-1150 for me please? | lookup_order | 13468 |
| S04 (synthetic) | lookup_order LC-1050 | True | True | What is the status of LC-1050? | lookup_order | 14700 |
| S05 (synthetic) | lookup_order LC-1115 | True | True | Has LC-1115 been shipped yet? | lookup_order | 18372 |
| S06 (synthetic) | lookup_order LC-1015 | True | True | I placed order LC-1015 last week and nothing has come. | lookup_order | 18351 |
| S07 (synthetic) | lookup_order LC-1167 | True | True | Please track LC-1167. | lookup_order | 12961 |
| S08 (synthetic) | lookup_order LC-1001 | True | True | Order LC-1001, when will it be delivered? | lookup_order | 10986 |
| S09 (synthetic) | lookup_order LC-1125 | True | True | My order number is LC-1125. | lookup_order | 13505 |
| S10 (synthetic) | lookup_order LC-1200 | True | True | LC-1200, where is the parcel? | lookup_order | 10860 |
| S11 (synthetic) | lookup_order LC-1107 | True | True | Please look up LC-1107. | lookup_order | 13693 |
| S12 (synthetic) | lookup_order LC-1109 | True | True | Is Order LC-1109 delivered? | lookup_order | 11320 |
| S13 (synthetic) | lookup_order LC-1188 | True | True | Order LC-1188 has not arrived. | lookup_order | 12929 |
| S14 (synthetic) | start_return LC-1137 | True | True | I want to return the kettle from Order LC-1137, it stopped heating. | lookup_order, start_return | 15946 |
| S15 (synthetic) | start_return LC-1155 | True | True | The coffee beans from order LC-1155 arrive damaged. I want to return them. | lookup_order, start_return | 13263 |
| S16 (synthetic) | start_return LC-1161 | True | True | Please start a return for order LC-1161. The Moka Pot is leaking. | lookup_order, start_return | 14164 |
| S37 (synthetic) | start_return LC-1154 | True | True | I want to return the Grinder from Order LC-1154, I changed my mind. | lookup_order, start_return | 16433 |
| S17 (synthetic) | check_stock | True | True | Do you have the Larkfield Hand Burr Grinder Pro in stock? | check_stock | 10563 |
| S18 (synthetic) | check_stock | True | True | Is the Espresso Grinder 64mm available? | check_stock | 10967 |
| S19 (synthetic) | no tool | True | True | How long does shipping take to Hyderabad? |  | 7533 |
| S20 (synthetic) | no tool | True | True | What is your return policy for coffee beans? |  | 9034 |
| S21 (synthetic) | no tool | True | True | How long is the warranty on the Electric Burr Grinder? |  | 7369 |
| S22 (synthetic) | no tool | True | True | How do I cancel my coffee subscription? |  | 8891 |
| S23 (synthetic) | create_ticket | True | True | I'm very unhappy and I want to speak to a person. | create_ticket | 8500 |
| S24 (synthetic) | create_ticket | True | True | Please raise a ticket, my invoice has the wrong address. | create_ticket | 8251 |

| Source | Clips | Typed correct | Voiced correct | Order-id clips typed / voiced | Voiced calls on a different order id |
|---|---|---|---|---|---|
| synthetic | 25 | 25/25 (100%) | 25/25 (100%) | 17/17 / 17/17 | 0 |

| Source | create_ticket clips | Real ticket call, typed | Real ticket call, voiced | Hand-off with no ticket, typed | Hand-off with no ticket, voiced |
|---|---|---|---|---|---|
| synthetic | 2 | 2 | 2 | 0 | 0 |

Typed accuracy is the ceiling; the gap to voiced is the cost of voice. P1 is not deterministic, so single runs differ by a case or two.

| Quiet clip | Status | Heard | P1 calls | Pass |
|---|---|---|---|---|
| S29 (silent) | no_speech | - | 0 | True |
| S30 (noise) | no_speech | - | 0 | True |
| S34 (nonspeech) | no_speech | - | 0 | True |
| S35 (nonspeech) | low_confidence | They are worth living up to the number of girls around the world at home. | 0 | True |
| S36 (nonspeech) | no_speech | - | 0 | True |

| Scenario | Expect | Request clip (order) | Answer clip | Answer heard | Pending after request | Executed | Pass |
|---|---|---|---|---|---|---|---|
| voice-cancel | cancel | S14 (LC-1137) | S27 | No, cancel that. | True | none | True |
| voice-unclear | unclear | S37 (LC-1154) | S31 | Yo, no. | True | none | True |
| voice-confirm | execute | S16 (LC-1161) | S25 | Yes, please go ahead. | True | start_return | True |

## How to read this

- Synthetic clips are piper speech read back by Whisper. They test the pipeline (decoding, normalisation, id handling, silence) and are optimistic for accuracy.
- The headline WER compares Whisper's own text with the typed reference after standard text normalisation (case, punctuation, hyphens, digits read as words). The secondary WER collapses order ids and numbers on both sides against the spoken-form reference: it is lower, but it also forgives formatting, so it is not the headline. The order-id columns are scored against the manifest label, not against the normaliser.
- Quiet clips are silence, room noise, and three non-speech sounds a voice-activity filter can let through (laughter-like bursts, reversed-speech babble, keyboard clicks). Passing means no text, so no agent call.
- Own-voice rows stay empty until `python -m evals.record` and the `--own` runs have been done.
