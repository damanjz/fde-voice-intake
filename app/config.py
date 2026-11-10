"""Settings read from environment variables (all optional)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Models live in ./models by default (a folder or a link to a shared models folder); FDE_MODELS_DIR overrides.
MODELS = os.environ.get("FDE_MODELS_DIR", str(Path(__file__).resolve().parents[1] / "models")).replace("\\", "/")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class Settings:
    agent_url: str = field(default_factory=lambda: _env("AGENT_URL", "http://localhost:8000"))
    agent_timeout_s: float = field(default_factory=lambda: float(_env("AGENT_TIMEOUT_S", "180")))
    whisper_dir: str = field(default_factory=lambda: _env("WHISPER_DIR", f"{MODELS}/whisper/small"))
    piper_voice: str = field(
        default_factory=lambda: _env("PIPER_VOICE", f"{MODELS}/piper/en_US-lessac-medium.onnx")
    )
    # "en" (default): force English, romanised Hinglish stays Roman. "auto": detect English vs Hindi only.
    stt_language: str = field(default_factory=lambda: _env("STT_LANGUAGE", "en"))
    stt_beam_size: int = field(default_factory=lambda: int(_env("STT_BEAM_SIZE", "5")))
    stt_threads: int = field(default_factory=lambda: int(_env("STT_THREADS", "8")))
    tts_length_scale: float = field(default_factory=lambda: float(_env("TTS_LENGTH_SCALE", "1.0")))
    # While an action is pending, a transcript below this confidence is not sent to the agent.
    min_logprob: float = field(default_factory=lambda: float(_env("STT_MIN_LOGPROB", "-0.8")))
    max_no_speech: float = field(default_factory=lambda: float(_env("STT_MAX_NO_SPEECH", "0.5")))
    # Any turn (pending or not) below this confidence is not sent: Whisper invents sentences from babble.
    reject_logprob: float = field(default_factory=lambda: float(_env("STT_REJECT_LOGPROB", "-0.9")))
    keep_audio_dir: str = field(default_factory=lambda: _env("VOICE_KEEP_AUDIO_DIR", ""))  # debug only
    port: int = 8200
    max_audio_seconds: float = 60.0
    max_upload_mb: int = 10


settings = Settings()
