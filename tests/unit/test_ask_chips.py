"""Ask chip editing: the answer is compiled from the edited chips by the certified compiler."""

from datetime import date

import pytest

from semantic.compiler import ChipError, compile_question

AS_OF = date(2026, 9, 30)
Q = "Which strategy worked best for unsecured loans in the last 90 days?"


def test_edited_time_and_dimensions_change_the_sql():
    c = compile_question(Q, AS_OF, chips={"metric": "cure_rate", "dimensions": ["province"], "filters": [],
                                         "time": "last 30 days"})
    assert c.time_label == "last 30 days" and c.dimensions == ["province"] and "province_code" in c.sql
    assert "primary_product" not in c.sql


def test_unknown_metric_dimension_filter_or_period_is_refused():
    base = {"metric": "cure_rate", "dimensions": [], "filters": [], "time": None}
    for bad in ({"metric": "salary; drop table x"}, {"dimensions": ["ssn"]}, {"filters": ["1=1 OR c.x = 1"]},
                {"time": "whenever"}):
        with pytest.raises(ChipError):
            compile_question(Q, AS_OF, chips={**base, **bad})


def test_chips_through_the_pipeline_respect_the_scope():
    from common.ask_scope import AskScope, use_scope
    from nlq.pipeline import ask

    with use_scope(AskScope(allow_metrics=False)):
        a = ask(Q, None, {"metric": "cure_rate", "dimensions": [], "filters": [], "time": "last 30 days"})
    assert a.refused
