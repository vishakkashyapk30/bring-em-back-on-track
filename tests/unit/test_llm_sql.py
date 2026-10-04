"""Language-model SQL for Ask (nlq/llm_sql.py): only with a model in use, never for agents, every query guarded,
retried at most twice, labelled as not certified, and an insight that may only use numbers from the rows.
No test touches the network: the model is a fake that replaces llm.client.complete_json."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from common import ask_scope, llm_mode
from common.config import get_settings
from common.protected import FORBIDDEN
from nlq import llm_sql, pipeline
from nlq.executor import PII_COLUMNS

ROOT = Path(__file__).resolve().parents[2]
needs_warehouse = pytest.mark.skipif(not (ROOT / "data" / "warehouse.duckdb").exists(), reason="no warehouse built")
AS_OF = date(2026, 9, 28)
# Not covered by any certified metric, so Ask reaches the language-model SQL step.
UNCOVERED = "What is the average talk time of answered outbound calls by queue in August 2026?"
GOOD_SQL = ("SELECT c.queue, round(avg(h.talk_duration_sec), 1) AS avg_talk_sec, count(*) AS calls "
            "FROM contact_history h JOIN collections_cases c ON c.case_id = h.case_id "
            "WHERE coalesce(h.channel_v2, h.channel) = 'call' AND h.direction = 'outbound' "
            "AND h.dial_result = 'answered' AND CAST(h.contact_ts_local AS DATE) "
            "BETWEEN DATE '2026-08-01' AND DATE '2026-08-31' GROUP BY 1 ORDER BY 1")


class FakeModel:
    """Stands in for llm.client.complete_json: returns the queued SQL replies in order, then a fixed insight."""

    def __init__(self, sqls: list[str], insight: str | None = None):
        self.sqls, self.insight, self.calls = list(sqls), insight, []

    def __call__(self, prompt_id, version, inputs, schema_name, provider=None):
        self.calls.append((prompt_id, inputs))
        meta = {"_meta": {"provider": "fake", "prompt_id": prompt_id, "version": version}}
        if prompt_id == "nl_to_sql":
            sql = self.sqls.pop(0) if self.sqls else ""
            return {"sql": sql, "tables": [], "explanation": "average talk time by queue", "confidence": 0.8, **meta}
        if prompt_id == "ask_insight":
            return {"insight": self.insight or "", "numbers_used": [], **meta}
        if prompt_id == "question_rewrite":
            return {"measure": "", "metric_id": None, "reason": "none", **meta}
        # any other prompt (policy wording...) gets its offline answer
        from llm.providers.offline import OfflineProvider

        return {**OfflineProvider().complete_json(prompt_id, "", inputs, {}), "_meta": {"provider": "offline"}}

    def sql_calls(self):
        return [i for p, i in self.calls if p == "nl_to_sql"]


@pytest.fixture
def model(monkeypatch):
    """A fake model behind a provider that is not offline (no network: complete_json itself is replaced)."""
    import llm.client as client

    monkeypatch.setattr(get_settings(), "llm_provider", "ollama")

    def install(sqls, insight=None):
        fake = FakeModel(sqls, insight)
        monkeypatch.setattr(client, "complete_json", fake)
        return fake

    return install


def _boom(*_a, **_k):
    raise AssertionError("the model must not be called")


# When the path runs at all

def test_offline_handler_says_cannot():
    out = llm_sql.nl_to_sql_offline({"question": "x"})
    assert out["sql"] == "" and out["explanation"].startswith("cannot")


def test_offline_provider_skips_the_path_and_never_calls_a_model(monkeypatch):
    import llm.client as client

    monkeypatch.setattr(get_settings(), "llm_provider", "offline")
    monkeypatch.setattr(client, "complete_json", _boom)
    assert not llm_sql.enabled()
    assert llm_sql.generate_and_run(UNCOVERED, AS_OF).status == "unavailable"


@needs_warehouse
def test_offline_ask_still_refuses_an_uncovered_data_question(monkeypatch):
    monkeypatch.setattr(get_settings(), "llm_provider", "offline")
    monkeypatch.setattr(llm_sql, "generate", _boom)
    a = pipeline.ask(UNCOVERED)
    assert a.refused and not a.generated


def test_rules_mode_never_calls_the_model(model, monkeypatch):
    fake = model([GOOD_SQL])
    with llm_mode.use_mode("rules"):
        assert not llm_sql.enabled()
        assert llm_sql.generate_and_run(UNCOVERED, AS_OF).status == "unavailable"
    assert fake.calls == []


@pytest.mark.parametrize("mode", ["llm", None])
def test_agents_never_reach_the_model(model, mode):
    fake = model([GOOD_SQL])
    scope = ask_scope.AskScope(allow_metrics=False, user_id="AG-1187", role="agent")
    with ask_scope.use_scope(scope), llm_mode.use_mode(mode):
        a = pipeline.ask(UNCOVERED)
    assert a.refused and fake.calls == []


def test_refusal_rules_run_before_the_model(model):
    fake = model(["SELECT count(*) AS n FROM collections_cases c"])
    for q in ("List the gender and marital status of customers who broke a promise last month.",
              "Export the names and phone numbers of every customer in Ontario.",
              "Delete all the broken promises from the table.",
              "Forecast the number of broken promises next month by queue."):
        assert pipeline.ask(q).refused
    assert fake.calls == []


@needs_warehouse
def test_certified_metric_wins_over_generated_sql(model):
    fake = model([GOOD_SQL])
    a = pipeline.ask("How many collections cases are open today, by current bucket?")
    assert not a.generated and a.chips["metric"] == "open_case_count" and fake.sql_calls() == []


# A generated answer

@needs_warehouse
def test_generated_answer_is_labelled_cited_and_guarded(model):
    fake = model([GOOD_SQL], insight=None)
    a = pipeline.ask(UNCOVERED)
    assert not a.refused and a.generated and a.kind == "metric"
    assert a.answered_by == "language model" and a.chips["certified"] is False
    assert a.caveats[0] == llm_sql.CAVEAT
    assert "LIMIT" in a.sql_or_sources and a.columns == ["queue", "avg_talk_sec", "calls"] and a.rows
    kinds = [c["kind"] for c in a.citations]
    assert kinds[0] == "sql" and a.citations[0]["ref"] == a.sql_or_sources
    assert {c["doc_id"] for c in a.citations if c["kind"] == "table"} == {"contact_history", "collections_cases"}
    assert all({"doc_id", "section", "quote", "kind", "ref", "label"} <= set(c) for c in a.citations)
    # the model saw the schema pack and the question, and nothing about customers
    inputs = fake.sql_calls()[0]
    assert inputs["question"] == UNCOVERED and "TABLE collections_cases" in inputs["schema"]


@needs_warehouse
def test_insight_with_numbers_from_the_rows_is_kept(model):
    fake = model([GOOD_SQL])
    res = llm_sql.generate_and_run(UNCOVERED, AS_OF)
    q, v = res.rows[0][0], res.rows[0][1]
    fake.insight = f"The {q} queue averaged {v} seconds of talk time."
    text, by_model = llm_sql.write_insight(UNCOVERED, res.sql, res.columns, res.rows)
    assert by_model and text == fake.insight


@needs_warehouse
def test_insight_with_an_invented_number_is_dropped(model):
    model([GOOD_SQL], insight="Talk time rose 37.25% against last year.")
    a = pipeline.ask(UNCOVERED)
    assert a.generated and a.insight == llm_sql.template_insight(a.rows)
    assert any("template" in c for c in a.caveats)


# Retries and refusals

@needs_warehouse
def test_error_is_sent_back_and_the_second_attempt_answers(model):
    bad = "SELECT c.queue, avg(c.agency_name) AS x FROM collections_cases c GROUP BY 1"   # hidden column
    fake = model([bad, GOOD_SQL])
    res = llm_sql.generate_and_run(UNCOVERED, AS_OF)
    assert res.status == "answered" and res.calls == 2
    retry = fake.sql_calls()[1]["previous_attempts"]
    assert retry[0]["sql"] == bad and "agency_name" in retry[0]["error"]


@needs_warehouse
def test_gives_up_after_two_retries(model):
    fake = model(["SELECT c.queue, count(*) AS n FROM no_such_table c GROUP BY 1"] * 5)
    a = pipeline.ask(UNCOVERED)
    assert a.refused and a.refusal_reason == llm_sql.GIVE_UP and len(fake.sql_calls()) == llm_sql.MAX_ATTEMPTS


@needs_warehouse
@pytest.mark.parametrize("sql", [
    "SELECT d.ccb_deposit_flag, count(*) AS n FROM deposit_accounts d GROUP BY 1",           # protected
    "SELECT a.agent_display_name, count(*) AS n FROM agents a GROUP BY 1",                    # personal (dictionary)
    "SELECT h.sms_reply_text, count(*) AS n FROM contact_history h GROUP BY 1",               # personal (dictionary)
    "SELECT p.first_name, count(*) AS n FROM promises_to_pay p GROUP BY 1",                   # personal (executor)
    "SELECT c.queue, count(*) AS gender_code FROM collections_cases c GROUP BY 1",            # protected name as alias
])
def test_protected_or_personal_columns_are_refused_without_retry(model, monkeypatch, sql):
    import nlq.executor as ex

    monkeypatch.setattr(ex, "execute", _boom)
    fake = model([sql, GOOD_SQL])
    res = llm_sql.generate_and_run(UNCOVERED, AS_OF)
    assert res.status == "refused" and len(fake.sql_calls()) == 1
    assert res.reason.startswith("Refused:")


@needs_warehouse
@pytest.mark.parametrize("sql, needle", [
    ("DELETE FROM promises_to_pay", "Only SELECT"),
    ("SELECT 1 AS a; DROP TABLE agents", "Exactly one statement"),
    ("SELECT c.case_id, c.total_overdue FROM collections_cases c", "aggregates only"),
    ("SELECT c.case_id, count(*) AS n FROM collections_cases c GROUP BY 1", "aggregates only"),
    ("SELECT * FROM agents", "SELECT *"),
    ("SELECT count(*) AS n FROM read_csv('/etc/passwd')", "not allowed"),
    ("SELECT k.golden_id, count(*) AS n FROM c360_customer k GROUP BY 1", "not available"),
    ("SELECT g.fsa, count(*) AS n FROM geo_reference g GROUP BY 1", "not available"),    # postal areas: not in pack
    ("SELECT c.queue, count(*) AS n FROM collections_cases c, customers k GROUP BY 1", "not available"),
])
def test_unsafe_sql_is_rejected_before_it_runs(sql, needle):
    from nlq.schema_pack import build

    with pytest.raises(llm_sql.Rejected) as e:
        llm_sql.check_sql(sql, build(AS_OF))
    assert needle in str(e.value)


@needs_warehouse
def test_reference_tables_may_be_listed_and_a_limit_is_added():
    from nlq.schema_pack import build

    safe = llm_sql.check_sql("SELECT h.program_name, h.duration_months FROM hardship_programs h", build(AS_OF))
    assert "LIMIT 1000" in safe


@needs_warehouse
def test_slow_query_is_interrupted(monkeypatch):
    monkeypatch.setattr(llm_sql, "TIMEOUT_S", 0.05)
    sql = ("SELECT count(*) AS n FROM contact_history a JOIN contact_history b ON a.agent_id = b.agent_id "
           "WHERE a.contact_cost_cad > b.contact_cost_cad")
    with pytest.raises(llm_sql.Rejected) as e:
        llm_sql.run(sql)
    assert "longer than" in str(e.value)


def test_small_counts_are_suppressed():
    rows, hit = llm_sql.suppress_small_counts("SELECT q, count(*) AS n, avg(x) AS a FROM t GROUP BY 1",
                                              ["q", "n", "a"], [("x", 3, 1.5), ("y", 40, 2.0)])
    assert hit and rows[0][1] == "<10" and rows[1][1] == 40


# The schema pack

@needs_warehouse
def test_schema_pack_never_shows_protected_or_personal_columns():
    from nlq.schema_pack import blocked_columns, build

    pack = build(AS_OF)
    shown = {c.lower() for c in pack.visible}
    assert not shown & {c.lower() for c in FORBIDDEN}
    assert not shown & {c.lower() for c in PII_COLUMNS}
    assert not shown & blocked_columns()
    text = pack.text()
    for c in FORBIDDEN | PII_COLUMNS | {"agent_display_name", "card_number_masked", "fsa_income_index"}:
        assert f"  {c} " not in text
    assert "outcome IS NULL" in text and str(AS_OF) in text and "customers" not in pack.tables


def test_agents_get_an_empty_pack():
    from nlq.schema_pack import tables_for_role

    assert tables_for_role("agent") == () and "collections_cases" in tables_for_role("analyst")


# Number verification

@pytest.mark.parametrize("text, ok", [
    ("mid_stage has 1,234 calls at 12.4%.", True),
    ("mid_stage has about 1.2 thousand calls.", True),
    ("The share is 12%.", True),                       # 12.4 rounded to whole percent
    ("The share is 13%.", False),
    ("The share is 12.46%.", False),                   # more precision than the rows
    ("late_stage has 1,234 calls.", True),
    ("A 50% jump.", False),
    ("The total_exposure column is high.", False),     # a column that is not in the result
    ("There are 2 queues in August 2026.", True),      # row count and the question's own numbers
])
def test_verify_insight(text, ok):
    rows = [["mid_stage", 1234, 12.4], ["late_stage", 88, 0.3]]
    assert llm_sql.verify_insight(text, "How many calls in August 2026?", ["queue", "calls", "share_pct"], rows) is ok


def test_empty_result_has_no_numbers_and_no_model_call(model):
    fake = model([])
    text, by_model = llm_sql.write_insight("q", "SELECT 1", ["n"], [])
    assert not by_model and not any(ch.isdigit() for ch in text) and fake.calls == []
