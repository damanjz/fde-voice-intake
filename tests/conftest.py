"""Shared fakes: no models, no network. The agent API is mocked with httpx.MockTransport."""

from __future__ import annotations

import io
import json
import wave

import httpx
import pytest

from app.agent_client import AgentClient
from app.config import Settings
from app.pipeline import VoicePipeline
from app.stt import SttResult
from app.tts import TtsResult


def tiny_wav(seconds: float = 0.2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def stt_result(text: str, logprob: float | None = -0.2, no_speech: float = 0.05) -> SttResult:
    if not text:
        logprob, no_speech = None, 1.0
    return SttResult(text, "en", 1.0, 2.0, logprob, no_speech, 400.0, 20.0, 0.0)


class FakeStt:
    """Returns queued transcripts in order."""

    def __init__(self, *results: SttResult) -> None:
        self.queue = list(results)
        self._model = object()
        self.calls = 0

    def load(self):
        return self._model

    def transcribe(self, data, language=None) -> SttResult:
        self.calls += 1
        return self.queue.pop(0)


class FakeTts:
    def __init__(self) -> None:
        self._voice = object()
        self.spoken: list[str] = []

    def load(self):
        return self._voice

    def synthesize(self, text: str, length_scale=None) -> TtsResult:
        self.spoken.append(text)
        return TtsResult(tiny_wav(), 0.2, 50.0)


class FakeAgent:
    """Mocked P1 /chat. `replies` are returned in order; `fail` makes every call raise a connection error."""

    def __init__(self, *replies: dict, fail: bool = False) -> None:
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.fail = fail

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/health":
                return httpx.Response(200, json={"status": "ok"})
            self.requests.append(json.loads(request.content))
            if self.fail:
                raise httpx.ConnectError("down", request=request)
            return httpx.Response(200, json=self.replies.pop(0))

        self.client = AgentClient(Settings(), httpx.Client(transport=httpx.MockTransport(handler)))


def agent_reply(text: str, pending: dict | None = None, **kw) -> dict:
    return {"text": text, "citations": kw.get("citations", []), "tool_calls": kw.get("tool_calls", []),
            "pending_action": pending, "escalated": kw.get("escalated", False), "usage": {}}


@pytest.fixture
def make_pipeline():
    def build(stt: FakeStt, agent: FakeAgent, cfg: Settings | None = None):
        tts = FakeTts()
        return VoicePipeline(stt=stt, tts=tts, agent=agent.client, cfg=cfg or Settings()), tts

    return build
