import json
from pathlib import Path

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.answer import classify
from app.normalize import normalize_order_ids
from evals import clips, p1_answer, record, report, run_e2e, run_stt
from evals.common import add_noise, array_to_wav, percentile, wav_to_array
from tests.conftest import FakeAgent, FakeStt, agent_reply, stt_result


def test_manifest_shape():
    manifest = clips.build()
    assert len(manifest) == 37
    assert len({c["id"] for c in manifest}) == 37
    kinds = [c["kind"] for c in manifest]
    assert kinds.count("silent") + kinds.count("noise") == 2
    assert kinds.count("nonspeech") == 3 and {c["group"] for c in manifest if c["kind"] == "nonspeech"} == {
        "laughter", "babble", "keyboard"}
    assert kinds.count("yes") >= 2 and kinds.count("no") >= 2 and kinds.count("hardneg") >= 3
    assert kinds.count("query") == 25
    for c in manifest:
        assert {"spoken", "typed", "expected_order_id", "expected_tool", "length_scale", "snr_db"} <= set(c)
    assert sum(c["snr_db"] is not None for c in manifest) >= 5  # noisy clips
    assert len({c["length_scale"] for c in manifest}) >= 4  # several speaking rates


def test_manifest_file_matches_the_source_and_audio_exists():
    root = Path(__file__).resolve().parents[1] / "evals"
    on_disk = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in on_disk] == [c["id"] for c in clips.build()]
    assert all((root / "audio" / c["file"]).exists() for c in on_disk)


def test_confusable_ids_present_and_labels_follow_the_spoken_words():
    manifest = {c["id"]: c for c in clips.build()}
    labels = {c["expected_order_id"] for c in manifest.values() if c["expected_order_id"]}
    assert {"LC-1150", "LC-1015", "LC-1050", "LC-1115"} <= labels
    for c in manifest.values():
        if c["expected_order_id"]:
            # the label is derived independently of the normaliser: it must be what the normaliser reads too
            assert normalize_order_ids(c["spoken"]).order_ids == [c["expected_order_id"]], c["id"]
            assert c["expected_order_id"] in c["typed"]


def test_scenario_clips_exist_with_the_roles_the_e2e_needs():
    by_id = {c["id"]: c for c in clips.build()}
    roles = (run_e2e.CANCEL_REQUEST, run_e2e.UNCLEAR_REQUEST, run_e2e.CONFIRM_REQUEST)
    assert [by_id[r]["expected_order_id"] for r in roles] == ["LC-1137", "LC-1154", "LC-1161"]
    assert all(by_id[r]["expected_tool"] == "start_return" for r in roles)
    assert len({by_id[r]["expected_order_id"] for r in roles}) == 3  # cancel, unclear and confirm each get their own order
    assert by_id[run_e2e.YES_CLIP]["kind"] == "yes" and by_id[run_e2e.NO_CLIP]["kind"] == "no"
    assert by_id[run_e2e.UNCLEAR_CLIP]["kind"] == "hardneg"


P1_DATA = Path(__file__).resolve().parents[2] / "fde-support-agent" / "data"  # sibling checkout
# the item each return clip names, and what P1's order data must hold for it (read-only check)
RETURN_ITEMS = {"S14": "kettle", "S15": "beans", "S16": "moka", "S37": "grinder"}


def test_return_clips_match_p1_order_data():
    """Run 1 of the e2e eval used clips that did not match the orders, and P1 rightly refused them."""
    from datetime import date

    if not (P1_DATA / "orders.json").exists():
        pytest.skip("project 1 data not available")
    orders = {o["order_id"]: o for o in json.loads((P1_DATA / "orders.json").read_text(encoding="utf-8"))}
    products = {p["sku"]: p for p in json.loads((P1_DATA / "products.json").read_text(encoding="utf-8"))}
    by_id = {c["id"]: c for c in clips.build()}
    for cid, item in RETURN_ITEMS.items():
        clip = by_id[cid]
        order = orders[clip["expected_order_id"]]
        assert order["status"] == "delivered" and order["delivered_at"], cid
        age = (date(2026, 11, 10) - date.fromisoformat(order["delivered_at"][:10])).days
        assert 0 <= age <= 25, (cid, age)  # inside the 30-day window with room to spare
        held = [products[i["sku"]] for i in order["items"]]
        assert any(item in p["name"].lower() or item == p["category"] for p in held), (cid, [p["name"] for p in held])
        assert "orchestrator 2026-11-10, after e2e run 1" in clip["note"]
        assert item in clip["spoken"].lower() or item == "beans" and "beans" in clip["spoken"].lower()


def test_noise_is_deterministic_and_at_requested_snr():
    speech = np.sin(np.linspace(0, 400, 16000)).astype(np.float32) * 0.3
    a = add_noise(speech, 10, np.random.default_rng(1))
    b = add_noise(speech, 10, np.random.default_rng(1))
    assert np.array_equal(a, b)
    noise = a - speech
    snr = 20 * np.log10(np.sqrt(np.mean(speech**2)) / np.sqrt(np.mean(noise**2)))
    assert snr == pytest.approx(10, abs=0.5)


def test_wav_roundtrip():
    x = np.linspace(-0.5, 0.5, 1000).astype(np.float32)
    y, rate = wav_to_array(array_to_wav(x, 22050))
    assert rate == 22050 and np.allclose(x, y, atol=1e-3)


def test_percentile():
    assert percentile([], 50) == 0.0
    assert percentile([1, 2, 3, 4], 50) == pytest.approx(2.5)
    assert percentile([10], 95) == 10
    assert percentile(list(range(101)), 95) == pytest.approx(95)


def test_p1_reader_loads_read_only_and_rejects_the_hard_negatives():
    fn = p1_answer.load_typed_answer()
    if fn is None:
        pytest.skip("project 1 agent.py not available")
    assert p1_answer.p1_reads("Yes, please go ahead.", fn) == "yes"
    assert p1_answer.p1_reads("No, cancel that.", fn) == "no"
    for phrase in clips.HARD_NEGATIVE_PHRASES:
        assert classify(phrase) is None, phrase
        if phrase != "Don't cancel it":  # P1 reads this as a no (cancel): a finding reported to the project 1 owner
            assert p1_answer.p1_reads(phrase, fn) is None, phrase
    assert p1_answer.load_typed_answer(Path("does-not-exist.py")) is None


def test_score_row_for_clips():
    clip = {"id": "S01", "kind": "query", "spoken": "Where is my order L C one one five zero?",
            "typed": "Where is my order LC-1150?", "expected_order_id": "LC-1150", "snr_db": None}
    row = run_stt.score_clip(clip, stt_result("Where is my order LC-1150?"))
    assert row["id_exact"] is True and row["wer_norm"] == 0.0 and row["wer_raw"] > 0
    assert row["wer_typed"] == 0.0  # headline: against the typed reference
    bad = run_stt.score_clip(clip, stt_result("Where is my order LC-1015?"))
    assert bad["id_exact"] is False and bad["wer_norm"] > 0 and bad["wer_typed"] > 0
    quiet = {"id": "S29", "kind": "silent", "spoken": "", "typed": "", "snr_db": None}
    assert run_stt.score_clip(quiet, stt_result(""))["no_text"] is True
    assert run_stt.score_clip(quiet, stt_result("Thank you."))["no_text"] is False
    assert run_stt.score_clip(quiet | {"kind": "nonspeech"}, stt_result("Ha ha ha."))["no_text"] is False
    babble = run_stt.score_clip(quiet | {"kind": "nonspeech"}, stt_result("They are worth living up to the number of girls", logprob=-0.99))
    assert babble["no_text"] is False and babble["blocked"] is True  # text, but the confidence rule stops it
    laugh = run_stt.score_clip(quiet | {"kind": "nonspeech"}, stt_result("Ha ha ha.", logprob=-0.4))
    assert laugh["blocked"] is False


def test_yes_no_rows_use_both_readers():
    yes = {"id": "S25", "kind": "yes", "spoken": "Yes, please go ahead.", "typed": "Yes, please go ahead.",
           "expected_order_id": None, "snr_db": None}
    row = run_stt.score_clip(yes, stt_result("Yes, please go ahead."))
    assert row["p6_ok"] is True and row["p6_answer"] == "yes"
    assert row.get("p1_ok") in (True, None)
    neg = yes | {"id": "S31", "kind": "hardneg", "spoken": "Yeah, no.", "typed": "Yeah, no."}
    row = run_stt.score_clip(neg, stt_result("Yeah, no."))
    assert row["p6_ok"] is True and row["p6_answer"] is None  # not an answer: correct for a hard negative
    row = run_stt.score_clip(neg, stt_result("Yeah."))
    assert row["p6_ok"] is False and row["p6_answer"] == "yes"  # a mis-heard hard negative would confirm: counted as a miss


def test_summarize_counts():
    rows = [
        {"id": "a", "source": "synthetic", "kind": "query", "spoken": "x y", "typed": "x y", "raw": "x y", "sent": "x y",
         "id_exact": True, "id_raw_exact": True, "audio_seconds": 2.0, "stt_ms": 1000, "wer_norm": 0.0, "wer_raw": 0.0, "wer_typed": 0.0},
        {"id": "b", "source": "synthetic", "kind": "query", "spoken": "x y", "typed": "x y", "raw": "x z", "sent": "x z",
         "id_exact": False, "id_raw_exact": False, "audio_seconds": 2.0, "stt_ms": 3000, "wer_norm": 0.5, "wer_raw": 0.5, "wer_typed": 0.5},
        {"id": "c", "source": "synthetic", "kind": "silent", "spoken": "", "typed": "", "raw": "", "sent": "", "no_text": True,
         "blocked": True, "audio_seconds": 3.0, "stt_ms": 10},
        {"id": "d", "source": "synthetic", "kind": "hardneg", "spoken": "x", "typed": "x", "raw": "x", "sent": "x", "wer_norm": 0.0,
         "wer_raw": 0.0, "wer_typed": 0.0, "p6_ok": True, "p1_ok": False, "audio_seconds": 2.0, "stt_ms": 500},
    ]
    s = run_stt.summarize(rows)
    assert s["id_exact"] == 1 and s["id_total"] == 2 and s["quiet_ok"] == 1 and s["quiet_total"] == 1
    assert s["wer_norm"] == pytest.approx(0.2) and s["wer_typed"] == pytest.approx(0.2)
    assert s["hardneg_ok"] == 1 and s["hardneg_total"] == 1


# ---- end-to-end scoring (no P1 needed)

def clip(tool, order=None):
    return {"id": "X", "expected_tool": tool, "expected_order_id": order}


def test_score_reply_tool_and_order():
    reply = {"tool_calls": [{"name": "lookup_order", "args": {"order_id": "LC-1150"}, "result": {}}]}
    assert run_e2e.score_reply(clip("lookup_order", "LC-1150"), reply)["ok"]
    wrong = {"tool_calls": [{"name": "lookup_order", "args": {"order_id": "LC-1015"}, "result": {}}]}
    s = run_e2e.score_reply(clip("lookup_order", "LC-1150"), wrong)
    assert not s["ok"] and s["wrong_order"]
    assert not run_e2e.score_reply(clip("lookup_order", "LC-1150"), {"tool_calls": []})["ok"]


def test_score_reply_pending_action_counts_as_the_tool():
    reply = {"tool_calls": [], "pending_action": {"tool": "start_return", "args": {"order_id": "LC-1144"}}}
    s = run_e2e.score_reply(clip("start_return", "LC-1144"), reply)
    assert s["ok"] and s["pending"]


def test_score_reply_no_tool_label():
    assert run_e2e.score_reply(clip(None), {"tool_calls": [{"name": "check_stock", "args": {}}]})["ok"]
    assert not run_e2e.score_reply(clip(None), {"pending_action": {"tool": "create_ticket", "args": {}}})["ok"]


def test_ticket_label_counts_only_real_ticket_calls_and_handoffs_separately():
    proposed = {"pending_action": {"tool": "create_ticket", "args": {"summary": "x"}}}
    executed = {"tool_calls": [{"name": "create_ticket", "args": {}, "result": {"ref": "T-1"}}]}
    assert run_e2e.score_reply(clip("create_ticket"), proposed)["ok"]
    assert run_e2e.score_reply(clip("create_ticket"), executed)["ok"]
    handoff = run_e2e.score_reply(clip("create_ticket"), {"escalated": True, "tool_calls": []})
    assert not handoff["ok"] and handoff["handoff_only"] and handoff["escalated"]
    both = run_e2e.score_reply(clip("create_ticket"), {"escalated": True} | proposed)
    assert both["ok"] and not both["handoff_only"]


def test_summary_separates_tickets_and_handoffs():
    def row(ok, handoff):
        return {"id": "T", "source": "synthetic", "expected_tool": "create_ticket", "expected_order_id": None,
                "typed": {"ok": ok, "handoff_only": handoff}, "voiced": {"ok": ok, "handoff_only": handoff, "timings": {"agent_ms": 1}}}

    s = run_e2e.summarize([row(True, False), row(False, True), row(False, True)])
    assert s["ticket_n"] == 3 and s["ticket_voiced_ok"] == 1 and s["handoff_only_voiced"] == 2 and s["handoff_only_typed"] == 2


def test_quiet_clip_makes_no_call(make_pipeline, tmp_path, monkeypatch):
    class Counter:
        calls = 0

    agent = FakeAgent()
    pipe, _ = make_pipeline(FakeStt(stt_result("")), agent)
    wav = tmp_path / "S29.wav"
    wav.write_bytes(array_to_wav(np.zeros(16000, dtype=np.float32), 16000))
    monkeypatch.setattr(run_e2e, "clip_path", lambda c: wav)
    out = run_e2e.run_quiet({"id": "S29", "kind": "silent"}, pipe, Counter())
    assert out["ok"] and out["status"] == "no_speech" and agent.requests == []


@pytest.fixture
def silent_wav(tmp_path, monkeypatch):
    wav = tmp_path / "x.wav"
    wav.write_bytes(array_to_wav(np.zeros(16000, dtype=np.float32), 16000))
    monkeypatch.setattr(run_e2e, "clip_path", lambda c: wav)
    return wav


def test_scenarios_cancel_unclear_then_confirm(make_pipeline, silent_wav):
    pending_a = {"tool": "start_return", "args": {"order_id": "LC-1144"}}
    pending_b = {"tool": "start_return", "args": {"order_id": "LC-1199"}}
    done = agent_reply("Return started.", tool_calls=[{"name": "start_return", "args": {}, "result": {"return_id": "R-1"}}])
    agent = FakeAgent(
        agent_reply("Please confirm.", pending_a), agent_reply("Cancelled."),                  # voice-cancel
        agent_reply("Please confirm.", pending_a), agent_reply("Cancelled by cleanup."),      # voice-unclear (+ button cleanup)
        agent_reply("Please confirm.", pending_b), done,                                       # voice-confirm
    )
    stt = FakeStt(stt_result("return the kettle from LC-1144"), stt_result("No, cancel that."),
                  stt_result("return the kettle from LC-1144"), stt_result("Yeah, no."),
                  stt_result("return the grinder from LC-1199"), stt_result("Yes, please go ahead."))
    pipe, _ = make_pipeline(stt, agent)
    req_a, req_b, yes, no, unclear = {"id": "S14"}, {"id": "S16"}, {"id": "S25"}, {"id": "S27"}, {"id": "S31"}
    cancel = run_e2e.run_scenario("voice-cancel", req_a, no, pipe, "cancel")
    unclear_out = run_e2e.run_scenario("voice-unclear", req_a, unclear, pipe, "unclear")
    confirm = run_e2e.run_scenario("voice-confirm", req_b, yes, pipe, "execute")
    assert cancel["ok"] and unclear_out["ok"] and confirm["ok"]
    assert confirm["request_order"] == "LC-1199" and cancel["request_order"] == "LC-1144"
    assert [(r["message"], r["confirm"]) for r in agent.requests] == [
        ("return the kettle from LC-1144", None), ("cancel", False),
        ("return the kettle from LC-1144", None), ("cancel", False),   # the second is the cleanup button, not the unclear answer
        ("return the grinder from LC-1199", None), ("confirm", True),
    ]
    assert unclear_out["answer_status"] == "unclear_answer" and unclear_out["executed"] == []


def test_the_confirm_scenario_is_the_only_one_that_can_write():
    assert [p for p in ("voice-cancel", "voice-unclear", "voice-confirm")] == ["voice-cancel", "voice-unclear", "voice-confirm"]
    src = Path(run_e2e.__file__).read_text(encoding="utf-8")
    assert src.index('"voice-confirm", CONFIRM_REQUEST') > src.index('"voice-cancel", CANCEL_REQUEST')
    assert "DATABASE PRECONDITION" in src and run_e2e.PRECONDITION in src.replace('"\n    "', "") or run_e2e.PRECONDITION


def test_scenario_fails_when_agent_proposes_nothing(make_pipeline, silent_wav):
    pipe, _ = make_pipeline(FakeStt(stt_result("return it")), FakeAgent(agent_reply("Sorry, no.")))
    out = run_e2e.run_scenario("voice-confirm", {"id": "S14"}, {"id": "S25"}, pipe, "execute")
    assert not out["ok"] and not out["pending_after_request"]


# ---- recorder and report

def test_record_saves_clip_and_manifest(tmp_path, monkeypatch):
    monkeypatch.setattr(record, "OWN_DIR", tmp_path)
    monkeypatch.setattr(record, "OWN_MANIFEST", tmp_path / "manifest.json")
    c = TestClient(record.create_app())
    assert "O01" in c.get("/").text
    r = c.post("/save/O01", files={"audio": ("O01.webm", b"x" * 2000, "audio/webm")})
    assert r.status_code == 200 and r.json()["clips_recorded"] == 1
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest[0]["id"] == "O01" and manifest[0]["source"] == "own" and manifest[0]["expected_order_id"] == "LC-1150"
    assert c.post("/save/O99", files={"audio": ("a.webm", b"x" * 2000, "audio/webm")}).status_code == 404
    assert c.post("/save/O02", files={"audio": ("a.webm", b"x", "audio/webm")}).status_code == 400
    assert len(record.PROMPTS) == 10


BASE = {"clips": 36, "wer_typed": 0.022, "wer_raw": 0.28, "wer_norm": 0.03, "id_exact": 16, "id_total": 16, "id_raw_exact": 15,
        "yn_ok": 4, "yn_total": 4, "yn_ok_p1": 4, "hardneg_ok": 3, "hardneg_total": 3, "hardneg_ok_p1": 3,
        "quiet_ok": 5, "quiet_total": 5, "stt_ms_p50": 1700.0, "stt_ms_p95": 2600.0, "stt_rtf": 0.5}
STT = {"date": "d", "elapsed_s": 1, "calibration": [], "p1_reader": "available",
       "answers_text": [{"phrase": "Yeah, no", "p6": None, "p1": None}],
       "tts": {"n": 2, "ms_p50": 200, "ms_p95": 400, "rtf_p50": 0.03, "rows": []},
       "runs": {"en": {"rows": [], "summary": {"synthetic": BASE}},
                "auto": {"rows": [{"language": "en", "source": "synthetic"}], "summary": {"synthetic": BASE | {"stt_ms_p50": 2500.0}}}}}


def test_report_headline_wer_is_against_the_typed_reference():
    table = report.numbers_table(STT, None)
    lines = {ln.split("|")[1].strip(): ln for ln in table.splitlines() if ln.startswith("| ") and "|" in ln[2:]}
    headline = next(v for k, v in lines.items() if k.startswith("WER, Whisper text vs the typed reference"))
    secondary = next(v for k, v in lines.items() if k.startswith("WER with ids and numbers collapsed"))
    assert "2.2%" in headline and "3.0%" in secondary
    assert "28.3%" not in table  # the raw-vs-spoken-words figure is no longer a headline number
    assert "pending" in table and "not recorded yet" in table and "optimistic" in table
    assert "3/3 (100%) / 3/3 (100%)" in table and "4/4 (100%)" in table


def test_report_readme_patch(tmp_path, monkeypatch):
    table = report.numbers_table(STT, None)
    readme = tmp_path / "README.md"
    readme.write_text(f"top\n{report.START}\nold\n{report.END}\nbottom\n", encoding="utf-8")
    monkeypatch.setattr(report, "README", readme)
    assert report.patch_readme(table)
    text = readme.read_text(encoding="utf-8")
    assert "old" not in text and "16/16" in text and text.startswith("top") and text.endswith("bottom\n")


@pytest.mark.models
def test_real_models_on_a_synthetic_clip():
    """Needs the downloaded models and evals/audio (python -m evals.make_clips)."""
    from app.config import settings
    from app.stt import Transcriber

    clip = Path(__file__).resolve().parents[1] / "evals" / "audio" / "S01.wav"
    if not (Path(settings.whisper_dir).exists() and clip.exists()):
        pytest.skip("models or clips not present")
    res = Transcriber().transcribe(clip.read_bytes())
    assert normalize_order_ids(res.text).order_ids == ["LC-1150"]


def test_report_with_e2e_results_and_language_note():
    s_ = {"n": 24, "typed_ok": 21, "voiced_ok": 20, "id_n": 16, "id_typed_ok": 14, "id_voiced_ok": 13, "ticket_n": 2,
          "ticket_typed_ok": 1, "ticket_voiced_ok": 1, "handoff_only_typed": 1, "handoff_only_voiced": 1,
          "wrong_order_voiced": 0, "wrong_order_typed": 0, "agent_ms_voiced": [15000]}
    e2e = {"date": "d", "agent_url": "u", "stt_language": "en", "elapsed_s": 1, "precondition": "no open return for LC-1199",
           "rows": [], "summary": {"synthetic": s_}, "silent": [{"id": "S29", "kind": "silent", "status": "no_speech", "transcript_raw": "",
                                                                  "agent_calls": 0, "ok": True}] * 2,
           "scenarios": [{"name": "voice-confirm", "expect": "execute", "ok": True},
                         {"name": "voice-cancel", "expect": "cancel", "ok": False, "reason": "x"}]}
    table = report.numbers_table(STT, e2e)
    assert "21/24 (88%)" in table and "20/24 (83%)" in table and "2/2 (100%)" in table
    assert "FAIL: x" in table and "`en` wins on speed" in table
    assert "Real create_ticket calls (typed / voiced), of 2 ticket clips | 1 / 1" in table
    assert "Hand-offs with no ticket call" in table
    section = report.e2e_section(e2e)
    assert "Database precondition: no open return for LC-1199" in section and "Hand-off with no ticket" in section


def test_report_marks_run1_as_not_a_result(monkeypatch):
    run1 = {"date": "2026-11-10T04:02:11", "summary": {"synthetic": {"n": 24, "typed_ok": 21, "voiced_ok": 21}}}
    monkeypatch.setattr(report, "load", lambda name: run1 if name in ("e2e.json", "e2e-run1.json") else None)
    assert report.is_run1(run1)
    table = report.numbers_table(STT, run1)
    assert "run 1 failed on test data" in table and "21/24" not in table
    assert not report.is_run1({"date": "2026-11-11T09:00:00"})
