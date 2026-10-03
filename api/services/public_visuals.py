"""Public, aggregate-only data for the landing page visuals: the Canada risk map, the nightly decision flow and a
sample customer that shows how source records come together. Nothing here is per person: groups under
`suppression_min_group` customers are hidden, and the sample customer carries no names, IDs or contact details.

Reads the warehouse through common.db.warehouse() (read-only) and data/features/*.parquet. Results are cached in
memory for ten minutes."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import pandas as pd

from common.config import get_settings
from common.db import warehouse

CACHE_SECONDS = 600
_cache: dict[str, tuple[float, Any]] = {}
_lock = threading.Lock()

PROVINCES = {
    "BC": "British Columbia", "AB": "Alberta", "SK": "Saskatchewan", "MB": "Manitoba", "ON": "Ontario",
    "QC": "Quebec", "NB": "New Brunswick", "NS": "Nova Scotia", "PE": "Prince Edward Island",
    "NL": "Newfoundland and Labrador", "YT": "Yukon", "NT": "Northwest Territories", "NU": "Nunavut",
}
REASON_LABEL = {
    "no_funds": "Not enough money", "forgot": "Forgot", "unreachable": "Could not be reached", "dispute": "Dispute",
    "other": "Other reason", "missed_payment": "Missed payment", "returned_pad": "Returned automatic payment",
    "overlimit": "Over the limit", "manual": "Opened by hand", "reduced_income": "Reduced income",
    "job_loss": "Job loss", "rate_reset": "Rate reset", "illness": "Illness",
    "text_hardship_clear_90d": "Clear hardship in recent calls", "dpd_at_creation": "Already late when promised",
    "card_util": "High card use", "bur_inq_6m": "Many recent credit checks",
    "days_to_due_at_creation": "Long wait to due date",
    "days_in_case": "Time in collections",
}
METRICS: dict[str, dict] = {
    "broken_ptp_rate": {"label": "Broken promises", "unit": "%", "monthly": True,
                        "note": "Share of promises to pay, due that month, that were broken."},
    "hardship_rate": {"label": "Hardship", "unit": "%", "monthly": True,
                      "note": "Share of cases opened that month that carry a hardship flag. "
                                                  "Older cases are mostly closed, so recent months read higher."},
    "open_cases": {"label": "Open cases", "unit": "per 1,000", "monthly": False,
                   "note": "Open collections cases per 1,000 customers, today."},
    "promises_at_risk": {"label": "Promises at risk", "unit": "%", "monthly": False,
                         "note": "Share of open promises the model puts in the high or very high risk band, today."},
}


def cached(key: str, fn: Callable[[], Any]) -> Any:
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_SECONDS:
            return hit[1]
    value = fn()
    with _lock:
        _cache[key] = (time.time(), value)
    return value


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def _con():
    con = warehouse(read_only=True)
    con.execute("SET search_path='silver,gold,features'")
    return con


def month_list(as_of: date, n: int = 12) -> list[str]:
    y, m = as_of.year, as_of.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def top_reason(s: pd.Series) -> str | None:
    s = s.dropna()
    return REASON_LABEL.get(s.mode().iloc[0], str(s.mode().iloc[0]).replace("_", " ").capitalize()) if len(s) else None


def aggregate(
    df: pd.DataFrame, months: list[str], monthly: bool, min_group: int, denom: dict | None = None
) -> tuple[dict, list]:
    """df columns: pr, m, golden_id, v (0/1), reason (only on rows that count for the reason). Returns the per-province
    series and the national series; a province-month with fewer than `min_group` customers has value None."""
    keys = months if monthly else ["all"]
    if not monthly:
        df = df.assign(m="all")

    def val(g: pd.DataFrame, pr: str | None) -> float:
        if denom is None:
            return round(100 * float(g.v.mean()), 2)
        d = denom["all"] if pr is None else denom["pr"].get(pr, 0)
        return round(1000 * float(g.v.sum()) / d, 2) if d else 0.0

    series: dict[str, dict] = {}
    for pr, gp in df.groupby("pr"):
        row = {"value": [], "n": [], "top": []}
        by_m = {m: g for m, g in gp.groupby("m")}
        for m in keys:
            g = by_m.get(m)
            n = int(g.golden_id.nunique()) if g is not None else 0
            ok = g is not None and n >= min_group
            row["value"].append(val(g, pr) if ok else None)
            row["n"].append(n if ok else None)
            row["top"].append(top_reason(g.reason) if ok else None)
        series[str(pr)] = row
    by_m = {m: g for m, g in df.groupby("m")}
    national = [val(by_m[m], None) if m in by_m else None for m in keys]
    return series, national


def fsa_layer(df: pd.DataFrame, geo: pd.DataFrame, min_group: int, denom_fsa: dict | None) -> dict:
    out, hidden = [], 0
    for fsa, g in df.groupby("fsa"):
        n = int(g.golden_id.nunique())
        r = geo.get(fsa)
        if r is None:
            continue
        if n < min_group:
            hidden += 1
            continue
        v = (1000 * g.v.sum() / denom_fsa[fsa]) if denom_fsa is not None else 100 * g.v.mean()
        out.append({"fsa": fsa, "province": r["pr"], "lat": r["lat"], "lon": r["lon"], "n": n,
                    "value": round(float(v), 2)})
    return {"items": out, "hidden": hidden}


def _load_frames(months: list[str]) -> dict[str, pd.DataFrame]:
    con = _con()
    lo, hi = f"{months[0]}-01", get_settings().as_of_date.isoformat()
    try:
        cust = """JOIN identity.case_xref x ON x.case_id = {k}.case_id
                  JOIN gold.c360_customer c ON c.golden_id = x.golden_id"""
        broken = con.execute(f"""
            SELECT g.province_code pr, c.fsa, strftime(p.ptp_due_date, '%Y-%m') m, x.golden_id,
                   CASE WHEN p.ptp_status = 'broken' THEN 1 ELSE 0 END v,
                   CASE WHEN p.ptp_status = 'broken' THEN p.broken_reason_agent_coded END reason
            FROM promises_to_pay p {cust.format(k='p')} JOIN geo_reference g ON g.fsa = c.fsa
            WHERE p.ptp_status IN ('kept', 'partially_kept', 'broken') AND p.ptp_due_date >= DATE '{lo}'
              AND p.ptp_due_date <= DATE '{hi}'""").df()
        hard = con.execute(f"""
            SELECT g.province_code pr, c.fsa, strftime(k.case_open_date, '%Y-%m') m, k.golden_id,
                   CASE WHEN k.hardship_flag THEN 1 ELSE 0 END v,
                   CASE WHEN k.hardship_flag THEN k.hardship_reason END reason
            FROM gold.c360_case k JOIN gold.c360_customer c ON c.golden_id = k.golden_id
            JOIN geo_reference g ON g.fsa = c.fsa
            WHERE k.case_open_date >= DATE '{lo}' AND k.case_open_date <= DATE '{hi}'""").df()
        opened = con.execute("""
            SELECT g.province_code pr, c.fsa, k.golden_id, 1 v, k.case_open_reason reason
            FROM gold.c360_case k JOIN gold.c360_customer c ON c.golden_id = k.golden_id
            JOIN geo_reference g ON g.fsa = c.fsa WHERE k.case_status = 'open'""").df()
        den = con.execute("""SELECT g.province_code pr, c.fsa, count(*) n FROM gold.c360_customer c
                             JOIN geo_reference g ON g.fsa = c.fsa GROUP BY ALL""").df()
        geo = con.execute("""SELECT fsa, any_value(province_code) pr, any_value(centroid_lat) lat,
                                    any_value(centroid_lon) lon, sum(population_weight) w
                             FROM geo_reference WHERE centroid_lat IS NOT NULL GROUP BY fsa""").df()
        scores = pd.read_parquet(get_settings().features_dir / "ptp_scores.parquet",
                                 columns=["golden_id", "band", "reasons_json"]) if (
            get_settings().features_dir / "ptp_scores.parquet").exists() else None
        gl = con.execute("SELECT golden_id, fsa FROM gold.c360_customer").df() if scores is not None else None
    finally:
        con.close()
    out = {"broken": broken, "hard": hard, "opened": opened, "den": den, "geo": geo}
    if scores is not None:
        import json

        sc = scores.merge(gl, on="golden_id").merge(geo[["fsa", "pr"]], on="fsa")
        sc["v"] = sc.band.isin(["high", "very_high"]).astype(int)
        first = sc.reasons_json.map(lambda s: (json.loads(s) or [{}])[0].get("code"))
        sc["reason"] = first.where(sc.v == 1)
        out["risk"] = sc[["pr", "fsa", "golden_id", "v", "reason"]]
    return out


def _build_map() -> dict:
    s = get_settings()
    mg = s.suppression_min_group
    months = month_list(s.as_of_date)
    f = _load_frames(months)
    geo = f["geo"]
    geo_by = {r.fsa: {"pr": r.pr, "lat": float(r.lat), "lon": float(r.lon)} for r in geo.itertuples()}
    den = f["den"]
    den_pr = den.groupby("pr").n.sum().to_dict()
    den_all = int(den.n.sum())
    den_fsa = den.set_index("fsa").n.to_dict()

    metrics: dict[str, dict] = {}
    spec = {"broken_ptp_rate": (f["broken"], True, None), "hardship_rate": (f["hard"], True, None),
            "open_cases": (f["opened"], False, {"pr": den_pr, "all": den_all})}
    if "risk" in f:
        spec["promises_at_risk"] = (f["risk"], False, None)
    for mid, (df, monthly, denom) in spec.items():
        df = df.assign(m=df["m"] if "m" in df else "all")
        series, national = aggregate(df, months, monthly, mg, denom)
        layer = fsa_layer(df, geo_by, mg, den_fsa if denom else None)
        metrics[mid] = {**METRICS[mid], "national": national, "series": series, "fsas": layer["items"],
                        "fsas_hidden": layer["hidden"]}
    # Province bubble anchor: the population-weighted middle of its postal areas.
    g = geo.assign(wl=geo.lat * geo.w, wo=geo.lon * geo.w).groupby("pr")
    g = g.agg(wl=("wl", "sum"), wo=("wo", "sum"), w=("w", "sum"))
    provinces = [{"code": pr, "name": PROVINCES.get(pr, pr), "lat": round(float(r.wl / r.w), 3),
                  "lon": round(float(r.wo / r.w), 3), "customers": int(den_pr.get(pr, 0))}
                 for pr, r in g.iterrows() if pr in PROVINCES]
    return {"as_of": s.as_of_date.isoformat(), "months": months, "min_group": mg, "provinces": provinces,
            "metrics": metrics, "customers": den_all}


def public_map() -> dict:
    return cached("map", _build_map)


# ---- decision flow ---------------------------------------------------------------------------------------------

BANDS = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("very_high", "Very high"),
         ("none", "No promise to score")]
TREATMENTS = [("no_contact", "No contact"), ("reminder", "Reminder"), ("payment_link", "Payment link"),
              ("plan_offer", "Plan offer"), ("specialist_referral", "Specialist referral")]
BLOCK_PREFIXES = ("A representative acts", "Open dispute", "No contact:")


def _block_label(h: str) -> str:
    if h.startswith("A representative"):
        return "A representative acts for the customer"
    if h.startswith("Open dispute"):
        return "An open dispute"
    if "asked us to stop" in h:
        return "Customer asked us to stop"
    return h.replace("No contact: ", "").split(",")[0].capitalize()


def _build_flow() -> dict:
    path = get_settings().features_dir / "nba_queue.parquet"
    if not path.exists():
        return {"available": False, "nodes": [], "links": [], "total": 0,
                "message": "The nightly plan has not been built yet."}
    d = pd.read_parquet(path, columns=["treatment", "risk_band", "review_mode", "headline", "plan_date"])
    total = len(d)
    blocked = (d.treatment == "no_contact") & d.headline.fillna("").str.startswith(BLOCK_PREFIXES)
    d = d.assign(blocked=blocked, band=d.risk_band.fillna("none"))
    nodes: list[dict] = [{"id": "cases", "col": 0, "label": "Open cases", "value": total}]
    links: list[dict] = []

    def node(id_: str, col: int, label: str, value: int, **kw) -> None:
        if value:
            nodes.append({"id": id_, "col": col, "label": label, "value": int(value), **kw})

    def link(a: str, b: str, v: int) -> None:
        if v:
            links.append({"source": a, "target": b, "value": int(v)})

    reasons = d[blocked].headline.map(_block_label).value_counts().head(4)
    n_block = int(blocked.sum())
    node("allowed", 1, "Allowed to act", total - n_block)
    node("blocked", 1, "Blocked by policy", n_block, top=[{"label": k, "value": int(v)} for k, v in reasons.items()])
    link("cases", "allowed", total - n_block)
    link("cases", "blocked", n_block)
    ok = d[~d.blocked]
    for key, label in BANDS:
        node(f"band_{key}", 2, label, int((ok.band == key).sum()))
        link("allowed", f"band_{key}", int((ok.band == key).sum()))
    node("band_blocked", 2, "Not scored", n_block)
    link("blocked", "band_blocked", n_block)
    d = d.assign(bkey=d.band.where(~d.blocked, "blocked"))
    for key, label in TREATMENTS:
        node(f"t_{key}", 3, label, int((d.treatment == key).sum()))
    for bkey, g in d.groupby("bkey"):
        for tkey, n in g.treatment.value_counts().items():
            link(f"band_{bkey}", f"t_{tkey}", int(n))
    reviews = {"individual": "A person reviews each", "batch": "Batch, 2% sampled first", "none": "Nothing is sent"}
    d = d.assign(rv=d.review_mode.where(d.treatment != "no_contact", "none"))
    for key, label in reviews.items():
        node(f"r_{key}", 4, label, int((d.rv == key).sum()))
    for (t, rv), n in d.groupby(["treatment", "rv"]).size().items():
        link(f"t_{t}", f"r_{rv}", int(n))
    return {"available": True, "total": total, "plan_date": str(d.plan_date.iloc[0]) if total else None,
            "columns": ["Open cases", "Policy gate", "Break risk", "Treatment", "Review"],
            "nodes": nodes, "links": links}


def public_flow() -> dict:
    return cached("flow", _build_flow)


# ---- sample customer ---------------------------------------------------------------------------------------------

SYSTEM_LABEL = {"crm": "CRM", "cards": "Cards", "lending": "Loans", "core_banking": "Deposits",
                "bureau": "Credit bureau", "collections": "Collections case"}
ORDER = list(SYSTEM_LABEL)
TREATMENT_LABEL = dict(TREATMENTS)


def _build_sample() -> dict:
    """The first customer (by ID order) with exactly one record in each of the six systems, at least one match that
    is not certain, and a next action that sends something. Only labels, confidences and the action leave here."""
    con = _con()
    try:
        cands = con.execute("""
            SELECT x.golden_id, c.open_case_id FROM identity.identity_xref x JOIN gold.c360_customer c USING (golden_id)
            WHERE c.open_case_id IS NOT NULL GROUP BY x.golden_id, c.open_case_id
            HAVING count(DISTINCT x.source_system) = 6 AND min(x.match_probability) < 1 AND count(*) = 6
            ORDER BY x.golden_id LIMIT 300""").fetchall()
        q = get_settings().features_dir / "nba_queue.parquet"
        acts = {}
        if q.exists():
            qd = pd.read_parquet(q, columns=["case_id", "treatment", "channel"])
            acts = qd[qd.case_id.isin([c[1] for c in cands])].set_index("case_id")
        pick = next((c for c in cands if len(acts) and c[1] in acts.index and acts.loc[c[1]].treatment != "no_contact"),
                    cands[0] if cands else None)
        if not pick:
            return {"available": False, "records": [], "next_action": None}
        recs = con.execute("SELECT source_system, match_method, match_probability FROM identity.identity_xref "
                           "WHERE golden_id = ?", [pick[0]]).fetchall()
    finally:
        con.close()
    recs.sort(key=lambda r: ORDER.index(r[0]) if r[0] in ORDER else 99)
    records = [{"system": sysname, "label": f"{SYSTEM_LABEL.get(sysname, sysname)} record 1", "method": method,
                "confidence": float(prob) if prob is not None else None} for sysname, method, prob in recs]
    action = None
    if len(acts) and pick[1] in acts.index:
        t, ch = str(acts.loc[pick[1]].treatment), acts.loc[pick[1]].channel
        action = {"treatment": t, "label": TREATMENT_LABEL.get(t, t), "channel": None if ch != ch else ch}
    return {"available": True, "records": records, "next_action": action}


def public_sample() -> dict:
    return cached("sample", _build_sample)
