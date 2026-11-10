"""Text to speech: piper, one English voice, CPU."""

from __future__ import annotations

import io
import threading
import time
import wave
from dataclasses import dataclass

from app.config import Settings, settings


@dataclass
class TtsResult:
    wav: bytes
    audio_seconds: float
    ms: float


class Synthesizer:
    def __init__(self, cfg: Settings = settings) -> None:
        self.cfg = cfg
        self._voice = None
        self._lock = threading.Lock()

    def load(self):
        if self._voice is None:
            from piper import PiperVoice

            self._voice = PiperVoice.load(self.cfg.piper_voice)
        return self._voice

    def synthesize(self, text: str, length_scale: float | None = None) -> TtsResult:
        from piper import SynthesisConfig

        t0 = time.perf_counter()
        buf = io.BytesIO()
        with self._lock:
            voice = self.load()
            cfg = SynthesisConfig(length_scale=length_scale or self.cfg.tts_length_scale)
            with wave.open(buf, "wb") as w:
                voice.synthesize_wav(text, w, cfg)
        wav = buf.getvalue()
        with wave.open(io.BytesIO(wav), "rb") as r:
            seconds = r.getnframes() / r.getframerate()
        return TtsResult(wav, seconds, (time.perf_counter() - t0) * 1000)
