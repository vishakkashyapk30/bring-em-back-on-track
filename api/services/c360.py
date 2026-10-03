"""Read-only C360 services for the API (Layer 1 in the app): customer header and holdings, contact timeline,
identity and lineage, online feature vector. Same response shapes as api/fixtures so the frontend is unchanged."""

from __future__ import annotations

from typing import Any

from common.config import get_settings
from common.db import warehouse

PRODUCT_LABEL = {"card": "Credit card", "personal_loan": "Personal loan", "auto_loan": "Auto loan",
                 "mortgage": "Mortgage", "unsecured_loc": "Line of credit", "student_loc": "Student line of credit",
                 "chequing": "Chequing", "savings": "Savings", "tfsa_savings": "TFSA savings", "usd_account": "USD account"}
SYSTEM_LABEL = {"crm": "CRM", "cards": "Cards", "lending": "Lending", "core_banking": "Core banking",
                "bureau": "Credit bureau", "collections": "Collections"}


def _meta() -> dict:
    """as_of = the data snapshot; freshness = hours since the warehouse was last built (contract SLA: 26 h)."""
    import time

    s = get_settings()
    age = round((time.time() - s.warehouse_path.stat().st_mtime) / 3600, 1) if s.warehouse_path.exists() else None
    return {"as_of": f"{s.as_of_date}T06:00:00-04:00", "freshness_hours": age, "fixture": False}


def _q(sql: str, params: list | None = None) -> list[dict[str, Any]]:
    con = warehouse(read_only=True)
    try:
        rel = con.execute(sql, params or [])
        cols = [d[0] for d in rel.description]
        return [dict(zip(cols, r, strict=True)) for r in rel.fetchall()]
    finally:
        con.close()


def customer(golden_id: str) -> dict | None:
    rows = _q("SELECT * FROM gold.c360_customer WHERE golden_id = ?", [golden_id])
    if not rows:
        return None
    c = rows[0]
    case = _q("SELECT current_bucket, hardship_source, hardship_flag, case_open_date FROM gold.c360_case WHERE case_id = ?",
              [c["open_case_id"]])[0] if c["open_case_id"] else {}
    risk = _q("""SELECT score, score_band FROM silver.model_scores
                 WHERE model_name = 'collections_risk' AND list_contains(?, crm_customer_id)
                 ORDER BY score_date DESC LIMIT 1""", [c["crm_customer_ids"]])
    accts = _q("""SELECT product_type, account_id, current_balance, past_due_amount, dpd, account_status, source_system
                  FROM gold.c360_account WHERE golden_id = ? ORDER BY is_open DESC, source_system, account_id""", [golden_id])
    since = _q("SELECT min(customer_since_date) d FROM silver.stg_customers WHERE list_contains(?, crm_customer_id)",
               [c["crm_customer_ids"]])[0]["d"]
    consent_call = (f"{c['permitted_call_start_local']}-{c['permitted_call_end_local']}" if c["consent_call"] else "no")
    return {
        "meta": _meta(), "golden_id": golden_id, "display_name": c["display_name"], "segment": c["segment"],
        "city": c["city"], "province_code": c["province_code"], "customer_since": str(since.year) if since else None,
        "time_zone": c["time_zone"],
        "badges": {
            "risk": {"band": (risk[0]["score_band"] if risk else "n/a"), "score": round(float(risk[0]["score"]), 2) if risk else None},
            "bucket": case.get("current_bucket"),
            "consent": {"call": consent_call, "sms": c["consent_sms"], "email": c["consent_email"],
                        "push": c["consent_push"], "language": (c["preferred_language"] or "EN").upper()},
            "hardship_flag": c["hardship_flag"], "hardship_source": case.get("hardship_source"),
            "hardship_raised": str(case.get("case_open_date")) if case.get("hardship_flag") else None,
            "vulnerability_flag": c["vulnerability_flag"], "dispute_open_flag": c["dispute_open_flag"],
            "contact_block": c["contact_block"],
        },
        "holdings": [{"product": PRODUCT_LABEL.get(a["product_type"], a["product_type"]),
                      "account": "••" + a["account_id"][-4:], "balance": a["current_balance"],
                      "overdue": a["past_due_amount"] or None, "dpd": a["dpd"], "status": a["account_status"],
                      "system": SYSTEM_LABEL.get(a["source_system"])} for a in accts],
        "open_case_id": c["open_case_id"], "max_dpd": c["max_dpd"], "total_past_due_cad": float(c["total_past_due_cad"]),
        "payroll_delay_days": c["payroll_delay_days"],
    }


def timeline(golden_id: str, limit: int = 40) -> dict:
    rows = _q(f"""
        SELECT h.contact_ts_local AS ts, coalesce(h.channel_v2, h.channel) AS channel, h.direction, h.outcome_desc,
               h.system_event_type, h.sms_text, h.ptp_made_flag, h.payment_amount, h.transcript_id, h.contact_id,
               h.hardship_mentioned_flag, h.dispute_raised_flag
        FROM silver.contact_history h JOIN identity.case_xref x ON x.case_id = h.case_id
        WHERE x.golden_id = ? ORDER BY h.contact_ts_local DESC LIMIT {int(limit)}""", [golden_id])
    items = []
    for r in rows:
        sys_evt = (r["system_event_type"] or "").replace("_", " ")
        bits = [sys_evt.capitalize() if sys_evt else (r["outcome_desc"] or "")]
        if r["sms_text"]:
            bits.append(f"\u201c{r['sms_text'][:90]}\u201d")
        if r["ptp_made_flag"]:
            bits.append("promise to pay taken")
        if r["payment_amount"]:
            bits.append(f"payment ${r['payment_amount']:,.2f}")
        if r["hardship_mentioned_flag"]:
            bits.append("hardship mentioned")
        if r["dispute_raised_flag"]:
            bits.append("dispute raised")
        items.append({"date": str(r["ts"])[:10], "type": r["channel"] or "system",
                      "text": "; ".join(b for b in bits if b) or r["direction"],
                      "transcript_id": r["transcript_id"], "contact_id": r["contact_id"] if r["transcript_id"] else None,
                      "severity": "high" if r["system_event_type"] and "broken" in (r["system_event_type"] or "") else None})
    return {"meta": _meta(), "items": items, "next_cursor": None}


def identity(golden_id: str) -> dict | None:
    rows = _q("""SELECT source_system, source_ref, match_method, match_probability, evidence FROM identity.identity_xref
                 WHERE golden_id = ? ORDER BY source_system, source_ref""", [golden_id])
    if not rows:
        return None
    c = _q("SELECT match_method, match_confidence FROM gold.c360_customer WHERE golden_id = ?", [golden_id])[0]
    systems = sorted({r["source_system"] for r in rows})
    return {"meta": _meta(), "golden_id": golden_id, "match_confidence": float(c["match_confidence"]),
            "match_method": c["match_method"],
            "sources": [{"system": r["source_system"], "ref": r["source_ref"], "method": r["match_method"],
                         "confidence": float(r["match_probability"]) if r["match_probability"] is not None else None}
                        for r in rows],
            "lineage": [SYSTEM_LABEL.get(s, s) for s in systems]}


def features_online(golden_id: str) -> dict | None:
    rows = _q("SELECT * FROM features.f_customer_online WHERE golden_id = ?", [golden_id])
    if not rows:
        return None
    v = {k: (float(x) if hasattr(x, "as_integer_ratio") and not isinstance(x, (bool, int)) else x)
         for k, x in rows[0].items() if k not in ("golden_id", "as_of_ts")}
    return {"meta": _meta(), "golden_id": golden_id, "as_of": str(rows[0]["as_of_ts"]), "vector": v}
