"""Render evals/report.md and the numbers table in README.md from evals/results/*.json.

    python -m evals.report

README numbers are copied from here, never typed by hand. End-to-end rows stay "pending" until
`python -m evals.run_e2e` has written evals/results/e2e.json.
"""

from __future__ import annotations

import json
import re

from app.config import settings
from evals.common import EVALS, RESULTS_DIR

README = EVALS.parent / "README.md"
START, END = "<!-- numbers:start -->", "<!-- numbers:end -->"
PENDING = "pending (orchestrator runs `python -m evals.run_e2e`)"


def load(name: str) -> dict | None:
    path = RESULTS_DIR / name
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def pct(x: float | None, digits: int = 1) -> str:
    return "-" if x is None else f"{100 * x:.{digits}f}%"


def sec(ms: float | None) -> str:
    return "-" if ms is None else (f"{ms / 1000:.1f} s" if ms >= 1000 else f"{ms:.0f} ms")


def frac(a: int, b: int) -> str:
    return f"{a}/{b} ({pct(a / b, 0)})" if b else "-"


def pick_default(stt: dict) -> str:
    return "en" if "en" in stt["runs"] else next(iter(stt["runs"]))


def is_run1(e2e: dict | None) -> bool:
    """e2e.json still holds run 1, whose test data did not match the orders: its numbers are not a result."""
    run1 = load("e2e-run1.json")
    return bool(e2e and run1 and e2e.get("date") == run1.get("date"))


RUN1_PENDING = "pending: run 1 failed on test data that did not match the orders (kept in e2e-run1.json); run 2 not done yet"


def numbers_table(stt: dict | None, e2e: dict | None) -> str:
    if e2e and is_run1(e2e):
        e2e = None  # shown as pending in the table; the detail stays in the end-to-end section
    if not stt:
        return "_No STT results yet: run `python -m evals.run_stt`._"
    lang = pick_default(stt)
    syn = stt["runs"][lang]["summary"].get("synthetic")
    own = stt["runs"][lang]["summary"].get("own")
    tts = stt["tts"]

    def col(s: dict | None, key: str, fmt) -> str:
        return fmt(s) if s else "not recorded yet"

    rows = [
        ("Clips", lambda s: str(s["clips"])),
        ("WER, Whisper text vs the typed reference (standard normalisation)", lambda s: pct(s["wer_typed"])),
        ("WER with ids and numbers collapsed, vs the spoken-form reference (secondary)", lambda s: pct(s["wer_norm"])),
        ("Order-id exact match (after normalisation)", lambda s: frac(s["id_exact"], s["id_total"])),
        ("Order-id exact match, Whisper text alone (before normalisation)", lambda s: frac(s.get("id_raw_exact", 0), s["id_total"])),
        ("Spoken yes/no read correctly, P6 strict reader", lambda s: frac(s["yn_ok"], s["yn_total"])),
        ("Spoken yes/no read correctly, P1 `_typed_answer`", lambda s: frac(s["yn_ok_p1"], s["yn_total"]) if s.get("yn_ok_p1") is not None else "n/a"),
        ("Hard-negative spoken answers not taken as yes or no, P6 / P1", lambda s: f"{frac(s['hardneg_ok'], s['hardneg_total'])} / " + (frac(s["hardneg_ok_p1"], s["hardneg_total"]) if s.get("hardneg_ok_p1") is not None else "n/a")),
        ("Quiet clips (silence, noise, laughter, babble, keyboard) where Whisper returned no text", lambda s: frac(s["quiet_ok"], s["quiet_total"])),
        ("Quiet clips producing no agent call (no text, or blocked by the confidence rule)", lambda s: frac(s.get("quiet_blocked", s["quiet_ok"]), s["quiet_total"])),
        ("STT latency p50 / p95 (CPU, int8)", lambda s: f"{sec(s['stt_ms_p50'])} / {sec(s['stt_ms_p95'])}"),
    ]
    intro = (f"STT language setting: `{lang}`. Synthetic clips are piper speech read back by Whisper: a best case, "
             "optimistic, and no real-world accuracy claim is made from them.")
    out = [intro, "", "| Measure | Synthetic clips (optimistic) | Own voice |", "|---|---|---|"]
    for label, fn in rows:
        out.append(f"| {label} | {col(syn, '', fn)} | {col(own, '', fn)} |")
    out.append(f"| TTS latency p50 / p95 (piper, CPU, {tts['n']} sample replies) | {sec(tts['ms_p50'])} / {sec(tts['ms_p95'])} | same voice |")
    if e2e:
        def e2e_cell(source: str, key: str) -> str:
            s = e2e["summary"].get(source)
            return frac(s[key], s["n"]) if s else "not run"

        out.append(f"| End-to-end tool + order id correct, typed text (ceiling) | {e2e_cell('synthetic', 'typed_ok')} | {e2e_cell('own', 'typed_ok')} |")
        out.append(f"| End-to-end tool + order id correct, voiced | {e2e_cell('synthetic', 'voiced_ok')} | {e2e_cell('own', 'voiced_ok')} |")
        s_ = e2e["summary"].get("synthetic")
        if s_:
            out.append(f"| Real create_ticket calls (typed / voiced), of {s_['ticket_n']} ticket clips | {s_['ticket_typed_ok']} / {s_['ticket_voiced_ok']} | not run |")
            out.append(f"| Hand-offs with no ticket call (typed / voiced), counted separately | {s_['handoff_only_typed']} / {s_['handoff_only_voiced']} | not run |")
        sil = e2e.get("silent", [])
        out.append(f"| Silent, noise and non-speech clips causing no agent call | {frac(sum(x['ok'] for x in sil), len(sil))} | not run |")
        for sc in e2e.get("scenarios", []):
            out.append(f"| Scenario {sc['name']} | {'pass' if sc.get('ok') else 'FAIL: ' + str(sc.get('reason', ''))} | not run |")
    else:
        pending = RUN1_PENDING if is_run1(load("e2e.json")) else PENDING
        for label in ("End-to-end tool + order id correct, typed text (ceiling)", "End-to-end tool + order id correct, voiced",
                      "Quiet clips causing no agent call (end to end)", "Voice cancel, voice unclear answer, voice confirm of a return"):
            out.append(f"| {label} | {pending} | pending |")
    note = language_note(stt)
    if note:
        out += ["", note]
    return "\n".join(out)


def language_table(stt: dict) -> str:
    out = ["| Setting | WER vs typed ref | Order-id exact | Order-id, Whisper text alone | STT p50 | STT p95 | Quiet clips, no agent call |",
           "|---|---|---|---|---|---|---|"]
    for lang, run in stt["runs"].items():
        s = run["summary"].get("synthetic")
        if s:
            out.append(f"| `{lang}` | {pct(s['wer_typed'])} | {frac(s['id_exact'], s['id_total'])} | "
                       f"{frac(s.get('id_raw_exact', 0), s['id_total'])} | {sec(s['stt_ms_p50'])} | "
                       f"{sec(s['stt_ms_p95'])} | {frac(s.get('quiet_blocked', s['quiet_ok']), s['quiet_total'])} |")
    note = language_note(stt)
    if note:
        out += ["", note]
    return "\n".join(out)


def language_note(stt: dict) -> str:
    """Which STT language setting won on the synthetic clips, and by how much."""
    runs = stt["runs"]
    if "en" not in runs or "auto" not in runs:
        return ""
    a, b = runs["en"]["summary"].get("synthetic"), runs["auto"]["summary"].get("synthetic")
    if not (a and b):
        return ""
    diff_wer = (b["wer_typed"] - a["wer_typed"]) * 100
    diff_ms = b["stt_ms_p50"] - a["stt_ms_p50"]
    langs = ", ".join(sorted({r["language"] for r in runs["auto"]["rows"] if r["source"] == "synthetic"}))
    if abs(diff_wer) < 0.05 and a["id_exact"] == b["id_exact"]:
        verdict = f"`en` wins on speed: same accuracy, `auto` is {abs(diff_ms):.0f} ms {'slower' if diff_ms > 0 else 'faster'} at p50"
    elif diff_wer > 0 or b["id_exact"] < a["id_exact"]:
        verdict = f"`en` wins: WER {abs(diff_wer):.1f} points lower or ids better; `auto` STT p50 {diff_ms:+.0f} ms"
    else:
        verdict = f"`auto` wins on accuracy: WER {abs(diff_wer):.1f} points lower; STT p50 {diff_ms:+.0f} ms"
    return (f"`en` against `auto` on the synthetic clips: {verdict}. Order-id matches {a['id_exact']} (`en`) vs "
            f"{b['id_exact']} (`auto`); `auto` chose: {langs}. All synthetic speech is clear English, so this says "
            "nothing about real Hinglish speakers. The default stays `en` because Hindi detection can return "
            "Devanagari or a translation, which the agent does not read.")


def clip_table(stt: dict) -> str:
    lang = pick_default(stt)
    out = [f"Language `{lang}`. Raw = what Whisper returned; sent = after normalisation (what the agent receives).", "",
           "| Clip | Kind | SNR | Spoken | Raw transcript | Sent to agent | WER vs typed | Order id | Answer read (P6 / P1) | avg logprob |", "|---|---|---|---|---|---|---|---|---|---|"]
    for r in stt["runs"][lang]["rows"]:
        wer_n = f"{100 * r['wer_typed']:.0f}%" if "wer_typed" in r else "-"
        ans = f"{r['p6_answer']} / {r.get('p1_answer')}" if "p6_ok" in r else "-"
        ident = "-" if "id_exact" not in r else ("ok" if r["id_exact"] else "WRONG")
        lp = "-" if r["avg_logprob"] is None else f"{r['avg_logprob']:.2f}"
        esc = lambda t: (t or "").replace("|", "/")
        out.append(f"| {r['id']} | {r['kind']} | {r['snr_db'] if r['snr_db'] is not None else '-'} | {esc(r['spoken'])} | "
                   f"{esc(r['raw'])} | {esc(r['sent'])} | {wer_n} | {ident} | {ans} | {lp} |")
    return "\n".join(out)


def _passes(r: dict) -> bool:
    """The pipeline's confidence gate, applied to a calibration row."""
    return r["avg_logprob"] is not None and r["avg_logprob"] >= settings.min_logprob and r["no_speech_prob"] <= settings.max_no_speech


def calibration_table(stt: dict) -> str:
    cal = stt.get("calibration") or []
    if not cal:
        return "_No calibration rows._"
    intro = ("Extra noisy copies of the four yes/no clips (not part of the 30). The gate blocks a spoken answer while an action "
             f"is pending when avg logprob is below {settings.min_logprob} or no-speech probability is above {settings.max_no_speech}.")
    out = [intro, "", "| Clip | SNR dB | Heard | Right answer | avg logprob | no-speech | Gate |", "|---|---|---|---|---|---|---|"]
    for r in cal:
        passes = _passes(r)
        out.append(f"| {r['id']} ({r['kind']}) | {r['snr_db']} | {r['raw'].replace('|', '/')} | {'yes' if r['polarity_ok'] else 'NO'} | "
                   f"{'-' if r['avg_logprob'] is None else format(r['avg_logprob'], '.2f')} | {r['no_speech_prob']:.2f} | "
                   f"{'passes' if passes else 'blocked'} |")
    wrong_pass = sum((not r["polarity_ok"]) and _passes(r) for r in cal)
    right_block = sum(r["polarity_ok"] and not _passes(r) for r in cal)
    out += ["", (f"Wrong answers that passed the gate: {wrong_pass} of {len(cal)}. Right answers blocked: {right_block} of "
                 f"{len(cal)}. Twelve clips is a small sample: the thresholds are a starting point to re-tune on own-voice clips.")]
    return "\n".join(out)


def run1_note() -> str:
    """Run 1 (kept in e2e-run1.json) failed on test data that did not match the orders: say so wherever results show."""
    run1 = load("e2e-run1.json")
    if not run1:
        return "No earlier e2e run kept."
    s = run1["summary"].get("synthetic", {})
    return (f"Run 1 ({run1['date']}, kept as `evals/results/e2e-run1.json`): typed {s.get('typed_ok')}/{s.get('n')}, voiced "
            f"{s.get('voiced_ok')}/{s.get('n')}, all three voice scenarios failed. All six failures were bad test data, not code: the "
            "return clips named an item the order did not hold (a kettle from an order of coffee beans, beans from an order of a scale "
            "and glassware) or an order that was not delivered. Project 1's refusals (for example \"there is no kettle in this order\") "
            "were the correct behaviour. The clips were then changed to match project 1's order data (see the manifest notes).")


def answers_section(stt: dict) -> str:
    rows = stt.get("answers_text") or []
    if not rows:
        return "_No answer rows._"
    intro = ("Text-only hard negatives: a yes or no word followed by a negation, delay, laugh or goodbye. "
             "A careful reader returns nothing (an unclear answer), never yes.")
    out = [intro, "", "| Phrase | P6 strict reader | P1 `_typed_answer` |", "|---|---|---|"]
    for r in rows:
        out.append(f"| {r['phrase']} | {r['p6'] or 'not an answer'} | {r['p1'] or 'not an answer'} |")
    out += ["", f"P1 reader: {stt.get('p1_reader', 'unknown')} (loaded read-only from the project 1 agent file, only in the eval)."]
    return "\n".join(out)


def e2e_section(e2e: dict | None) -> str:
    if not e2e:
        return f"Status: {PENDING}.\n\nThe run scores the typed text and the voiced clip each against the manifest label (tool name plus order id), " \
               "checks that silent clips make no P1 call, and runs one return confirmed by voice and one cancelled by voice."
    heading = "RUN 1, NOT A RESULT (test data did not match the orders). " if is_run1(e2e) else ""
    out = [f"{heading}Run {e2e['date']} against {e2e['agent_url']} (STT language `{e2e['stt_language']}`, {e2e['elapsed_s']} s).", "",
           run1_note(), "",
           f"Database precondition: {e2e.get('precondition', 'not recorded')}", "",
           "| Clip | Label | Typed ok | Voiced ok | Voiced transcript | Voiced tools | Agent ms (voiced) |", "|---|---|---|---|---|---|---|"]
    for r in e2e["rows"]:
        label = f"{r['expected_tool'] or 'no tool'} {r['expected_order_id'] or ''}".strip()
        v = r["voiced"]
        out.append(f"| {r['id']} ({r['source']}) | {label} | {r['typed'].get('ok')} | {v.get('ok')} | {(v.get('transcript') or '').replace('|', '/')} | "
                   f"{', '.join(v.get('tools') or [])} | {(v.get('timings') or {}).get('agent_ms', '-')} |")
    out += ["", "| Source | Clips | Typed correct | Voiced correct | Order-id clips typed / voiced | Voiced calls on a different order id |", "|---|---|---|---|---|---|"]
    for source, s in e2e["summary"].items():
        out.append(f"| {source} | {s['n']} | {frac(s['typed_ok'], s['n'])} | {frac(s['voiced_ok'], s['n'])} | "
                   f"{s['id_typed_ok']}/{s['id_n']} / {s['id_voiced_ok']}/{s['id_n']} | {s['wrong_order_voiced']} |")
    out += ["", "| Source | create_ticket clips | Real ticket call, typed | Real ticket call, voiced | Hand-off with no ticket, typed | Hand-off with no ticket, voiced |", "|---|---|---|---|---|---|"]
    for source, s in e2e["summary"].items():
        out.append(f"| {source} | {s['ticket_n']} | {s['ticket_typed_ok']} | {s['ticket_voiced_ok']} | {s['handoff_only_typed']} | {s['handoff_only_voiced']} |")
    out += ["", "Typed accuracy is the ceiling; the gap to voiced is the cost of voice. P1 is not deterministic, so single runs differ by a case or two.", "",
            "| Quiet clip | Status | Heard | P1 calls | Pass |", "|---|---|---|---|---|"]
    for s in e2e.get("silent", []):
        out.append(f"| {s['id']} ({s['kind']}) | {s['status']} | {s['transcript_raw'] or '-'} | {s['agent_calls']} | {s['ok']} |")
    out += ["", "| Scenario | Expect | Request clip (order) | Answer clip | Answer heard | Pending after request | Executed | Pass |", "|---|---|---|---|---|---|---|---|"]
    for sc in e2e.get("scenarios", []):
        out.append(f"| {sc['name']} | {sc.get('expect', '-')} | {sc.get('request_clip', '-')} ({sc.get('request_order') or '-'}) | "
                   f"{sc.get('answer_clip', '-')} | {(sc.get('answer_transcript') or '-').replace('|', '/')} | "
                   f"{sc.get('pending_after_request', '-')} | {', '.join(sc.get('executed', [])) or 'none'} | "
                   f"{sc.get('ok')}{'' if sc.get('ok') else ' ' + str(sc.get('reason', ''))} |")
    return "\n".join(out)


def latency_section(stt: dict, e2e: dict | None) -> str:
    lang = pick_default(stt)
    s = stt["runs"][lang]["summary"]["synthetic"]
    t = stt["tts"]
    out = ["| Stage | p50 | p95 | Note |", "|---|---|---|---|",
           f"| STT (`{lang}`, small int8, CPU) | {sec(s['stt_ms_p50'])} | {sec(s['stt_ms_p95'])} | real-time factor {s['stt_rtf']:.2f} (decode, VAD and decode included) |",
           f"| TTS (piper, CPU) | {sec(t['ms_p50'])} | {sec(t['ms_p95'])} | {t['n']} sample replies, real-time factor {t['rtf_p50']:.3f} |"]
    if e2e:
        from evals.common import percentile
        ms = [m for s_ in e2e["summary"].values() for m in s_["agent_ms_voiced"] if m]
        if ms:
            out.append(f"| Agent (P1, GPU) | {sec(percentile(ms, 50))} | {sec(percentile(ms, 95))} | measured in the end-to-end run |")
    else:
        out.append("| Agent (P1, GPU) | pending | pending | measured by the orchestrator's end-to-end run |")
    return "\n".join(out)


def render() -> tuple[str, str]:
    stt, e2e = load("stt.json"), load("e2e.json")
    table = numbers_table(stt, e2e)
    if not stt:
        return "# Voice intake eval report\n\n" + table + "\n", table
    report = f"""# Voice intake eval report

STT run {stt['date']} ({stt['elapsed_s']} s). All speech models run on CPU. Fictional customer, synthetic clips.

## Numbers

{table}

## STT language setting: en vs auto (synthetic clips)

{language_table(stt)}

## Latency

{latency_section(stt, e2e)}

## Per-clip transcripts (synthetic clips)

{clip_table(stt)}

## Yes/no readers

{answers_section(stt)}

## Confidence gate calibration

{calibration_table(stt)}

## End-to-end against the support agent

{e2e_section(e2e)}

## How to read this

- Synthetic clips are piper speech read back by Whisper. They test the pipeline (decoding, normalisation, id handling, silence) and are optimistic for accuracy.
- The headline WER compares Whisper's own text with the typed reference after standard text normalisation (case, punctuation, hyphens, digits read as words). The secondary WER collapses order ids and numbers on both sides against the spoken-form reference: it is lower, but it also forgives formatting, so it is not the headline. The order-id columns are scored against the manifest label, not against the normaliser.
- Quiet clips are silence, room noise, and three non-speech sounds a voice-activity filter can let through (laughter-like bursts, reversed-speech babble, keyboard clicks). Passing means no text, so no agent call.
- Own-voice rows stay empty until `python -m evals.record` and the `--own` runs have been done.
"""
    return report, table


def patch_readme(table: str) -> bool:
    if not README.exists():
        return False
    text = README.read_text(encoding="utf-8")
    if START not in text or END not in text:
        return False
    new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: f"{START}\n{table}\n{END}", text, flags=re.DOTALL)
    README.write_text(new, encoding="utf-8")
    return True


def main() -> None:
    report, table = render()
    (EVALS / "report.md").write_text(report, encoding="utf-8")
    print(f"wrote {EVALS / 'report.md'}; README table updated: {patch_readme(table)}")


if __name__ == "__main__":
    main()

