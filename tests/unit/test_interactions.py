# ruff: noqa: E501
"""Grounded answers over notes and calls: access first, citations always, refusal when nothing says it. Runs on a tiny index
built in a temp folder; no network, no warehouse, no model."""

from datetime import datetime

import duckdb
import pytest

from common import ask_scope
from common.config import get_settings
from rag import interactions as it
from rag import search_index as si

ROWS = [
    # source, doc_id, case, golden, contact, call_key, ts, speaker, turn, note_type, text
    ("note", "N-1", "CS-1", "G-1", "CT-1", None, datetime(2026, 8, 1), "agent", 1, "call_note",
     "spoke w/ cust. disputes late fee, says paid in app on time. dispute opened"),
    ("transcript", "100", "CS-1", "G-1", "CT-2", "100", datetime(2026, 8, 5), "customer", 7, None,
     "I lost my job in June and my hours were cut."),
    ("transcript", "100", "CS-1", "G-1", "CT-2", "100", datetime(2026, 8, 5), "agent", 8, None,
     "If you are having a hardship we have options."),
    ("transcript", "100", "CS-1", "G-1", "CT-2", "100", datetime(2026, 8, 5), "customer", 9, None,
     "I can pay 250 the 15th. I promise."),
    ("voice", "VS-100", "CS-1", "G-1", "CT-2", "100", datetime(2026, 8, 5), "customer", 3, None,
     "i lost my job in june and my hours were cut"),
    ("note", "N-2", "CS-2", "G-2", "CT-3", None, datetime(2026, 8, 2), "agent", 1, "call_note",
     "customer says she wants to dispute the fraud charge on the card"),
]


@pytest.fixture
def index(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    con = duckdb.connect(str(si.path()))
    con.execute("""CREATE TABLE interactions(uid BIGINT, source VARCHAR, doc_id VARCHAR, case_id VARCHAR, golden_id VARCHAR,
                   contact_id VARCHAR, call_key VARCHAR, ts TIMESTAMP, speaker VARCHAR, turn_index INTEGER,
                   note_type VARCHAR, text VARCHAR)""")
    for i, r in enumerate(ROWS, 1):
        con.execute("INSERT INTO interactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [i, *r])
    si.build_inverted(con)
    con.close()
    return tmp_path


def scope(role, allowed):
    return ask_scope.AskScope(role=role, case_allowed=lambda c: c in allowed, user_id="u")


def test_agent_only_sees_their_own_cases(index):
    s = scope("agent", {"CS-1"})
    hits = it.search("did the customer dispute anything", s)
    assert hits and {h["case_id"] for h in hits} == {"CS-1"}
    assert it.search("did the customer dispute anything", s, case_id="CS-2") == []
    assert it.search("dispute", s, golden_id="G-2") == []


def test_team_lead_and_batch_scope(index):
    assert {h["case_id"] for h in it.search("dispute", scope("team_lead", {"CS-1", "CS-2"}))} == {"CS-1", "CS-2"}
    assert {h["case_id"] for h in it.search("dispute", None)} == {"CS-1", "CS-2"}


def test_analyst_gets_nothing_and_a_clear_reason(index):
    s = ask_scope.AskScope(role="analyst", case_allowed=lambda c: False)
    assert it.search("dispute", s) == [] and it.search("dispute", s, case_id="CS-1") == []
    a = it.answer("did the customer dispute anything", s, case_id="CS-1")
    assert a["refused"] and not a["citations"]


def test_answer_cites_a_retrieved_snippet_word_for_word(index):
    a = it.answer("What did the customer say about the late fee?", None, case_id="CS-1")
    assert not a["refused"] and a["citations"]
    snips = {(h["doc_id"], h["turn_index"]): h["text"] for h in it.search("late fee", None, case_id="CS-1")}
    for c in a["citations"]:
        assert it._norm(c["quote"]) in it._norm(snips[(c["doc_id"], c["turn_index"])])
        assert {"source", "doc_id", "case_id", "contact_id", "turn_index", "ts", "speaker", "quote", "label"} <= set(c)


def test_customer_questions_skip_agent_script_lines(index):
    hits = it.search("has the customer mentioned hardship", None, case_id="CS-1")
    assert hits and all(h["speaker"] != "agent" or h["source"] == "note" for h in hits)


def test_no_evidence_is_refused(index):
    a = it.answer("What did the customer say about their cat?", None, case_id="CS-1")
    assert a["refused"] and a["answer"] is None and a["citations"] == []
    assert a["refusal_reason"] == "Nothing in the notes or calls says that."


def test_last_promise_is_the_most_recent_one(index):
    a = it.answer("When did the customer last promise to pay?", None, case_id="CS-1")
    assert not a["refused"] and "250" in a["answer"]


def test_summary_of_recent_interactions_cites_each_one(index):
    a = it.answer("Summarise the last three interactions", None, case_id="CS-1")
    assert not a["refused"] and {c["source"] for c in a["citations"]} >= {"note", "transcript"}


def test_voice_only_search(index):
    hits = it.search("lost job", None, case_id="CS-1", sources=("voice",))
    assert hits and {h["source"] for h in hits} == {"voice"}


def test_protected_and_pii_text_is_scrubbed_at_build_time():
    con = duckdb.connect()
    for raw, gone in [("spoke to customer - mentioned their religion - dispute opened", "religion"),
                      ("mentioned being pregnant, sent link", "pregnant"), ("mentioned attedning church on Sundays", "church"),
                      ("card 4520 1667 1426 5915 please", "4520"), ("May I speak with Joyce Gay?", "Joyce")]:
        out = con.execute(f"SELECT {si._sql_clean('?')}", [raw]).fetchone()[0]
        assert gone not in out, out
    assert "dispute opened" in con.execute(f"SELECT {si._sql_clean('?')}", ["x - mentioned their religion - dispute opened"]).fetchone()[0]


def _llm(monkeypatch, out):
    import common.llm_mode as lm
    import llm.client as client

    monkeypatch.setattr(lm, "effective_provider", lambda: "gemini")
    calls = []
    monkeypatch.setattr(client, "complete_json", lambda *a, **k: calls.append(a) or {**out, "_meta": {"provider": "gemini"}})
    return calls


def _ref_for(question, doc, turn):
    for i, h in enumerate(it.search(question, None, case_id="CS-1"), 1):
        if (h["doc_id"], h["turn_index"]) == (doc, turn):
            return f"S{i}"
    raise AssertionError("snippet not retrieved")


def test_model_answer_is_accepted_only_when_grounded(index, monkeypatch):
    q = "What did the customer say about the late fee?"
    good = {"answer": "The customer disputes the late fee and says they paid on time.", "refused": False, "refusal_reason": None,
            "citations": [{"ref": _ref_for(q, "N-1", 1), "doc_id": "N-1", "turn_index": 1,
                           "quote": "disputes late fee, says paid in app on time"}]}
    calls = _llm(monkeypatch, good)
    a = it.answer(q, None, case_id="CS-1")
    assert calls and a["by_llm"] and a["citations"][0]["quote"] == "disputes late fee, says paid in app on time"

    invented = {**good, "citations": [{**good["citations"][0], "quote": "customer threatened legal action"}]}
    _llm(monkeypatch, invented)
    a = it.answer(q, None, case_id="CS-1")
    assert not a["by_llm"] and not a["refused"]  # fell back to the extractive answer

    wrong_number = {**good, "answer": "The customer disputes a $75 late fee."}
    _llm(monkeypatch, wrong_number)
    assert not it.answer(q, None, case_id="CS-1")["by_llm"]

    _llm(monkeypatch, {**good, "citations": []})
    assert not it.answer(q, None, case_id="CS-1")["by_llm"]


def test_model_is_not_called_when_nothing_is_retrieved_or_not_allowed(index, monkeypatch):
    calls = _llm(monkeypatch, {"answer": "x", "citations": [], "refused": False, "refusal_reason": None})
    assert it.answer("What did the customer say about their cat?", None, case_id="CS-1")["refused"]
    assert it.answer("dispute", scope("agent", set()), case_id="CS-1")["refused"]
    assert not calls


def test_offline_handler_is_registered():
    from llm.client import complete_json

    out = complete_json("interaction_answer", 1, {"question": "x", "snippets": []}, "interaction_answer", provider="offline")
    assert out["refused"] is True
