"""FastAPI service for the voice front end: POST /voice/turn, POST /voice/say, GET /health, the page at /."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import settings
from app.pipeline import VoicePipeline
from app.stt import AudioError

STATIC_DIR = Path(__file__).resolve().parent / "static"
SAY_MAX_CHARS = 2000
SAY_BODY_LIMIT = 64 * 1024
MULTIPART_OVERHEAD = 1024 * 1024


class SayRequest(BaseModel):
    text: str = Field(max_length=SAY_MAX_CHARS)


class _TooLarge(Exception):
    pass


class BodyLimit:
    """Refuse an oversized POST body before it is parsed or buffered.

    A request must declare Content-Length (411 otherwise); one over the limit is refused with 413 straight
    away, and a body that turns out larger than it declared is cut off mid-stream.
    """

    def __init__(self, app, limits: dict[str, int]) -> None:
        self.app = app
        self.limits = limits

    async def __call__(self, scope, receive, send) -> None:
        limit = self.limits.get(scope.get("path", "")) if scope["type"] == "http" and scope["method"] == "POST" else None
        if limit is None:
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is None or not declared.isdigit():
            await self._reply(send, 411, "Content-Length is required")
            return
        if int(declared) > limit:
            await self._reply(send, 413, f"request body larger than {limit} bytes")
            return
        received = 0
        started = False

        async def counted():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise _TooLarge
            return message

        async def tracked(message):
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, counted, tracked)
        except _TooLarge:
            if not started:
                await self._reply(send, 413, f"request body larger than {limit} bytes")

    @staticmethod
    async def _reply(send, status: int, detail: str) -> None:
        body = json.dumps({"detail": detail}).encode()
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})


def create_app(pipeline: VoicePipeline | None = None, preload: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if preload:
            app.state.pipeline.preload()
        yield

    app = FastAPI(title="Larkfield voice intake", lifespan=lifespan)
    pipe_cfg = pipeline.cfg if pipeline else settings
    app.state.pipeline = pipeline or VoicePipeline()
    max_bytes = pipe_cfg.max_upload_mb * 1024 * 1024

    @app.post("/voice/turn")
    def voice_turn(
        audio: Annotated[UploadFile | None, File()] = None,
        session_id: Annotated[str | None, Form()] = None,
        confirm: Annotated[str | None, Form()] = None,
        prior_turns: Annotated[int, Form(ge=0, le=100000)] = 0,
    ) -> dict:
        pipe: VoicePipeline = app.state.pipeline
        if confirm is not None and confirm.lower() in ("true", "false"):
            return pipe.press_button(session_id, confirm.lower() == "true").to_dict()
        if confirm is not None:
            raise HTTPException(400, "confirm must be true or false")
        if audio is None:
            raise HTTPException(400, "send an audio file or a confirm value")
        data = audio.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(413, f"audio larger than {pipe_cfg.max_upload_mb} MB")
        if not data:
            raise HTTPException(400, "empty audio upload")
        pipe.keep_debug_audio(data)
        try:  # the audio is not kept after this request (unless the debug flag is set)
            return pipe.voice_turn(session_id, data, prior_turns).to_dict()
        except AudioError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/voice/say")
    def voice_say(req: SayRequest) -> Response:
        """Text to speech only (used by evals and by integrations that bring their own transcript)."""
        if not req.text.strip():
            raise HTTPException(400, "text is empty")
        from app.speakable import make_speakable

        return Response(app.state.pipeline.tts.synthesize(make_speakable(req.text)).wav, media_type="audio/wav")

    @app.get("/health")
    def health() -> dict:
        pipe: VoicePipeline = app.state.pipeline
        return {
            "status": "ok",
            "stt_model_loaded": pipe.stt._model is not None,
            "tts_voice_loaded": pipe.tts._voice is not None,
            "agent_url": settings.agent_url,
            "agent_reachable": pipe.agent.healthy(),
            "stt_language": settings.stt_language,
        }

    @app.middleware("http")
    async def no_cache_for_page(request, call_next):
        response = await call_next(request)
        if request.method == "GET" and not request.url.path.startswith("/health"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    if STATIC_DIR.is_dir():
        app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
    app.add_middleware(BodyLimit, limits={"/voice/turn": max_bytes + MULTIPART_OVERHEAD, "/voice/say": SAY_BODY_LIMIT})
    return app


app = create_app(preload=True)
