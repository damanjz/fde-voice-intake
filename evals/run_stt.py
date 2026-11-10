"""Speech-to-text and text-to-speech eval on the clips (CPU, no agent calls).

    python -m evals.run_stt                    # synthetic clips, language en and auto
    python -m evals.run_stt --own              # also the recorded own-voice clips (evals/own/)
    python -m evals.run_stt --languages en     # one setting only

Writes evals/results/stt.json. Render the report with `python -m evals.report`.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime

import numpy as np

from app.answer import classify
from app.config import settings
from app.normalize import prepare_transcript
from app.speakable import make_speakable
from app.stt import SAMPLE_RATE, Transcriber
from app.tts import Synthesizer
from app.wer import corpus_wer, wer
from evals.clips import HARD_NEGATIVE_PHRASES
from evals.common import EVALS, RESULTS_DIR, add_noise, clip_path, load_manifest, percentile, wav_to_array
from evals.p1_answer import load_typed_answer, p1_reads

CAL_SNRS = (5, 0, -5)  # extra noisy copies of the yes/no clips, only to calibrate the confidence gate
QUIET_KINDS = ("silent", "noise", "nonspeech")
P1_TYPED_ANSWER = load_typed_answer()  # None when project 1's file is not available


def score_clip(clip: dict, stt) -> dict:
    prepared = prepare_transcript(stt.text)
    spoken, typed = clip["spoken"], clip["typed"]
    row = {
        "id": clip["id"], "source": clip.get("source", "synthetic"), "kind": clip["kind"],
        "group": clip.get("group"), "snr_db": clip.get("snr_db"),
        "spoken": spoken, "typed": typed, "raw": stt.text, "sent": prepared.text,
        "order_ids": prepared.order_ids, "raw_ids": re.findall(r"\bLC-\d{4}\b", stt.text), "suspect_ids": prepared.suspect_ids,
        "language": stt.language, "avg_logprob": stt.avg_logprob, "no_speech_prob": stt.no_speech_prob,
        "audio_seconds": round(stt.audio_seconds, 2), "stt_ms": round(stt.ms), "detect_ms": round(stt.detect_ms),
    }
    if clip["kind"] in QUIET_KINDS:
        row["no_text"] = not prepared.text.strip()
        # what the pipeline does: no text, or Whisper's own score too low, means no agent call
        row["blocked"] = row["no_text"] or (stt.avg_logprob is not None and stt.avg_logprob < settings.reject_logprob)
        return row
    # headline: Whisper's own text against the typed reference, standard text normalisation (case, punctuation)
    row["wer_typed"] = wer(typed, stt.text, normalise_ids=False)
    row["wer_raw"] = wer(spoken, stt.text, normalise_ids=False)  # against the spoken words: informational
    row["wer_norm"] = wer(spoken, prepared.text, normalise_ids=True)  # ids and numbers collapsed: secondary
    expected = clip.get("expected_order_id")
    if expected:
        row["id_exact"] = prepared.order_ids == [expected]
        row["id_raw_exact"] = row["raw_ids"] == [expected]  # Whisper's own text, before our normaliser
    if clip["kind"] in ("yes", "no", "hardneg"):
        want = clip["kind"] if clip["kind"] != "hardneg" else None  # a hard negative must not be read as any answer
        row["p6_answer"] = classify(prepared.text)
        row["p6_ok"] = row["p6_answer"] == want
        if P1_TYPED_ANSWER:
            row["p1_answer"] = p1_reads(prepared.text, P1_TYPED_ANSWER)
            row["p1_ok"] = row["p1_answer"] == want
    return row


def summarize(rows: list[dict]) -> dict:
    speech = [r for r in rows if "wer_norm" in r]
    with_id = [r for r in rows if "id_exact" in r]
    quiet = [r for r in rows if "no_text" in r]
    yn = [r for r in rows if r["kind"] in ("yes", "no") and "p6_ok" in r]
    hard = [r for r in rows if r["kind"] == "hardneg" and "p6_ok" in r]
    stt_ms = [r["stt_ms"] for r in rows if r["audio_seconds"] > 0.3]
    secs = [r["audio_seconds"] for r in rows if r["audio_seconds"] > 0.3]
    return {
        "clips": len(rows),
        "wer_typed": corpus_wer([(r["typed"], r["raw"]) for r in speech], False) if speech else None,
        "wer_raw": corpus_wer([(r["spoken"], r["raw"]) for r in speech], False) if speech else None,
        "wer_norm": corpus_wer([(r["spoken"], r["sent"]) for r in speech], True) if speech else None,
        "id_exact": sum(r["id_exact"] for r in with_id), "id_total": len(with_id),
        "id_raw_exact": sum(r["id_raw_exact"] for r in with_id),
        "yn_ok": sum(r["p6_ok"] for r in yn), "yn_total": len(yn),
        "yn_ok_p1": sum(r.get("p1_ok", False) for r in yn) if P1_TYPED_ANSWER else None,
        "hardneg_ok": sum(r["p6_ok"] for r in hard), "hardneg_total": len(hard),
        "hardneg_ok_p1": sum(r.get("p1_ok", False) for r in hard) if P1_TYPED_ANSWER else None,
        "quiet_ok": sum(r["no_text"] for r in quiet), "quiet_total": len(quiet),
        "quiet_blocked": sum(r["blocked"] for r in quiet),
        "stt_ms_p50": percentile(stt_ms, 50), "stt_ms_p95": percentile(stt_ms, 95),
        "stt_rtf": (sum(stt_ms) / 1000) / sum(secs) if secs else None,
    }


def answers_text() -> list[dict]:
    """Hard-negative phrases (no audio) through both readers: P6's strict one and P1's `_typed_answer`."""
    return [{"phrase": p, "p6": classify(p), "p1": p1_reads(p, P1_TYPED_ANSWER) if P1_TYPED_ANSWER else "n/a"}
            for p in HARD_NEGATIVE_PHRASES]


def run_language(clips: list[dict], setting: str) -> dict:
    """setting: en | auto | en-noprompt (no Larkfield prompt: shows what the normaliser alone recovers)."""
    language, _, variant = setting.partition("-")
    use_prompt = variant != "noprompt"
    stt = Transcriber()
    stt.load()
    stt.transcribe(np.zeros(16000, dtype=np.float32), language="en")  # warm-up, not measured
    rows = []
    for clip in clips:
        data = clip_path(clip).read_bytes()
        rows.append(score_clip(clip, stt.transcribe(data, language=language, use_prompt=use_prompt)))
        r = rows[-1]
        print(f"[{setting}] {r['id']:4} {r['stt_ms']:5d} ms  {r['raw']!r} -> {r['sent']!r}", flush=True)
    out = {"rows": rows, "summary": {}}
    for source in sorted({r["source"] for r in rows}):
        out["summary"][source] = summarize([r for r in rows if r["source"] == source])
    return out


def calibrate(clips: list[dict]) -> list[dict]:
    """Noisy copies of the yes/no clips: what the confidence numbers look like when audio is poor."""
    stt = Transcriber()
    stt.load()
    rows = []
    for clip in clips:
        if clip["kind"] not in ("yes", "no") or clip.get("source") == "own":
            continue
        speech, rate = wav_to_array(clip_path(clip).read_bytes())
        for snr in CAL_SNRS:
            rng = np.random.default_rng(1000 + int(clip["id"][1:]) * 10 + snr + 10)
            noisy = add_noise(speech, snr, rng)
            noisy = noisy * min(1.0, 0.9 / (float(np.max(np.abs(noisy))) or 1.0))
            idx = np.linspace(0, len(noisy) - 1, int(len(noisy) * SAMPLE_RATE / rate))
            audio16 = np.interp(idx, np.arange(len(noisy)), noisy).astype(np.float32)
            res = stt.transcribe(audio16, language="en")
            rows.append({"id": clip["id"], "kind": clip["kind"], "snr_db": snr, "raw": res.text,
                         "avg_logprob": res.avg_logprob, "no_speech_prob": res.no_speech_prob,
                         "polarity_ok": classify(res.text) == clip["kind"]})
            print(f"[cal] {clip['id']} snr={snr:3d} {res.text!r} lp={res.avg_logprob} ns={res.no_speech_prob:.2f}", flush=True)
    return rows


def tts_latency() -> dict:
    replies = json.loads((EVALS / "replies.json").read_text(encoding="utf-8"))
    tts = Synthesizer()
    tts.load()
    tts.synthesize("Warm up.")
    ms, rtf, rows = [], [], []
    for text in replies:
        spoken = make_speakable(text)
        t = tts.synthesize(spoken)
        ms.append(t.ms)
        rtf.append(t.ms / 1000 / t.audio_seconds)
        rows.append({"chars": len(spoken), "audio_seconds": round(t.audio_seconds, 2), "ms": round(t.ms)})
    return {"n": len(ms), "ms_p50": percentile(ms, 50), "ms_p95": percentile(ms, 95),
            "rtf_p50": percentile(rtf, 50), "rows": rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--own", action="store_true", help="include recorded own-voice clips")
    ap.add_argument("--languages", default="en,auto,en-noprompt", help="comma list of: en, auto, en-noprompt")
    args = ap.parse_args()
    clips = load_manifest()
    if args.own:
        clips += load_manifest(own=True)
    if not clips:
        raise SystemExit("no clips: run `python -m evals.make_clips` first")
    started = time.time()
    result = {"date": datetime.now().isoformat(timespec="seconds"), "runs": {}}
    for lang in args.languages.split(","):
        result["runs"][lang] = run_language(clips, lang)
    result["calibration"] = calibrate(clips)
    result["answers_text"] = answers_text()
    result["p1_reader"] = "available" if P1_TYPED_ANSWER else "not available"
    result["tts"] = tts_latency()
    result["elapsed_s"] = round(time.time() - started)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "stt.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    for lang, run in result["runs"].items():
        print(lang, json.dumps(run["summary"], indent=1))
    print("tts", {k: v for k, v in result["tts"].items() if k != "rows"})


if __name__ == "__main__":
    main()
