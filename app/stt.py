"""Speech to text: faster-whisper `small`, int8 on CPU, bundled PyAV decoder (no system ffmpeg)."""

from __future__ import annotations

import io
import threading
import time
from dataclasses import dataclass

import numpy as np

from app.config import Settings, settings

SAMPLE_RATE = 16000
MIN_AUDIO_SECONDS = 0.3

# Biases the decoder toward Larkfield words. Roman Hinglish in the Hindi prompt keeps output in Roman script.
PROMPT_EN = (
    "Larkfield Coffee Co. customer support call. Order ids look like LC-1150, LC-1015, LC-1200. "
    "Products: Hand Burr Grinder, Electric Burr Grinder, Espresso Grinder, Pour-Over Dripper, French Press, "
    "Moka Pot, kettle, coffee beans. Words: return, refund, warranty, subscription, ticket, BlueDart."
)
PROMPT_HI = (
    "Larkfield Coffee Co. support. Mera order LC-1150 abhi tak nahi aaya, kahan hai? "
    "Grinder kharab hai, return karna hai. Haan, bana do. Nahi, cancel karo."
)


class AudioError(ValueError):
    """The upload could not be decoded as audio."""


@dataclass
class SttResult:
    text: str
    language: str
    language_probability: float
    audio_seconds: float
    avg_logprob: float | None  # duration-weighted over kept segments; None when no speech
    no_speech_prob: float  # highest over segments (1.0 when nothing was kept)
    ms: float
    decode_ms: float
    detect_ms: float


# Containers a browser or a phone adapter can send. PyAV probes many formats; anything else is refused.
ALLOWED_CONTAINERS = {"wav", "matroska", "webm", "ogg", "mov", "mp4", "m4a"}


def decode_bytes(data: bytes, max_seconds: float | None = None) -> np.ndarray:
    """Decode wav, webm/opus, ogg or mp4 bytes to 16 kHz mono float32 with PyAV (bundled ffmpeg libraries).

    Only whitelisted containers are accepted, and decoding stops as soon as the audio runs past max_seconds
    (default: settings.max_audio_seconds), so a small compressed upload cannot expand into a huge array.
    faster-whisper's own decode_audio passes an option that PyAV 19 rejects, so the same few lines live here.
    """
    import av

    limit = int((max_seconds if max_seconds is not None else settings.max_audio_seconds) * SAMPLE_RATE)
    parts: list[np.ndarray] = []
    total = 0
    try:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
        with av.open(io.BytesIO(data), mode="r") as container:
            names = set(container.format.name.split(","))
            if not names & ALLOWED_CONTAINERS:
                raise AudioError(f"unsupported audio container: {container.format.name}")
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    chunk = out.to_ndarray().reshape(-1)
                    total += len(chunk)
                    if total > limit:
                        raise AudioError(f"audio is longer than {limit / SAMPLE_RATE:.0f}s")
                    parts.append(chunk)
        for out in resampler.resample(None):
            parts.append(out.to_ndarray().reshape(-1))
    except AudioError:
        raise
    except Exception as exc:
        raise AudioError(f"could not decode audio: {exc}") from exc
    if not parts:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(parts).astype(np.float32) / 32768.0


class Transcriber:
    def __init__(self, cfg: Settings = settings) -> None:
        self.cfg = cfg
        self._model = None
        self._lock = threading.Lock()

    def load(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.cfg.whisper_dir, device="cpu", compute_type="int8", cpu_threads=self.cfg.stt_threads
            )
        return self._model

    def _choose_language(self, model, audio: np.ndarray, language: str) -> tuple[str, float]:
        if language != "auto":
            return language, 1.0
        _, _, probs = model.detect_language(audio)
        p = dict(probs)
        en, hi = p.get("en", 0.0), p.get("hi", 0.0)
        total = (en + hi) or 1.0
        return ("hi", hi / total) if hi > en else ("en", en / total)

    def transcribe(
        self, data: bytes | np.ndarray, language: str | None = None, use_prompt: bool = True
    ) -> SttResult:
        language = language or self.cfg.stt_language
        t0 = time.perf_counter()
        audio = (
            decode_bytes(bytes(data), self.cfg.max_audio_seconds) if isinstance(data, (bytes, bytearray)) else data
        )
        decode_ms = (time.perf_counter() - t0) * 1000
        seconds = len(audio) / SAMPLE_RATE
        if seconds > self.cfg.max_audio_seconds:
            raise AudioError(f"audio is {seconds:.0f}s, the limit is {self.cfg.max_audio_seconds:.0f}s")
        if seconds < MIN_AUDIO_SECONDS:
            return SttResult("", language, 0.0, seconds, None, 1.0, decode_ms, decode_ms, 0.0)
        with self._lock:
            model = self.load()
            t1 = time.perf_counter()
            lang, lang_p = self._choose_language(model, audio, language)
            detect_ms = (time.perf_counter() - t1) * 1000
            segments, _info = model.transcribe(
                audio,
                language=lang,
                beam_size=self.cfg.stt_beam_size,
                initial_prompt=(PROMPT_HI if lang == "hi" else PROMPT_EN) if use_prompt else None,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
                condition_on_previous_text=False,
            )
            kept = []
            for seg in segments:
                # Whisper invents text on near-silence: drop segments it itself doubts.
                if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                    continue
                kept.append(seg)
        text = " ".join(s.text.strip() for s in kept).strip()
        ms = (time.perf_counter() - t0) * 1000
        if not kept or not text:
            return SttResult("", lang, lang_p, seconds, None, 1.0, decode_ms, detect_ms, ms)
        weights = [max(s.end - s.start, 0.01) for s in kept]
        avg_lp = sum(s.avg_logprob * w for s, w in zip(kept, weights)) / sum(weights)
        return SttResult(
            text, lang, lang_p, seconds, avg_lp, max(s.no_speech_prob for s in kept), ms, decode_ms, detect_ms
        )
