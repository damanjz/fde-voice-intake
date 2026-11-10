"""Shared helpers for the eval scripts."""

from __future__ import annotations

import io
import json
import wave
from pathlib import Path

import numpy as np

EVALS = Path(__file__).resolve().parent
AUDIO_DIR = EVALS / "audio"
OWN_DIR = EVALS / "own"
RESULTS_DIR = EVALS / "results"
MANIFEST = EVALS / "manifest.json"
OWN_MANIFEST = OWN_DIR / "manifest.json"


def load_manifest(own: bool = False) -> list[dict]:
    path = OWN_MANIFEST if own else MANIFEST
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def clip_path(clip: dict) -> Path:
    return (OWN_DIR if clip.get("source") == "own" else AUDIO_DIR) / clip["file"]


def percentile(values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..100); 0.0 for an empty list."""
    if not values:
        return 0.0
    xs = sorted(values)
    pos = (len(xs) - 1) * q / 100
    lo, hi = int(pos), min(int(pos) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def wav_to_array(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as w:
        rate = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return samples, rate


def array_to_wav(samples: np.ndarray, rate: int) -> bytes:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def room_noise(n: int, rng: np.random.Generator) -> np.ndarray:
    """Low-passed gaussian noise: a rough stand-in for fan and street rumble, unit RMS."""
    white = rng.standard_normal(n + 64)
    kernel = np.hanning(33)
    kernel /= kernel.sum()
    low = np.convolve(white, kernel, mode="same")[32 : 32 + n]
    mixed = 0.7 * low / (low.std() or 1.0) + 0.3 * white[:n]
    return mixed / (mixed.std() or 1.0)


def add_noise(speech: np.ndarray, snr_db: float, rng: np.random.Generator) -> np.ndarray:
    rms = float(np.sqrt(np.mean(speech**2))) or 1e-4
    noise = room_noise(len(speech), rng) * rms / (10 ** (snr_db / 20))
    return speech + noise
