"""One voice turn: audio -> STT -> normalise -> agent -> speakable -> TTS, with per-stage timings.

Safety rules that live here (project 1 holds the real pending action, per session):
- silence, fillers-only and unclear audio are never sent to the agent;
- while an action may be pending, only a confident, whole-utterance yes or no is passed on, as confirm=true or
  confirm=false; anything else is not sent and the customer is asked to say yes or no or press a button;
- if the pending state is unknown (this service restarted, or the agent timed out), it is treated as pending;
- a /chat call is never retried automatically.
"""

from __future__ import annotations

import base64
import re
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from app.agent_client import AgentClient, AgentUnavailable
from app.answer import classify
from app.config import Settings, settings
from app.normalize import prepare_transcript
from app.speakable import make_speakable, speak_pending
from app.stt import SttResult, Transcriber
from app.tts import Synthesizer

FALLBACK_TEXT = "I can't reach support right now, please try again."
CONFIRM_UNKNOWN_TEXT = (
    "I couldn't check whether that went through. Please don't repeat it yet: "
    "ask for your order status, or check your email, before trying again."
)
NO_SPEECH_TEXT = "I didn't catch that. Please try again."
LOW_CONFIDENCE_TEXT = "I wasn't sure what you said. Please say yes or no again, or press Confirm or Cancel."
NOT_SURE_TEXT = "I wasn't sure what you said. Please say it again."
UNCLEAR_TEXT = "Please say yes or no, or press Confirm or Cancel."
SESSION_PREFIX = "voice-"
MAX_SESSIONS = 2000
_SESSION_OK = re.compile(r"^voice-[A-Za-z0-9_-]{1,64}$")
_ASKS_ID = re.compile(r"\border (?:id|number)\b", re.IGNORECASE)
_ASK_CUE = re.compile(r"\?|\b(?:please )?(?:provide|share|give|tell|send|confirm)\b|\bwhat(?:'s| is)\b", re.IGNORECASE)


def clean_session_id(raw: str | None) -> str:
    """Session ids always start with 'voice-' so they never collide with the typed chat page."""
    if raw and _SESSION_OK.match(raw):
        return raw
    if raw:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", raw)[:64]
        if safe:
            return SESSION_PREFIX + safe.removeprefix(SESSION_PREFIX)
    return SESSION_PREFIX + uuid.uuid4().hex[:12]


def asks_for_order_id(reply_text: str) -> bool:
    """Did the agent's reply ask the customer for an order id?"""
    return bool(_ASKS_ID.search(reply_text or "") and _ASK_CUE.search(reply_text or ""))


def confident(stt: SttResult, cfg: Settings) -> bool:
    return (
        stt.avg_logprob is not None
        and stt.avg_logprob >= cfg.min_logprob
        and stt.no_speech_prob <= cfg.max_no_speech
    )


@dataclass
class _State:
    pending: bool = False
    asked_id: bool = False


@dataclass
class TurnResult:
    status: str  # ok | no_speech | low_confidence | unclear_answer | agent_unavailable
    session_id: str
    transcript_raw: str = ""
    transcript: str = ""
    language: str = ""
    order_ids: list[str] = field(default_factory=list)
    suspect_ids: list[str] = field(default_factory=list)
    stt_confidence: dict = field(default_factory=dict)
    reply_text: str = ""
    spoken_text: str = ""
    citations: list[str] = field(default_factory=list)
    pending: bool = False  # an action may be waiting for yes or no (the page keeps its card)
    pending_action: dict | None = None
    escalated: bool = False
    tool_calls: list[dict] = field(default_factory=list)
    timings: dict = field(default_factory=dict)
    audio_seconds: float = 0.0
    audio_wav_base64: str = ""

    def to_dict(self) -> dict:
        return self.__dict__.copy()


class VoicePipeline:
    def __init__(
        self,
        stt: Transcriber | None = None,
        tts: Synthesizer | None = None,
        agent: AgentClient | None = None,
        cfg: Settings = settings,
    ) -> None:
        self.cfg = cfg
        self.stt = stt or Transcriber(cfg)
        self.tts = tts or Synthesizer(cfg)
        self.agent = agent or AgentClient(cfg)
        self._sessions: OrderedDict[str, _State] = OrderedDict()  # LRU by last use
        self._lock = threading.Lock()

    def preload(self) -> None:
        self.stt.load()
        self.tts.load()

    # ---- session state

    def _state(self, session_id: str, create: bool = False) -> _State | None:
        with self._lock:
            st = self._sessions.get(session_id)
            if st is None and create:
                st = self._sessions[session_id] = _State()
            if st is not None:
                self._sessions.move_to_end(session_id)
            while len(self._sessions) > MAX_SESSIONS:
                self._sessions.popitem(last=False)  # least recently used
            return st

    def has_pending(self, session_id: str, prior_turns: int = 0) -> bool:
        """Is an action possibly waiting? Fail safe: a session this service has never seen, but the page says
        already had turns (this service restarted, or the state was evicted), counts as pending."""
        st = self._state(session_id)
        if st is None:
            return prior_turns > 0
        return st.pending

    def _asked_id(self, session_id: str) -> bool:
        st = self._state(session_id)
        return bool(st and st.asked_id)

    # ---- speaking

    def _speak(self, result: TurnResult, text: str, spoken: str | None, t_start: float) -> TurnResult:
        result.reply_text = text
        result.spoken_text = spoken if spoken is not None else make_speakable(text)
        speech = self.tts.synthesize(result.spoken_text)
        result.audio_seconds = speech.audio_seconds
        result.audio_wav_base64 = base64.b64encode(speech.wav).decode("ascii")
        result.timings["tts_ms"] = round(speech.ms)
        result.timings["total_ms"] = round((time.perf_counter() - t_start) * 1000)
        return result

    def _finish(self, result: TurnResult, text: str, t_start: float, prior_turns: int = 0) -> TurnResult:
        result.pending = bool(result.pending_action) or self.has_pending(result.session_id, prior_turns)
        spoken = speak_pending(result.pending_action, text) if result.pending_action else None
        return self._speak(result, text, spoken, t_start)

    # ---- agent

    def _ask_agent(self, result: TurnResult, message: str, confirm: bool | None) -> None:
        t0 = time.perf_counter()
        st = self._state(result.session_id, create=True)
        try:
            reply = self.agent.chat(result.session_id, message, confirm)
        except AgentUnavailable:
            result.status = "agent_unavailable"
            result.reply_text = CONFIRM_UNKNOWN_TEXT if confirm is not None else FALLBACK_TEXT
            result.timings["agent_ms"] = round((time.perf_counter() - t0) * 1000)
            with self._lock:
                st.pending = True  # a timed-out call may have left an action waiting, or run it: fail safe
            return
        result.timings["agent_ms"] = round((time.perf_counter() - t0) * 1000)
        result.reply_text = reply["text"]
        result.citations = list(reply.get("citations") or [])
        result.pending_action = reply.get("pending_action")
        result.escalated = bool(reply.get("escalated"))
        result.tool_calls = list(reply.get("tool_calls") or [])
        with self._lock:
            st.pending = bool(result.pending_action)
            st.asked_id = asks_for_order_id(result.reply_text)

    # ---- turns

    def press_button(self, session_id: str | None, confirm: bool) -> TurnResult:
        """Confirm or Cancel button: the same call P1's own page makes."""
        t_start = time.perf_counter()
        result = TurnResult(status="ok", session_id=clean_session_id(session_id))
        result.transcript = "confirm" if confirm else "cancel"
        self._ask_agent(result, result.transcript, confirm)
        return self._finish(result, result.reply_text, t_start)

    def voice_turn(self, session_id: str | None, audio: bytes, prior_turns: int = 0) -> TurnResult:
        t_start = time.perf_counter()
        result = TurnResult(status="ok", session_id=clean_session_id(session_id))
        stt = self.stt.transcribe(audio)
        result.timings["stt_ms"] = round(stt.ms)
        result.language = stt.language
        result.transcript_raw = stt.text
        result.stt_confidence = {
            "avg_logprob": None if stt.avg_logprob is None else round(stt.avg_logprob, 3),
            "no_speech_prob": round(stt.no_speech_prob, 3),
            "audio_seconds": round(stt.audio_seconds, 2),
        }
        prepared = prepare_transcript(stt.text, expect_order_id=self._asked_id(result.session_id))
        if not prepared.text.strip():  # silence, noise, or only fillers: never sent to the agent
            result.status = "no_speech"
            return self._finish(result, NO_SPEECH_TEXT, t_start, prior_turns)
        result.transcript = prepared.text
        result.order_ids, result.suspect_ids = prepared.order_ids, prepared.suspect_ids
        if stt.avg_logprob is not None and stt.avg_logprob < self.cfg.reject_logprob:
            # Whisper writes confident-looking sentences for babble or music; its own score gives it away
            result.status = "low_confidence"
            pending = self.has_pending(result.session_id, prior_turns)
            return self._finish(result, LOW_CONFIDENCE_TEXT if pending else NOT_SURE_TEXT, t_start, prior_turns)
        if self.has_pending(result.session_id, prior_turns):
            if not confident(stt, self.cfg):
                result.status = "low_confidence"
                return self._finish(result, LOW_CONFIDENCE_TEXT, t_start, prior_turns)
            answer = classify(prepared.text)
            if answer is None:
                result.status = "unclear_answer"
                return self._finish(result, UNCLEAR_TEXT, t_start, prior_turns)
            self._ask_agent(result, "confirm" if answer == "yes" else "cancel", answer == "yes")
        else:
            self._ask_agent(result, prepared.text, None)
        return self._finish(result, result.reply_text, t_start, prior_turns)

    def keep_debug_audio(self, audio: bytes) -> None:
        """Debug only (VOICE_KEEP_AUDIO_DIR). The file name is generated here, never taken from the client."""
        if self.cfg.keep_audio_dir:
            d = Path(self.cfg.keep_audio_dir)
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{int(time.time())}-{uuid.uuid4().hex[:8]}.audio").write_bytes(audio)
