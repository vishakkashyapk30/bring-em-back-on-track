import pytest

from nlq.guard import GuardError, validate

VIEWS = {"gold.role_analyst_metrics_v"}


def test_select_gets_limit():
    out = validate("select province_code, count(*) from gold.role_analyst_metrics_v group by 1", VIEWS)
    assert "LIMIT 1000" in out


@pytest.mark.parametrize("sql", [
    "delete from gold.role_analyst_metrics_v",
    "select * from gold.c360_customer",
    "select * from read_csv('/etc/passwd')",
    "select gender_code from gold.role_analyst_metrics_v",
    "select 1; select 2",
])
def test_rejects_unsafe(sql):
    with pytest.raises(GuardError):
        validate(sql, VIEWS)


def test_caps_large_limit():
    assert "LIMIT 1000" in validate("select * from gold.role_analyst_metrics_v limit 999999", VIEWS)


def test_agent_row_filter_cannot_be_widened():
    from nlq.guard import agent_row_filters, apply_row_filters, validate

    safe = validate("SELECT case_id FROM collections_cases WHERE assigned_agent_id = 'agent-002' OR 1=1",
                    {"collections_cases"})
    sql, applied = apply_row_filters(safe, agent_row_filters("agent-001"))
    assert applied
    assert "(SELECT * FROM collections_cases WHERE assigned_agent_id = 'agent-001') AS collections_cases" in sql
    # a user id with quotes cannot break out of the filter
    sql2, _ = apply_row_filters(safe, agent_row_filters("a'; DROP TABLE x;--"))
    assert "DROP" in sql2 and "'aDROPTABLEx--'" in sql2
