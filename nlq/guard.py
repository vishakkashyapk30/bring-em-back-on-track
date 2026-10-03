"""SQL guard: defence in depth on top of read-only role views."""

from __future__ import annotations

import sqlglot
from sqlglot import exp

from common.protected import find_forbidden

FORBIDDEN_FUNCS = {
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto", "read_text", "read_blob",
    "glob", "httpfs", "sniff_csv", "query_table", "query",
}
DEFAULT_LIMIT = 1000


class GuardError(ValueError):
    pass


def validate(sql: str, allowed_views: set[str], max_limit: int = DEFAULT_LIMIT) -> str:
    """Return safe SQL (LIMIT enforced) or raise GuardError.

    Checks: exactly one SELECT; only allowed views; no file/network functions; no protected columns;
    a LIMIT no larger than max_limit (added if missing).
    """
    try:
        stmts = sqlglot.parse(sql, read="duckdb")
    except sqlglot.errors.ParseError as e:
        raise GuardError(f"Could not parse SQL: {e}") from e
    if len(stmts) != 1 or stmts[0] is None:
        raise GuardError("Exactly one statement is allowed")
    tree = stmts[0]
    if not isinstance(tree, (exp.Select, exp.Union, exp.Subquery)) or tree.find(
        exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Copy
    ):
        raise GuardError("Only SELECT queries are allowed")

    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    allowed = {v.lower() for v in allowed_views}
    allowed_bare = {v.split(".")[-1] for v in allowed}
    for t in tree.find_all(exp.Table):
        name = t.name.lower()
        full = ".".join(p for p in (t.db, t.name) if p).lower()
        if name in ctes:
            continue
        if not name:  # table functions such as read_csv(...)
            raise GuardError("Table functions are not allowed")
        if full not in allowed and name not in allowed_bare:
            raise GuardError(f"Table '{full}' is not available for your role")

    for f in tree.find_all(exp.Func):
        fname = (f.sql_name() if not isinstance(f, exp.Anonymous) else f.name).lower()
        if fname in FORBIDDEN_FUNCS:
            raise GuardError(f"Function '{fname}' is not allowed")

    bad = find_forbidden(c.name for c in tree.find_all(exp.Column))
    if bad:
        raise GuardError(f"Protected attributes can't be queried: {sorted(bad)}")

    limit = tree.args.get("limit")
    if limit is None:
        tree = tree.limit(max_limit)
    else:
        try:
            n = int(limit.expression.name)
        except (AttributeError, ValueError) as e:
            raise GuardError("LIMIT must be a number") from e
        if n > max_limit:
            tree = tree.limit(max_limit)
    return tree.sql(dialect="duckdb")


def agent_row_filters(user_id: str) -> dict[str, str]:
    """Row filters for the agent role (V1 §4 step 3): an agent only ever sees cases assigned to them."""
    uid = "".join(ch for ch in user_id if ch.isalnum() or ch in "-_")
    pred = f"assigned_agent_id = '{uid}'"
    return {"collections_cases": pred, "c360_case": pred}


def apply_row_filters(safe_sql: str, filters: dict[str, str]) -> tuple[str, bool]:
    """Wrap every filtered table in a sub-select that carries the user's row filter, so nothing in the user's own
    WHERE (an `OR 1=1`, a filter on another agent) can widen the rows. Run it on SQL that already passed `validate`
    and the column checks. Returns (sql, applied)."""
    tree = sqlglot.parse_one(safe_sql, read="duckdb")
    ctes = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    applied = False
    for t in list(tree.find_all(exp.Table)):
        name = t.name.lower()
        if name in ctes or name not in filters:
            continue
        source = t.copy()
        source.set("alias", None)
        inner = exp.select("*").from_(source).where(filters[name])
        alias = t.alias or t.name
        t.replace(exp.Subquery(this=inner, alias=exp.TableAlias(this=exp.to_identifier(alias))))
        applied = True
    return tree.sql(dialect="duckdb"), applied
