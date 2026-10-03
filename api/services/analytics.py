"""Read-only analyst, team-lead and steward views over the warehouse: weather map (S2), strategy scorecard (S4),
agent roster, steward identity review queue and the monitoring snapshot. Groups under 10 customers are suppressed."""

from __future__ import annotations

import json
import time

from api.services.c360 import _meta, _q
from common.config import get_settings

MIN_GROUP = get_settings().suppression_min_group

MAP_METRICS = {
    # metric id: (label, value SQL over p (promise) or k (case), base)
    "broken_ptp_rate": ("Broken-promise rate", "promise"),
    "hardship_rate": ("Hardship rate (cases opened in 2026)", "case"),
}


def bubble_map(metric: str = "broken_ptp_rate") -> dict:
    if metric not in MAP_METRICS:
        metric = "broken_ptp_rate"
    label, base = MAP_METRICS[metric]
    if base == "promise":
        inner = """SELECT c.fsa, x.golden_id, CASE WHEN p.ptp_status = 'broken' THEN 1.0 ELSE 0.0 END AS v
                   FROM silver.promises_to_pay p JOIN identity.case_xref x ON x.case_id = p.case_id
                   JOIN gold.c360_customer c ON c.golden_id = x.golden_id
                   WHERE p.ptp_status IN ('kept', 'partially_kept', 'broken') AND p.ptp_due_date >= DATE '2026-01-01'"""
    else:
        inner = """SELECT c.fsa, k.golden_id, CASE WHEN k.hardship_flag THEN 1.0 ELSE 0.0 END AS v
                   FROM gold.c360_case k JOIN gold.c360_customer c ON c.golden_id = k.golden_id
                   WHERE k.case_open_date >= DATE '2026-01-01'"""
    sql = f"""SELECT g.fsa, any_value(g.city) AS city, any_value(g.province_code) AS province,
                     any_value(g.centroid_lat) AS lat, any_value(g.centroid_lon) AS lon,
                     count(DISTINCT t.golden_id) AS customers, round(avg(t.v), 4) AS value
              FROM ({inner}) t JOIN silver.geo_reference g ON g.fsa = t.fsa
              GROUP BY g.fsa"""
    rows = _q(sql)
    shown = [r for r in rows if r["customers"] >= MIN_GROUP and r["lat"] is not None]
    return {"meta": _meta(), "metric": metric, "label": label, "level": "fsa",
            "items": [{"fsa": r["fsa"], "city": r["city"], "province": r["province"], "lat": float(r["lat"]),
                       "lon": float(r["lon"]), "customers": r["customers"], "value": float(r["value"])} for r in shown],
            "suppressed": len(rows) - len(shown), "min_group": MIN_GROUP, "sql": " ".join(sql.split())}


def scorecard() -> dict:
    """S4: cure rate by strategy, on matured cohorts (opened at least 30 days before the snapshot). Causal only
    within randomly assigned cases; the all-cases figure is observed, not causal."""
    sql = """
        WITH k AS (
            SELECT split_part(strategy_code, '-', 1) AS stage, strategy_code, assignment_method = 'random' AS randomised,
                   coalesce(cure_flag AND days_to_cure <= 30, false) AS cured30, coalesce(complaint_flag, false) AS complaint_flag, cost_to_collect_est
            FROM silver.collections_cases WHERE case_open_date <= DATE '2026-08-28' AND strategy_code IS NOT NULL)
        SELECT stage, strategy_code,
               count(*) FILTER (WHERE randomised) AS randomised_cases,
               round(100.0 * avg(cured30::int) FILTER (WHERE randomised), 1) AS cure_rate_30d_randomised,
               count(*) AS all_cases,
               round(100.0 * avg(cured30::int), 1) AS cure_rate_30d_all,
               round(sum(cost_to_collect_est) / nullif(sum(cured30::int), 0), 2) AS cost_per_cure_cad,
               round(1000.0 * avg(complaint_flag::int), 1) AS complaints_per_1000_cases
        FROM k GROUP BY 1, 2 ORDER BY 1, 2"""
    return {"meta": _meta(), "items": _q(sql), "sql": " ".join(sql.split()),
            "note": ("Compare strategies only within a stage: a case's strategy code changes as it rolls to the next "
                     "stage, so early-stage codes stay only on cases that cured early. Randomised columns are causal "
                     "comparisons; all-cases columns are observed, not causal.")}


def agents(team_id: str | None = None) -> dict:
    sql = """SELECT agent_id, agent_display_name AS name, site, team_id, role, skill_hardship,
                    vulnerable_customer_certified, current_case_load, max_concurrent_cases,
                    round(ptp_kept_rate_90d, 3) AS ptp_kept_rate_90d, round(cure_rate_90d, 3) AS cure_rate_90d
             FROM silver.agents WHERE status = 'active' {f} ORDER BY team_id, agent_id LIMIT 200"""
    return {"meta": _meta(), "items": _q(sql.format(f="AND team_id = ?" if team_id else ""), [team_id] if team_id else [])}


def _mask(name: str | None) -> str | None:
    if not name:
        return None
    parts = name.replace(",", " ").split()
    return " ".join(p[0] + "***" for p in parts if p)


def identity_queue(limit: int = 50) -> dict:
    """Grey-band candidate links for the steward: masked side-by-side view (no full names, DOB year only)."""
    rows = _q("""
        WITH q AS (SELECT * FROM identity.review_queue ORDER BY score DESC, pair_id LIMIT ?),
        src AS (
            SELECT 'bureau' AS sys, bank_subject_ref AS src_ref, name_raw, dob, postal FROM silver.stg_external
             WHERE bank_subject_ref IN (SELECT source_ref FROM q WHERE source_system = 'bureau')
            UNION ALL SELECT 'cards', src_customer_ref, name_raw, dob, postal FROM silver.stg_card_accounts
             WHERE src_customer_ref IN (SELECT source_ref FROM q WHERE source_system = 'cards')
            UNION ALL SELECT 'lending', src_customer_ref, name_raw, dob, postal FROM silver.stg_loan_accounts
             WHERE src_customer_ref IN (SELECT source_ref FROM q WHERE source_system = 'lending')
            UNION ALL SELECT 'core_banking', src_customer_ref, name_raw, dob, postal FROM silver.stg_deposit_accounts
             WHERE src_customer_ref IN (SELECT source_ref FROM q WHERE source_system = 'core_banking')),
        s1 AS (SELECT sys, src_ref, any_value(name_raw) name_raw, any_value(dob) dob, any_value(postal) postal FROM src GROUP BY ALL),
        g AS (SELECT c.golden_id, c.display_name, c.fsa, min(s.dob) dob
              FROM gold.c360_customer c JOIN identity.crm_golden cg ON cg.golden_id = c.golden_id
              JOIN silver.stg_customers s ON s.crm_customer_id = cg.crm_customer_id
              WHERE c.golden_id IN (SELECT candidate_golden_id FROM q) GROUP BY ALL)
        SELECT q.pair_id, q.source_system, q.source_ref, q.candidate_golden_id, q.score, q.reason,
               s1.name_raw AS src_name, s1.dob AS src_dob, s1.postal AS src_postal,
               g.display_name AS g_name, g.fsa AS g_fsa, g.dob AS g_dob
        FROM q LEFT JOIN s1 ON s1.sys = q.source_system AND s1.src_ref = q.source_ref
        LEFT JOIN g ON g.golden_id = q.candidate_golden_id
        ORDER BY q.score DESC, q.pair_id""", [limit])
    total = _q("SELECT count(*) n FROM identity.review_queue")[0]["n"]
    items = [{
        "pair_id": r["pair_id"], "match_probability": float(r["score"]), "reason": r["reason"],
        "left": {"system": r["source_system"], "ref": r["source_ref"], "name": _mask(r["src_name"]),
                 "dob_year": r["src_dob"].year if r["src_dob"] else None, "fsa": (r["src_postal"] or "")[:3] or None},
        "right": {"system": "golden", "ref": r["candidate_golden_id"], "name": _mask(r["g_name"]),
                  "dob_year": r["g_dob"].year if r["g_dob"] else None, "fsa": r["g_fsa"]},
    } for r in rows]
    return {"meta": _meta(), "total": total, "items": items}


def monitoring() -> dict:
    s = get_settings()
    rep = s.reports_dir

    def load(name: str) -> dict | None:
        p = rep / f"{name}.json"
        return json.loads(p.read_text()) if p.exists() else None

    parity, text, bench, dq = load("feature_parity"), load("text_rules_eval"), load("benchmark"), load("data_quality")
    age = round((time.time() - s.warehouse_path.stat().st_mtime) / 3600, 1) if s.warehouse_path.exists() else None
    tests = (dq or {}).get("contract_tests", [])
    return {
        "meta": _meta(),
        "freshness_hours": age, "freshness_sla_hours": s.freshness_sla_hours,
        "contract_tests": {"passed": sum(t["status"] == "pass" for t in tests), "total": len(tests)},
        "feature_parity": parity,
        "text_features": (text or {}).get("accuracy"),
        "benchmark": {k: (bench or {}).get(k) for k in ("questions", "dev_scored", "dev_mean_score", "refused")},
        "model": None,  # Layer 4: PTP-break model drift and calibration once trained
    }
