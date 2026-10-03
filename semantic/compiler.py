"""Compile a plain-English metric question into SQL over the semantic registry (no LLM).

question -> (metric, dimensions, filters, time range) -> one SELECT over the typed silver tables, using the
certified metric definition. Returns None when the question doesn't map to a certified metric (the pipeline then
tries documents or refuses). Special templates: roll rate between two quarter-ends, period-vs-previous-period
comparisons, and a ranked list of open promises by the bank's break-risk score.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta

from nlq.timeparse import MON, TimeRange, _month, _month_end, parse
from semantic.registry import DIMENSIONS, FILTERS, METRICS, Metric, find


@dataclass
class Compiled:
    sql: str
    metric_id: str
    dimensions: list[str] = field(default_factory=list)
    filters: list[str] = field(default_factory=list)
    time_label: str | None = None
    time_range: TimeRange | None = None
    caveats: list[str] = field(default_factory=list)


class NoMetricMatch(Exception):
    pass


def _time_condition(col: str, tr: TimeRange) -> str:
    if col.endswith("_ts_local") or col.endswith("_ts"):
        return f"{col} >= TIMESTAMP '{tr.start}' AND {col} < TIMESTAMP '{tr.end + timedelta(days=1)}'"
    return f"{col} BETWEEN DATE '{tr.start}' AND DATE '{tr.end}'"


POLICY_MODAL = re.compile(r"\b(can we|may we|are we allowed|allowed to|permitted|maximum|minimum|limit)\b", re.I)


def _pick_metric(q: str) -> Metric | None:
    for m in METRICS:
        if m.id == "contact_count" and POLICY_MODAL.search(q):
            continue
        if m.id.endswith("_count") and re.search(r"\b(share|percent\w*|proportion|rate|fraction|ratio)\b", q, re.I):
            continue  # a count metric must not hijack a question that asks for a rate
        if find(m.patterns, q):
            return m
    return None


def _roll_rate(q: str, as_of: date) -> Compiled | None:
    if not re.search(r"\broll(ed|ing)?\b|roll rate|worse bucket", q, re.I):
        return None
    ends = re.findall(rf"end of {MON}\w* (\d{{4}})", q.lower())
    if len(ends) < 2:
        bt = re.search(rf"between {MON}\w*(?: (\d{{4}}))? and {MON}\w* (\d{{4}})", q.lower())
        if not bt:
            return None
        ends = [(bt.group(1), bt.group(2) or bt.group(4)), (bt.group(3), bt.group(4))]
    (m1, y1), (m2, y2) = ends[0], ends[1]
    d1, d2 = _month_end(int(y1), _month(m1)), _month_end(int(y2), _month(m2))
    b = re.search(r"(\d+)\s*-\s*(\d+) (?:days past due|bucket)", q)
    lo, hi = (int(b.group(1)), int(b.group(2))) if b else (1, 30)
    by_product = re.search(r"\bproducts?\b", q, re.I)
    dim = "a.product_type, " if by_product else ""
    # Certified roll-rate definition: snapshot dates parsed with the three formats of the metric owner's
    # reference query (rows in MM/DD/YYYY are left out, as in the certified figure; see the data quality report).
    snap = ("(SELECT account_id, product_type, dpd, coalesce(try_strptime(month_end_date, '%Y-%m-%d'), "
            "try_strptime(month_end_date, '%d/%m/%Y'), try_strptime(month_end_date, '%Y%m%d'))::DATE AS me "
            "FROM account_monthly_snapshot WHERE dpd IS NOT NULL)")
    sql = (f"SELECT {dim}round(100.0 * avg(CASE WHEN b.dpd > {hi} THEN 1 ELSE 0 END), 1) AS roll_rate_pct, "
           f"count(*) AS accounts FROM {snap} a JOIN {snap} b "
           f"ON a.account_id = b.account_id AND b.me = DATE '{d2}' "
           f"WHERE a.me = DATE '{d1}' AND a.dpd BETWEEN {lo} AND {hi}"
           + (" GROUP BY 1 ORDER BY 1" if by_product else ""))
    return Compiled(sql, "roll_rate", ["product"] if by_product else [], [f"dpd {lo}-{hi} at {d1}"],
                    f"{d1} to {d2}", None,
                    ["Snapshot dates arrive in several formats; parsed before comparing.",
                     "dpd is missing for some snapshot rows; those accounts are excluded."])


def _ptp_break_list(q: str, as_of: date) -> Compiled | None:
    if not re.search(r"(most likely|likely|risk) to break|break(ing)? a promise .*(most|likely)|highest break", q, re.I):
        return None
    tr = parse(q, as_of) or TimeRange(as_of, as_of + timedelta(days=6), "next 7 days")
    sql = ("SELECT p.ptp_id, k.golden_id, p.product, p.ptp_amount, p.ptp_due_date, round(s.score, 2) AS break_probability "
           "FROM promises_to_pay p JOIN model_scores s ON s.ptp_id = p.ptp_id AND s.model_name = 'ptp_break' "
           "LEFT JOIN c360_case k ON k.case_id = p.case_id "
           f"WHERE p.ptp_status = 'open' AND p.ptp_due_date BETWEEN DATE '{tr.start}' AND DATE '{tr.end}' "
           "ORDER BY break_probability DESC LIMIT 10")
    return Compiled(sql, "ptp_break_list", [], ["open promises"], tr.label, tr,
                    ["Break probability is the bank's ptp_break v2.1 score (a model estimate)."])


def compile_question(question: str, as_of: date, force_metric: str | None = None) -> Compiled | None:
    """`force_metric` is a certified metric id chosen by the optional LLM step; everything else (breakdowns, filters,
    period) is still read from the question by the rules."""
    q = question
    if not force_metric:
        for special in (_roll_rate, _ptp_break_list):
            c = special(q, as_of)
            if c:
                return c
    metric = next((m for m in METRICS if m.id == force_metric), None) if force_metric else _pick_metric(q)
    if metric is None:
        return None
    alias = metric.alias
    dims = [d for d in DIMENSIONS if find(d.patterns, q) and alias in d.expr]
    ids = {d.id for d in dims}
    # prefer the most specific dimension when several overlap
    drop = set()
    if ids & {"card_product", "primary_product"}:
        drop.add("product")
    if "test_cell" in ids:
        drop.add("strategy")
    if "prior_broken" in ids:
        drop.add("product")
    dims = [d for d in dims if d.id not in drop]
    joins: list[str] = []
    where = [w.replace("{as_of}", str(as_of)) for w in metric.where]
    filters = []
    chan_words = [w for w in (r"\bcalls?\b", r"\b(sms|text messages?|texts)\b", r"\bemails?\b") if re.search(w, q, re.I)]
    compare_channels = alias == "h" and len(chan_words) >= 2
    if compare_channels and "channel" not in ids:
        dims.append(next(d for d in DIMENSIONS if d.id == "channel"))
        ids.add("channel")
    for pattern, conds, fjoins in FILTERS:
        if compare_channels and pattern in (r"\bcalls?\b", r"\b(sms|text messages?|texts)\b", r"\bemails?\b"):
            continue
        if re.search(pattern, q, re.I) and alias in conds:
            cond = conds[alias]
            if cond not in where:
                where.append(cond)
                filters.append(cond)
            if alias in fjoins and fjoins[alias] not in joins:
                joins.append(fjoins[alias])
    bm = re.search(r"(\d+\s*-\s*\d+|\d+\+)\s*(?:days?\s*)?(?:past due\s*)?bucket", q, re.I)
    if bm and alias in ("c", "p", "h"):
        val = re.sub(r"\s+", "", bm.group(1)).lower()
        bucket = next(d for d in DIMENSIONS if d.id == "current_bucket")
        col = bucket.expr[alias]
        if alias in bucket.joins and bucket.joins[alias] not in joins:
            joins.append(bucket.joins[alias])
        where.append(f"{col} = '{val}'")
        filters.append(f"bucket {val}")
    for d in dims:
        j = d.joins.get(alias)
        if j and j not in joins:
            joins.append(j)
    select_dims = [f"{d.expr[alias]} AS {d.id}" for d in dims]
    unsupported = [d.id for d in DIMENSIONS if find(d.patterns, q) and alias not in d.expr and d.id not in ids]
    tr = parse(q, as_of) if metric.time_col else None
    caveats = []
    if metric.time_col and tr:
        if tr.previous:
            col = metric.time_col
            cur, prev = tr, tr.previous
            cur_c, prev_c = _time_condition(col, cur), _time_condition(col, prev)
            select_dims.insert(0, f"CASE WHEN {cur_c} THEN '{cur.label}' ELSE '{prev.label}' END AS period")
            where.append(f"(({cur_c}) OR ({prev_c}))")
        else:
            where.append(_time_condition(metric.time_col, tr))
    tm = re.search(r"(\d+)\s*(?:or more|\+)\s*days past due|(?:more than|over|at least) (\d+) days past due", q, re.I)
    if tm and metric.id in ("delinquency_rate", "loan_delinquency_rate"):
        n = int(tm.group(1) or tm.group(2))
        metric = Metric(**{**metric.__dict__, "select": metric.select.replace("dpd >= 1", f"dpd >= {n}")})
        filters.append(f"dpd >= {n}")
    select = metric.select.replace("{cure_days}", "30" if re.search(r"30 days|30-day", q) else "30")
    sql = f"SELECT {', '.join(select_dims + [select])} FROM {metric.base}"
    if joins:
        sql += " " + " ".join(joins)
    if where:
        sql += " WHERE " + " AND ".join(where)
    if select_dims:
        n = len(select_dims)
        sql += " GROUP BY " + ", ".join(str(i) for i in range(1, n + 1))
        rank = re.search(r"\b(highest|top|most|best|greatest|largest)\b|\b(lowest|least|worst|fewest|smallest)\b", q, re.I)
        if rank and ("agent" in ids or re.match(r"\s*which\b", q, re.I)):
            if "agent" in ids:
                sql += " HAVING count(*) >= 30"
                caveats.append("Agents with fewer than 30 records are left out so small samples don't top the list.")
            sql += f" ORDER BY {n + 1} {'ASC' if rank.group(2) else 'DESC'} LIMIT 10"
            caveats.append("Top 10 shown, ranked by the first value column.")
        else:
            sql += " ORDER BY " + ", ".join(str(i) for i in range(1, n + 1))
    for u in unsupported:
        caveats.append(f"Not split by {u.replace('_', ' ')}: that breakdown isn't available for this metric.")
    if "strategy" in {d.id for d in dims} and not re.search(r"randomi[sz]ed", q, re.I):
        caveats.append("Observed, not causal: strategies were not randomly assigned outside the randomised pilot.")
    if "test_cell" in {d.id for d in dims} and re.search(r"randomi[sz]ed", q, re.I):
        caveats.append("Randomised cases only, so the comparison between cells is causal.")
    return Compiled(sql, metric.id, [d.id for d in dims], filters, tr.label if tr else None, tr, caveats)
