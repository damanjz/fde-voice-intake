"""Synthesise the synthetic test clips with piper (CPU) and write evals/manifest.json.

    python -m evals.make_clips                      # every clip (piper is stochastic: all audio changes)
    python -m evals.make_clips --only S14,S15,S16,S37   # only these; every other wav is kept as it is
"""

from __future__ import annotations

import argparse
import json
import zlib

import numpy as np

from app.tts import Synthesizer
from evals import clips
from evals.common import AUDIO_DIR, MANIFEST, add_noise, array_to_wav, room_noise, wav_to_array

PAD_S = 0.35  # lead-in and tail silence, like a real hold-to-talk recording


def laughter(rng: np.random.Generator, rate: int = 16000, seconds: float = 3.0) -> np.ndarray:
    """Laughter-like: five voiced "ha" bursts at about 5 per second, each a harmonic buzz with breath noise."""
    out = np.zeros(int(rate * seconds), dtype=np.float32)
    for k in range(5):
        start = int(rate * (0.3 + 0.2 * k))
        n = int(rate * 0.14)
        t = np.arange(n) / rate
        f0 = 240 + 25 * rng.standard_normal() + 20 * np.sin(2 * np.pi * 6 * t)
        phase = 2 * np.pi * np.cumsum(f0) / rate
        buzz = sum(np.sin(h * phase) / h for h in range(1, 9))
        burst = (buzz + 0.15 * rng.standard_normal(n)) * np.hanning(n) * (0.9 - 0.12 * k)
        out[start : start + n] += burst.astype(np.float32)
    return out * 10 ** (-18 / 20) / (np.max(np.abs(out)) or 1.0)


def babble(tts: Synthesizer, rng: np.random.Generator, rate: int = 16000, seconds: float = 4.0) -> np.ndarray:
    """Unintelligible speech-like noise: four reversed piper utterances overlapped at different offsets."""
    texts = ["Where is my order and when will it arrive", "I would like to return the grinder please",
             "Do you have the pour over dripper in stock", "How long is the warranty on the kettle"]
    out = np.zeros(int(rate * seconds), dtype=np.float32)
    for i, text in enumerate(texts):
        speech, src_rate = wav_to_array(tts.synthesize(text, 1.0 + 0.05 * i).wav)
        idx = np.linspace(0, len(speech) - 1, int(len(speech) * rate / src_rate))
        voice = np.interp(idx, np.arange(len(speech)), speech)[::-1].astype(np.float32)
        start = int(rate * 0.3 * i)
        piece = voice[: len(out) - start]
        out[start : start + len(piece)] += piece
    return out * 10 ** (-20 / 20) / (np.max(np.abs(out)) or 1.0)


def keyboard(rng: np.random.Generator, rate: int = 16000, seconds: float = 4.0) -> np.ndarray:
    """Typing: about 9 key clicks a second, each a few milliseconds of decaying noise, over faint room noise."""
    out = (room_noise(int(rate * seconds), rng) * 10 ** (-52 / 20)).astype(np.float32)
    t = 0.2
    while t < seconds - 0.1:
        n = int(rate * 0.012)
        click = rng.standard_normal(n) * np.exp(-np.arange(n) / (rate * 0.003)) * rng.uniform(0.15, 0.5)
        start = int(rate * t)
        out[start : start + n] += click.astype(np.float32)
        t += rng.uniform(0.06, 0.18)
    return out


def main() -> None:
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="", help="comma list of clip ids to regenerate; the others keep their audio")
    only = {x.strip() for x in ap.parse_args().only.split(",") if x.strip()}
    tts = Synthesizer()
    manifest = clips.build()
    kept = {c["id"]: c for c in json.loads(MANIFEST.read_text(encoding="utf-8"))} if only and MANIFEST.exists() else {}
    for clip in manifest:
        if only and clip["id"] not in only:
            if clip["id"] not in kept or not (AUDIO_DIR / clip["file"]).exists():
                raise SystemExit(f"{clip['id']} has no audio yet: run without --only first")
            clip["audio_seconds"] = kept[clip["id"]]["audio_seconds"]
            continue
        rng = np.random.default_rng(zlib.crc32(clip["id"].encode()))
        if clip["kind"] in ("silent", "noise", "nonspeech"):
            n = 16000 * 3
            if clip["kind"] == "nonspeech":
                if clip["group"] == "laughter":
                    samples = laughter(rng)
                elif clip["group"] == "babble":
                    samples = babble(tts, rng)
                else:
                    samples = keyboard(rng)
                samples = samples + (room_noise(len(samples), rng) * 10 ** (-55 / 20)).astype(np.float32)
                n = len(samples)
            elif clip["kind"] == "silent":
                samples = rng.standard_normal(n).astype(np.float32) * 10 ** (-70 / 20)  # near digital silence
            else:
                samples = room_noise(n, rng).astype(np.float32) * 10 ** (-32 / 20)  # room hum, no speech
            wav, rate = array_to_wav(samples, 16000), 16000
            seconds = len(samples) / 16000
        else:
            speech, rate = wav_to_array(tts.synthesize(clip["spoken"], clip["length_scale"]).wav)
            pad = np.zeros(int(rate * PAD_S), dtype=np.float32)
            samples = np.concatenate([pad, speech, pad])
            if clip["snr_db"] is not None:
                samples = add_noise(samples, clip["snr_db"], rng)
            peak = float(np.max(np.abs(samples))) or 1.0
            samples = samples * min(1.0, 0.9 / peak)
            wav, seconds = array_to_wav(samples, rate), len(samples) / rate
        (AUDIO_DIR / clip["file"]).write_bytes(wav)
        clip["audio_seconds"] = round(seconds, 2)
        print(f"{clip['id']} {clip['kind']:6} {seconds:5.1f}s snr={clip['snr_db']} {clip['spoken'][:60]}")
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest)} clips to {AUDIO_DIR} and {MANIFEST}")


if __name__ == "__main__":
    main()
