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
