import re

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import FakeAgent, FakeStt, agent_reply, stt_result, tiny_wav


def client(make_pipeline, stt, agent):
    pipe, tts = make_pipeline(stt, agent)
    return TestClient(create_app(pipe)), tts


def post_audio(c, data=None, **form):
    return c.post("/voice/turn", files={"audio": ("t.webm", tiny_wav() if data is None else data, "audio/webm")}, data=form)


def test_voice_turn_returns_text_audio_and_timings(make_pipeline):
    agent = FakeAgent(agent_reply("It shipped.", citations=["KB-001"]))
    c, _ = client(make_pipeline, FakeStt(stt_result("where is my order LC-1150")), agent)
    r = post_audio(c, session_id="voice-api1")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["session_id"] == "voice-api1"
    assert body["reply_text"] == "It shipped." and body["citations"] == ["KB-001"]
    assert body["audio_wav_base64"] and set(body["timings"]) == {"stt_ms", "agent_ms", "tts_ms", "total_ms"}


def test_generated_session_id_has_prefix(make_pipeline):
    c, _ = client(make_pipeline, FakeStt(stt_result("hello")), FakeAgent(agent_reply("Hi.")))
    assert post_audio(c).json()["session_id"].startswith("voice-")


def test_confirm_button_without_audio(make_pipeline):
    agent = FakeAgent(agent_reply("Return started."))
    c, _ = client(make_pipeline, FakeStt(), agent)
    r = c.post("/voice/turn", data={"session_id": "voice-api2", "confirm": "true"})
    assert r.status_code == 200
    assert agent.requests == [{"session_id": "voice-api2", "message": "confirm", "confirm": True}]


def test_bad_confirm_value(make_pipeline):
    c, _ = client(make_pipeline, FakeStt(), FakeAgent())
    assert c.post("/voice/turn", data={"confirm": "maybe"}).status_code == 400


def test_missing_audio_and_empty_audio(make_pipeline):
    c, _ = client(make_pipeline, FakeStt(), FakeAgent())
    assert c.post("/voice/turn", data={"session_id": "voice-a"}).status_code == 400
    assert post_audio(c, b"", session_id="voice-a").status_code == 400


def test_oversize_upload_rejected(make_pipeline):
    c, _ = client(make_pipeline, FakeStt(), FakeAgent())
    big = b"\x00" * (10 * 1024 * 1024 + 10)
    assert post_audio(c, big).status_code == 413


def test_undecodable_audio_is_a_400(make_pipeline):
    from app.stt import AudioError

    class BadStt(FakeStt):
        def transcribe(self, data, language=None):
            raise AudioError("could not decode audio: nope")

    c, _ = client(make_pipeline, BadStt(), FakeAgent())
    r = post_audio(c, b"not audio")
    assert r.status_code == 400 and "decode" in r.json()["detail"]


def test_silence_returns_no_speech_and_no_agent_call(make_pipeline):
    agent = FakeAgent()
    c, _ = client(make_pipeline, FakeStt(stt_result("")), agent)
    body = post_audio(c, session_id="voice-q").json()
    assert body["status"] == "no_speech" and agent.requests == []


def test_audio_is_not_written_to_disk_by_default(make_pipeline, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c, _ = client(make_pipeline, FakeStt(stt_result("hello")), FakeAgent(agent_reply("Hi.")))
    post_audio(c)
    assert list(tmp_path.iterdir()) == []


def test_debug_flag_keeps_audio(make_pipeline, tmp_path):
    from app.config import Settings

    pipe, _ = make_pipeline(FakeStt(stt_result("hello")), FakeAgent(agent_reply("Hi.")),
                            Settings(keep_audio_dir=str(tmp_path / "dbg")))
    TestClient(create_app(pipe)).post("/voice/turn", files={"audio": ("../../evil name.wav", tiny_wav(), "audio/wav")})
    saved = list((tmp_path / "dbg").iterdir())
    assert len(saved) == 1
    assert re.fullmatch(r"\d+-[0-9a-f]{8}\.audio", saved[0].name)  # generated here, not taken from the client
    assert not (tmp_path.parent / "evil name.wav").exists()


def test_say_and_health_and_page(make_pipeline):
    c, tts = client(make_pipeline, FakeStt(), FakeAgent())
    r = c.post("/voice/say", json={"text": "Your order LC-1150 is here"})
    assert r.status_code == 200 and r.content[:4] == b"RIFF"
    assert tts.spoken == ["Your order L C one one five zero is here"]
    assert c.post("/voice/say", json={"text": "  "}).status_code == 400
    h = c.get("/health").json()
    assert h["agent_reachable"] is True and h["stt_language"] == "en"
    page = c.get("/")
    assert page.status_code == 200 and "Hold to talk" in page.text
    assert "http://" not in page.text.replace("http://localhost", "") and "https://" not in page.text


def test_body_over_the_limit_is_refused_before_parsing(make_pipeline):
    stt = FakeStt()
    c, _ = client(make_pipeline, stt, FakeAgent())
    r = post_audio(c, b"\x00" * (12 * 1024 * 1024))
    assert r.status_code == 413 and stt.calls == 0


def test_body_without_content_length_is_refused(make_pipeline):
    c, _ = client(make_pipeline, FakeStt(), FakeAgent())

    def chunks():
        yield b"--x"

    r = c.post("/voice/turn", content=chunks(), headers={"content-type": "multipart/form-data; boundary=x"})
    assert r.status_code == 411


def test_say_is_capped(make_pipeline):
    c, _ = client(make_pipeline, FakeStt(), FakeAgent())
    assert c.post("/voice/say", json={"text": "a" * 2001}).status_code == 422
    assert c.post("/voice/say", json={"text": "a" * 2000}).status_code == 200
    r = c.post("/voice/say", content=b"x" * (70 * 1024), headers={"content-type": "application/json"})
    assert r.status_code == 413


def test_prior_turns_reaches_the_pipeline(make_pipeline):
    agent = FakeAgent()
    c, _ = client(make_pipeline, FakeStt(stt_result("where is my order")), agent)
    body = post_audio(c, session_id="voice-restarted", prior_turns="2").json()
    assert body["status"] == "unclear_answer" and body["pending"] is True and agent.requests == []
    assert post_audio(c, session_id="voice-x", prior_turns="-1").status_code == 422
