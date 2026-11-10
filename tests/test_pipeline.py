import base64

import pytest

from app import pipeline as pl
from app.pipeline import CONFIRM_UNKNOWN_TEXT, FALLBACK_TEXT, asks_for_order_id, clean_session_id
from tests.conftest import FakeAgent, FakeStt, agent_reply, stt_result, tiny_wav
from tests.test_answer import HARD_NEGATIVES

PENDING = {"tool": "start_return", "args": {"order_id": "LC-1150", "skus": ["GR-001"], "reason": "faulty"}}


def test_session_ids_always_start_with_voice():
    assert clean_session_id(None).startswith("voice-")
    assert clean_session_id("voice-abc123") == "voice-abc123"
    assert clean_session_id("abc").startswith("voice-abc")
    assert clean_session_id("a b/c!").startswith("voice-abc")
    assert clean_session_id("!!!").startswith("voice-")
    assert len(clean_session_id("x" * 500)) <= len("voice-") + 64


def test_normal_turn(make_pipeline):
    stt = FakeStt(stt_result("Where is my order el see eleven fifty?"))
    agent = FakeAgent(agent_reply("Order LC-1150 shipped via BlueDart [KB-003].", citations=["KB-003"]))
    pipe, tts = make_pipeline(stt, agent)
    r = pipe.voice_turn("voice-t1", tiny_wav())
    assert r.status == "ok" and not r.pending
    assert r.transcript == "Where is my order LC-1150?"
    assert r.transcript_raw == "Where is my order el see eleven fifty?"
    assert r.order_ids == ["LC-1150"]
    assert agent.requests == [{"session_id": "voice-t1", "message": "Where is my order LC-1150?", "confirm": None}]
    assert tts.spoken == ["Order L C one one five zero shipped via BlueDart."]
    assert r.reply_text.startswith("Order LC-1150")
    assert r.citations == ["KB-003"]
    assert base64.b64decode(r.audio_wav_base64)[:4] == b"RIFF"
    assert set(r.timings) == {"stt_ms", "agent_ms", "tts_ms", "total_ms"}


def test_silence_never_reaches_the_agent(make_pipeline):
    agent = FakeAgent()
    pipe, tts = make_pipeline(FakeStt(stt_result("")), agent)
    r = pipe.voice_turn("voice-s", tiny_wav())
    assert r.status == "no_speech"
    assert agent.requests == []
    assert "didn't catch" in tts.spoken[0]
    assert "agent_ms" not in r.timings


def test_only_fillers_never_reaches_the_agent(make_pipeline):
    agent = FakeAgent()
    pipe, _ = make_pipeline(FakeStt(stt_result("Um, uh.")), agent)
    assert pipe.voice_turn("voice-s", tiny_wav()).status == "no_speech"
    assert agent.requests == []


def test_agent_down_speaks_fixed_fallback_and_never_retries(make_pipeline):
    agent = FakeAgent(fail=True)
    pipe, tts = make_pipeline(FakeStt(stt_result("Where is my order LC-1150")), agent)
    r = pipe.voice_turn("voice-d", tiny_wav())
    assert r.status == "agent_unavailable"
    assert r.reply_text == FALLBACK_TEXT
    assert tts.spoken == [FALLBACK_TEXT]
    assert len(agent.requests) == 1  # one attempt, no automatic retry


def test_failed_agent_call_marks_pending_fail_safe(make_pipeline):
    agent = FakeAgent(fail=True)
    pipe, _ = make_pipeline(FakeStt(stt_result("Where is my order LC-1150"), stt_result("where is my order")), agent)
    r = pipe.voice_turn("voice-d2", tiny_wav())
    assert r.pending and pipe.has_pending("voice-d2")
    # the next spoken turn is now treated as an answer to a possibly pending action: not sent
    r2 = pipe.voice_turn("voice-d2", tiny_wav())
    assert r2.status == "unclear_answer" and len(agent.requests) == 1


def test_timed_out_confirm_does_not_say_try_again(make_pipeline):
    agent = FakeAgent(fail=True)
    pipe, tts = make_pipeline(FakeStt(), agent)
    r = pipe.press_button("voice-d3", True)
    assert r.status == "agent_unavailable" and r.reply_text == CONFIRM_UNKNOWN_TEXT
    assert "couldn't check whether that went through" in tts.spoken[0]
    assert "please try again" not in CONFIRM_UNKNOWN_TEXT
    assert r.pending


def test_spoken_yes_sends_confirm_true(make_pipeline):
    stt = FakeStt(stt_result("I want to return the grinder from LC-1150"), stt_result("Yes, please go ahead."))
    agent = FakeAgent(agent_reply("I can start a return. Please confirm.", PENDING), agent_reply("Done."))
    pipe, _ = make_pipeline(stt, agent)
    r1 = pipe.voice_turn("voice-p", tiny_wav())
    assert r1.pending_action == PENDING and r1.pending and pipe.has_pending("voice-p")
    r2 = pipe.voice_turn("voice-p", tiny_wav())
    assert agent.requests[1] == {"session_id": "voice-p", "message": "confirm", "confirm": True}
    assert all("pending_action" not in q for q in agent.requests)
    assert r2.pending_action is None and not r2.pending and not pipe.has_pending("voice-p")
    assert r2.transcript == "Yes, please go ahead."


def test_spoken_no_sends_confirm_false(make_pipeline):
    stt = FakeStt(stt_result("return it"), stt_result("No, cancel that."))
    agent = FakeAgent(agent_reply("Please confirm.", PENDING), agent_reply("Okay, cancelled."))
    pipe, _ = make_pipeline(stt, agent)
    pipe.voice_turn("voice-y", tiny_wav())
    r = pipe.voice_turn("voice-y", tiny_wav())
    assert r.status == "ok"
    assert agent.requests[1] == {"session_id": "voice-y", "message": "cancel", "confirm": False}


@pytest.mark.parametrize("phrase", [h for h in HARD_NEGATIVES if h.strip()])
def test_hard_negative_answers_are_never_sent_while_pending(make_pipeline, phrase):
    agent = FakeAgent(agent_reply("Please confirm.", PENDING))
    pipe, _ = make_pipeline(FakeStt(stt_result("return it"), stt_result(phrase)), agent)
    pipe.voice_turn("voice-h", tiny_wav())
    r = pipe.voice_turn("voice-h", tiny_wav())
    assert r.status in ("unclear_answer", "no_speech"), phrase
    assert len(agent.requests) == 1, phrase  # nothing new reached the agent
    assert r.pending and pipe.has_pending("voice-h")


def test_unclear_answer_is_spoken(make_pipeline):
    agent = FakeAgent(agent_reply("Please confirm.", PENDING))
    pipe, tts = make_pipeline(FakeStt(stt_result("return it"), stt_result("Yeah, no")), agent)
    pipe.voice_turn("voice-u", tiny_wav())
    r = pipe.voice_turn("voice-u", tiny_wav())
    assert r.status == "unclear_answer" and tts.spoken[-1] == "Please say yes or no, or press Confirm or Cancel."


def test_low_confidence_answer_is_not_sent_while_pending(make_pipeline):
    stt = FakeStt(stt_result("return it"), stt_result("yes", logprob=-1.4), stt_result("yes", no_speech=0.8))
    agent = FakeAgent(agent_reply("Please confirm.", PENDING))
    pipe, tts = make_pipeline(stt, agent)
    pipe.voice_turn("voice-c", tiny_wav())
    for _ in range(2):
        r = pipe.voice_turn("voice-c", tiny_wav())
        assert r.status == "low_confidence" and r.transcript == "yes" and r.pending
    assert len(agent.requests) == 1
    assert "press Confirm or Cancel" in tts.spoken[-1]
    assert pipe.has_pending("voice-c")


def test_moderate_confidence_is_fine_when_nothing_pending(make_pipeline):
    agent = FakeAgent(agent_reply("Hello."))
    pipe, _ = make_pipeline(FakeStt(stt_result("hello there", logprob=-0.85)), agent)  # below the pending gate, above the reject line
    assert pipe.voice_turn("voice-n", tiny_wav()).status == "ok"
    assert len(agent.requests) == 1


def test_very_low_confidence_is_never_sent_even_with_nothing_pending(make_pipeline):
    # Whisper wrote a fluent sentence for babble; its own score (-0.99 on the eval clip) gives it away
    agent = FakeAgent(agent_reply("Hello."))
    pipe, tts = make_pipeline(FakeStt(stt_result("They are worth living up to the number of girls", logprob=-0.99)), agent)
    r = pipe.voice_turn("voice-n2", tiny_wav())
    assert r.status == "low_confidence" and agent.requests == [] and not r.pending
    assert tts.spoken == ["I wasn't sure what you said. Please say it again."]


def test_no_speech_keeps_the_pending_card(make_pipeline):
    agent = FakeAgent(agent_reply("Please confirm.", PENDING))
    pipe, _ = make_pipeline(FakeStt(stt_result("return it"), stt_result("")), agent)
    pipe.voice_turn("voice-k", tiny_wav())
    r = pipe.voice_turn("voice-k", tiny_wav())
    assert r.status == "no_speech" and r.pending


def test_unknown_session_with_earlier_turns_is_treated_as_pending(make_pipeline):
    agent = FakeAgent(agent_reply("Hello."))
    pipe, _ = make_pipeline(FakeStt(stt_result("where is my order"), stt_result("where is my order")), agent)
    # this service has never seen the session, but the page says it already had 3 turns (service restarted)
    r = pipe.voice_turn("voice-restart", tiny_wav(), prior_turns=3)
    assert r.status == "unclear_answer" and r.pending and agent.requests == []
    # a brand new session (no earlier turns) is not pending
    r = pipe.voice_turn("voice-fresh", tiny_wav(), prior_turns=0)
    assert r.status == "ok" and len(agent.requests) == 1


def test_button_clears_an_assumed_pending_state(make_pipeline):
    agent = FakeAgent(agent_reply("There is nothing waiting for confirmation."), agent_reply("Order shipped."))
    pipe, _ = make_pipeline(FakeStt(stt_result("where is order LC-1150")), agent)
    assert pipe.has_pending("voice-r", prior_turns=2)
    pipe.press_button("voice-r", False)
    assert not pipe.has_pending("voice-r", prior_turns=2)
    assert pipe.voice_turn("voice-r", tiny_wav(), prior_turns=2).status == "ok"


def test_session_state_is_evicted_least_recently_used_first(make_pipeline, monkeypatch):
    monkeypatch.setattr(pl, "MAX_SESSIONS", 3)
    pipe, _ = make_pipeline(FakeStt(), FakeAgent())
    for sid in ("a", "b", "c"):
        pipe._state(sid, create=True).pending = True
    pipe._state("a")  # a is used again: b is now the least recently used
    pipe._state("d", create=True)
    assert pipe._state("b") is None and pipe._state("a") is not None and pipe._state("d") is not None
    # an evicted session with earlier turns fails safe
    assert pipe.has_pending("b", prior_turns=1) is True


def test_pending_action_is_spoken_from_the_action_itself(make_pipeline):
    reply = agent_reply("long model text that should not be what is spoken. Estimated refund: INR 2,499 (x).", PENDING)
    pipe, tts = make_pipeline(FakeStt(stt_result("return it")), FakeAgent(reply))
    r = pipe.voice_turn("voice-sp", tiny_wav())
    expected = ("I can start a return for order L C one one five zero, items G R zero zero one, reason: faulty, "
                "estimated refund 2499 rupees. Say yes or no, or press Confirm or Cancel.")
    assert tts.spoken == [expected]
    assert r.spoken_text == tts.spoken[0] and r.reply_text.startswith("long model text")


def test_bare_id_answer_only_after_the_agent_asked_for_one(make_pipeline):
    agent = FakeAgent(agent_reply("Sure. What is your order id?"), agent_reply("Order shipped."), agent_reply("Okay."))
    stt = FakeStt(stt_result("where is my order"), stt_result("Eleven fifty."), stt_result("Eleven fifty."))
    pipe, _ = make_pipeline(stt, agent)
    pipe.voice_turn("voice-b1", tiny_wav())
    r = pipe.voice_turn("voice-b1", tiny_wav())
    assert r.transcript == "LC-1150." and r.order_ids == ["LC-1150"]
    pipe.voice_turn("voice-b1", tiny_wav())  # the reply "Order shipped." did not ask: left alone
    assert agent.requests[2]["message"] == "Eleven fifty."


def test_asks_for_order_id():
    assert asks_for_order_id("Sure. What is your order id?")
    assert asks_for_order_id("Please share your order number.")
    assert not asks_for_order_id("Your order shipped yesterday.")
    assert not asks_for_order_id("Order id LC-1150 is delivered.")


def test_buttons_send_confirm_flag_and_fixed_words(make_pipeline):
    agent = FakeAgent(agent_reply("Return started."), agent_reply("Cancelled."))
    pipe, _ = make_pipeline(FakeStt(), agent)
    pipe.press_button("voice-b", True)
    pipe.press_button("voice-b", False)
    assert agent.requests == [
        {"session_id": "voice-b", "message": "confirm", "confirm": True},
        {"session_id": "voice-b", "message": "cancel", "confirm": False},
    ]


def test_suspect_id_is_reported_and_sent_as_heard(make_pipeline):
    agent = FakeAgent(agent_reply("I can't find that order."))
    pipe, _ = make_pipeline(FakeStt(stt_result("where is LC one one five")), agent)
    r = pipe.voice_turn("voice-x", tiny_wav())
    assert r.suspect_ids == ["LC-115"]
    assert agent.requests[0]["message"] == "where is LC-115"


def test_heard_id_is_never_snapped_to_a_real_order(make_pipeline):
    agent = FakeAgent(agent_reply("No such order."))
    pipe, _ = make_pipeline(FakeStt(stt_result("order L C one zero zero zero")), agent)
    pipe.voice_turn("voice-z", tiny_wav())
    assert agent.requests[0]["message"] == "order LC-1000"
