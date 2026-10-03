# ruff: noqa: E501
"""Load everything the next-best-action rules need for open cases, in bulk (batch queue) or for one case (live).

One row per open case: the case, the customer's golden record (consent, hours, blocks, hardship), the current
promise and its break risk (models/ptp_break/score.py), cash-stress and text signals (features.f_customer_online),
and the primary account's age. Hardship changes made by people in the app (ops.db hardship_flag_events) override
the warehouse value, so a raised flag stops pressure immediately.
"""

from __future__ import annotations

import json
from datetime import date

import duckdb

from common.config import get_settings
from common.db import ops

SNAPSHOT = date(2026, 9, 28)

CASE_SQL = """
WITH sc AS (SELECT * FROM read_parquet('{scores}')),
     cur AS (  -- the promise the case is working on: the current one if open, else the open one due first
        SELECT DISTINCT ON (case_id) case_id, ptp_id, ptp_due_date, amount_cad, p_break, band, model, reasons_json,
               v21_score
        FROM sc ORDER BY case_id, ptp_due_date),
     brk AS (
        SELECT case_id, max(status_ts) AS last_broken_ts, arg_max(ptp_id, status_ts) AS last_broken_ptp, count(*) AS broken_count
        FROM silver.promises_to_pay WHERE ptp_status IN ('broken', 'partially_kept') GROUP BY 1),
     acct AS (
        SELECT account_id, date_diff('month', open_date, DATE '2026-09-28') AS months_on_book FROM gold.c360_account)
SELECT k.case_id, k.golden_id, k.case_open_date, k.current_dpd, k.current_bucket, k.primary_product,
       k.primary_account_id,
       k.total_overdue, k.total_exposure, k.assigned_agent_id, k.assigned_team, k.queue, k.strategy_code,
       k.hardship_flag AS case_hardship, k.hardship_source, k.hardship_reason, k.hardship_program_offered,
       k.hardship_program_accepted, k.hardship_plan_start, k.hardship_plan_end, k.payment_plan_flag,
       k.dispute_status, k.cease_contact_flag, k.third_party_rep_flag, k.insolvency_hold_flag, k.deceased_hold_flag,
       k.vulnerable_customer_flag, k.contact_cap_7d, k.contacts_last_7d, k.language_of_service,
       c.display_name, c.time_zone, c.province_code, c.consent_call, c.consent_sms, c.consent_email, c.consent_push,
       c.permitted_call_start_local, c.permitted_call_end_local, c.sunday_contact_permitted,
       c.internal_do_not_call_flag, c.contact_block, c.hardship_flag, c.vulnerability_flag, c.dispute_open_flag,
       c.payroll_delay_days,
       f.nsf_count_mtd, f.days_negative_mtd, f.high_cost_lender_txn_flag, f.ei_deposit_flag,
       f.last_stated_delay_reason, f.last_note_hardship_signal, f.last_call_hardship_signal,
       f.text_hardship_mentions_90d,
       cur.ptp_id, cur.ptp_due_date, cur.amount_cad AS ptp_amount, cur.p_break, cur.band AS risk_band,
       cur.model AS risk_model, cur.reasons_json, cur.v21_score,
       brk.last_broken_ts, brk.last_broken_ptp, coalesce(brk.broken_count, 0) AS broken_count,
       acct.months_on_book
FROM gold.c360_case k
JOIN gold.c360_customer c ON c.golden_id = k.golden_id
LEFT JOIN features.f_customer_online f ON f.golden_id = k.golden_id
LEFT JOIN cur ON cur.case_id = k.case_id
LEFT JOIN brk ON brk.case_id = k.case_id
LEFT JOIN acct ON acct.account_id = k.primary_account_id
WHERE k.case_status = 'open' {where}
"""


def _connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(get_settings().warehouse_path), read_only=True)
    return con


def _ops_hardship() -> dict[str, str]:
    """Latest hardship level set by a person in the app, per golden ID (overrides the warehouse)."""
    try:
        with ops() as db:
            rows = db.execute("""SELECT golden_id, to_level FROM hardship_flag_events e
                                 WHERE event_id = (SELECT max(event_id) FROM hardship_flag_events x
                                                   WHERE x.golden_id = e.golden_id)""").fetchall()
    except Exception:  # noqa: BLE001 - ops store not initialised yet
        return {}
    return {g: lvl for g, lvl in rows}


def _apply_ops(rows: list[dict]) -> list[dict]:
    latest = _ops_hardship()
    for r in rows:
        r["reasons"] = json.loads(r.pop("reasons_json") or "[]")
        if r["golden_id"] in latest:
            r["hardship_flag"] = latest[r["golden_id"]]
            r["hardship_source"] = "set in the app"
    return rows


def load_cases(case_id: str | None = None, golden_id: str | None = None) -> list[dict]:
    scores = get_settings().features_dir / "ptp_scores.parquet"
    where, params = "", []
    if case_id:
        where, params = "AND k.case_id = ?", [case_id]
    elif golden_id:
        where, params = "AND k.golden_id = ?", [golden_id]
    con = _connect()
    try:
        rel = con.execute(CASE_SQL.format(scores=scores, where=where), params)
        cols = [d[0] for d in rel.description]
        rows = [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
    finally:
        con.close()
    return _apply_ops(rows)


def load_programs() -> list[dict]:
    con = _connect()
    try:
        rel = con.execute("SELECT * FROM silver.hardship_programs WHERE CAST(effective_to AS VARCHAR) LIKE '9999%'")
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
    finally:
        con.close()


def load_offer_history(golden_ids: list[str] | None = None) -> dict[str, list[dict]]:
    """Past hardship offers per golden ID (for 'uses in 12 months' and 'broken plan in 90 days')."""
    con = _connect()
    try:
        sql = """SELECT x.golden_id, o.program_id, o.offer_ts, o.customer_response, o.plan_status, o.response_ts
                 FROM silver.offers o JOIN identity.case_xref x ON x.case_id = o.case_id"""
        if golden_ids is not None:
            con.execute("CREATE TEMP TABLE g AS SELECT unnest(?) AS golden_id", [golden_ids])
            sql += " SEMI JOIN g USING (golden_id)"
        rel = con.execute(sql)
        cols = [d[0] for d in rel.description]
        out: dict[str, list[dict]] = {}
        for r in rel.fetchall():
            d = dict(zip(cols, r, strict=True))
            out.setdefault(d["golden_id"], []).append(d)
        return out
    finally:
        con.close()
