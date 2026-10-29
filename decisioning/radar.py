# ruff: noqa: E501
"""S1 employer shock radar: weekly per employer_key with at least 10 customers: payroll-gap count, new EI count,
average payroll_amount_change_pct against the employer's own history and its industry_naics2 peers.

Gap plus new EI is called 'layoff_like'; a gap without EI is called 'payroll_delay'. ops_events are checked first and a
known incident is shown beside the pattern. It is a radar, not a layoff detector: no field says a person lost a job.

Rules and arithmetic only, so it works with LLM_PROVIDER=offline and needs no model. It computes on any data and says
"no cluster" when there is none. On the real release it finds none (docs/profiling/profiling_decisions.md section 1: 7.3% of
Windsor-Essex manufacturing deposits are late against 7.8% elsewhere), which is the honest answer, not an error.

Two entry points share one classifier:
* `compute(observations, ops_events)`: customer-week observations in memory (the unit tests and the spec suite).
* `employer_week(week)`: the real warehouse, aggregated in SQL on the latest deposit snapshot (read only).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MIN_GROUP = 10  # V1 section 6: only employers with 10 or more customers are shown
GAP_DAYS = 7  # a payroll deposit more than 7 days late is a gap (the profiling definition)
NEW_EI_DAYS = 30  # an EI deposit first seen in the last 30 days is new
MIN_GAPS = 5  # fewer late payrolls than this is not a cluster, whatever the share
MIN_GAP_RATE = 0.25  # at least a quarter of the employer's customers are late ...
PEER_MULTIPLE = 2.0  # ... and at least twice the industry peers' rate
ALPHA = 0.01  # chance of a false alarm per week across all employers (Bonferroni)
MIN_BASE_RATE = 0.01  # peers with almost no late payroll do not make one late payroll a signal
EI_SHARE_FOR_LAYOFF_LIKE = 0.30  # new EI among the late customers at or above this share looks like job loss

LABEL = ("Radar, not a layoff detector: it counts late payroll and new Employment Insurance deposits. "
         "No field says a person lost their job, so a person decides what it means.")
PATTERN_TEXT = {
    "layoff_like": "Late payroll with new EI deposits: looks like job loss for many people at one employer.",
    "payroll_delay": "Late payroll without new EI deposits: looks like a payroll delay at the employer.",
    "none": "No cluster: the share of late payroll is not unusual for this employer.",
}


@dataclass(frozen=True)
class Observation:
    """One customer-week."""

    golden_id: str
    employer_key: str
    industry_naics2: str
    week_start: dt.date
    payroll_gap: bool
    new_ei_deposit: bool
    payroll_amount_change_pct: float = 0.0
    has_open_case: bool = False
    exposure_cad: float = 0.0


def employer_token(employer_name: str) -> str:
    """The employer key shown to people: a short hash of the name (names are not shown on the radar)."""
    return "EMP-" + hashlib.sha1(employer_name.strip().lower().encode()).hexdigest()[:8].upper()


def week_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def aggregate(observations: Iterable[Observation]) -> list[dict[str, Any]]:
    """One group per (employer_key, week_start)."""
    by: dict[tuple[str, dt.date], list[Observation]] = defaultdict(list)
    for o in observations:
        by[(o.employer_key, week_of(o.week_start))].append(o)
    out = []
    for (key, week), os_ in by.items():
        out.append({
            "employer_key": key, "week_start": week, "industry_naics2": os_[0].industry_naics2,
            "n_customers": len(os_), "n_payroll_gap": sum(o.payroll_gap for o in os_),
            "n_new_ei": sum(o.new_ei_deposit for o in os_),
            "avg_payroll_change_pct": sum(o.payroll_amount_change_pct for o in os_) / len(os_),
            "open_cases": sum(o.has_open_case for o in os_),
            "exposure_cad": sum(o.exposure_cad for o in os_ if o.has_open_case),
            "members": [o.golden_id for o in os_],
            "members_behind": [o.golden_id for o in os_ if o.has_open_case],
            "members_not_behind": [o.golden_id for o in os_ if not o.has_open_case],
        })
    return out


def _ev(e: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    return e.get(key, default) if isinstance(e, Mapping) else getattr(e, key, default)


def _as_date(v: Any) -> dt.date:
    return v.date() if isinstance(v, dt.datetime) else v


def _tables(e: Any) -> list[str]:
    t = _ev(e, "affected_tables", None) or []
    if isinstance(t, str):
        t = [x.strip(' "[]') for x in t.split(",")]
    return [str(x) for x in t]


def known_incidents(week: dt.date, ops_events: Sequence[Any]) -> list[dict[str, Any]]:
    """ops_events that overlap the week and touch payroll data (deposit_accounts); checked before naming a pattern."""
    end = week + dt.timedelta(days=7)
    out = []
    for e in ops_events:
        if "deposit_accounts" not in _tables(e):
            continue
        s, f = _as_date(_ev(e, "start_ts")), _as_date(_ev(e, "end_ts"))
        if s <= end and f >= week:
            out.append({"event_id": _ev(e, "event_id"), "event_type": _ev(e, "event_type"),
                        "description": _ev(e, "description", "")})
    return out


def _tail(n: int, k: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p): how surprising k late payrolls are if the employer is like its peers."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return min(1.0, sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1)))


def classify(n: int, gaps: int, new_ei: int, peer_gap_rate: float | None, tests: int = 1) -> str:
    """Rules: enough late payrolls, a big enough share, and (when there are peers) clearly above them. Because the
    radar looks at thousands of employers a week, the surprise is judged with a Bonferroni correction (tests)."""
    if n <= 0 or gaps < MIN_GAPS:
        return "none"
    rate = gaps / n
    if rate < MIN_GAP_RATE:
        return "none"
    if peer_gap_rate is not None:
        if rate < PEER_MULTIPLE * peer_gap_rate or _tail(n, gaps, max(peer_gap_rate, MIN_BASE_RATE)) * tests > ALPHA:
            return "none"
    return "layoff_like" if new_ei / gaps >= EI_SHARE_FOR_LAYOFF_LIKE else "payroll_delay"


def rate_groups(groups: list[dict[str, Any]], ops_events: Sequence[Any] = (),
                min_group: int = MIN_GROUP) -> list[dict[str, Any]]:
    """Hide small groups, compare with own history and industry peers, check ops_events first, name the pattern."""
    visible = [g for g in groups if g["n_customers"] >= min_group]  # small groups never leave this function
    tot: dict[tuple, list[float]] = defaultdict(lambda: [0, 0, 0.0])  # per (week, industry): customers, gaps, change
    wk_tot: dict[Any, list[float]] = defaultdict(lambda: [0, 0, 0.0])
    tests: dict[Any, int] = defaultdict(int)
    quiet = {id(g): g["n_payroll_gap"] / g["n_customers"] < MIN_GAP_RATE for g in visible}
    for g in visible:  # the baseline is built from quiet groups, so one cluster cannot hide another
        if not quiet[id(g)]:
            tests[g["week_start"]] += 1
            continue
        for t in (tot[(g["week_start"], g["industry_naics2"])], wk_tot[g["week_start"]]):
            t[0] += g["n_customers"]
            t[1] += g["n_payroll_gap"]
            t[2] += g["avg_payroll_change_pct"] * g["n_customers"]
        tests[g["week_start"]] += 1
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for g in visible:
        history[g["employer_key"]].append(g)
    out = []
    for g in visible:
        n = g["n_customers"]
        ind = tot[(g["week_start"], g["industry_naics2"])]
        own_in = quiet[id(g)]
        pn, pg, pc = (ind[0] - own_in * n, ind[1] - own_in * g["n_payroll_gap"],
                      ind[2] - own_in * g["avg_payroll_change_pct"] * n)
        if pn < min_group:  # too few industry peers: compare with every other employer that week
            allw = wk_tot[g["week_start"]]
            pn, pg, pc = (allw[0] - own_in * n, allw[1] - own_in * g["n_payroll_gap"],
                          allw[2] - own_in * g["avg_payroll_change_pct"] * n)
        peer_rate = pg / pn if pn else None
        peer_change = pc / pn if pn else None
        prior = [p for p in history[g["employer_key"]] if p["week_start"] < g["week_start"]]
        own = sum(p["avg_payroll_change_pct"] for p in prior) / len(prior) if prior else None
        pattern = classify(n, g["n_payroll_gap"], g["n_new_ei"], peer_rate, tests[g["week_start"]])
        incidents = known_incidents(g["week_start"], ops_events)
        explained = incidents[0]["event_id"] if incidents and pattern != "none" else None
        text = PATTERN_TEXT[pattern]
        if explained:
            text += f" A known incident ({explained}) overlaps this week, so check it first."
        out.append({
            "employer_key": g["employer_key"], "week_start": g["week_start"].isoformat(),
            "industry_naics2": g["industry_naics2"], "n_customers": n,
            "n_payroll_gap": g["n_payroll_gap"], "n_new_ei": g["n_new_ei"],
            "gap_rate": round(g["n_payroll_gap"] / n, 4),
            "peer_gap_rate": None if peer_rate is None else round(peer_rate, 4),
            "avg_payroll_change_pct": round(g["avg_payroll_change_pct"], 4),
            "own_history_change_pct": None if own is None else round(own, 4),
            "industry_peer_change_pct": None if peer_change is None else round(peer_change, 4),
            "pattern": pattern, "explained_by_incident": explained, "known_incidents": incidents,
            "open_cases": g["open_cases"], "exposure_cad": round(g["exposure_cad"], 2),
            "label": f"{LABEL} {text}", "members": g.get("members", []),
            "members_behind": g.get("members_behind", []), "members_not_behind": g.get("members_not_behind", []),
        })
    return sorted(out, key=lambda r: (r["pattern"] == "none", -r["n_payroll_gap"], r["employer_key"]))


INTERNAL = ("members", "members_behind", "members_not_behind")


def public(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rows without the customer ID lists (what the screens and the API show)."""
    return [{k: v for k, v in r.items() if k not in INTERNAL} for r in rows]


def compute(observations: Iterable[Observation], ops_events: Sequence[Any] = ()) -> list[dict[str, Any]]:
    return rate_groups(aggregate(observations), ops_events)


# ------------------------------------------------------------------ the real warehouse (read only)
def _latest_snapshot(con) -> dt.date | None:
    """The full deposit snapshot (the one with the most rows; the other days hold a few hundred changed rows)."""
    row = con.execute("SELECT snapshot_date FROM silver.deposit_accounts GROUP BY 1 "
                      "ORDER BY count(*) DESC, 1 DESC LIMIT 1").fetchone()
    return row[0] if row else None


GROUPS_SQL = """
WITH dep AS (
    SELECT x.golden_id,
           max(d.payroll_delay_days) AS delay, avg(d.payroll_amount_change_pct) AS chg,
           bool_or(d.ei_deposit_flag AND d.ei_first_deposit_date >= CAST(? AS DATE) - INTERVAL {ei} DAY) AS new_ei
    FROM silver.deposit_accounts d
    JOIN identity.account_xref x ON x.source_system = 'core_banking' AND x.account_id = d.deposit_account_id
    WHERE d.snapshot_date = ?
    GROUP BY 1),
cust AS (
    SELECT g.golden_id, any_value(c.employer_name) AS employer_name, any_value(c.industry_naics2) AS ind
    FROM silver.customers c JOIN identity.crm_golden g USING (crm_customer_id)
    WHERE c.employer_name IS NOT NULL AND c.effective_to_ts >= TIMESTAMP '9999-01-01'
    GROUP BY 1),
cases AS (
    SELECT x.golden_id, sum(k.total_exposure) AS exposure
    FROM silver.collections_cases k JOIN identity.case_xref x USING (case_id)
    WHERE k.case_status = 'open' AND x.golden_id IS NOT NULL GROUP BY 1)
SELECT 'EMP-' || upper(substr(md5(lower(trim(cust.employer_name))), 1, 8)) AS employer_key,
       any_value(cust.ind) AS industry_naics2, count(*) AS n_customers,
       count(*) FILTER (WHERE dep.delay > {gap}) AS n_payroll_gap,
       count(*) FILTER (WHERE dep.new_ei) AS n_new_ei,
       coalesce(avg(dep.chg), 0) AS avg_payroll_change_pct,
       count(cases.golden_id) AS open_cases, coalesce(sum(cases.exposure), 0) AS exposure_cad
FROM dep JOIN cust USING (golden_id) LEFT JOIN cases USING (golden_id)
GROUP BY 1
"""


def employer_week(week: str | None = None, con=None, limit: int = 25) -> dict[str, Any]:
    """Radar rows for the latest full deposit snapshot of the real warehouse. `week` (YYYY-MM-DD) is accepted for
    the API but the release holds one full snapshot, so it must fall in the same week (otherwise: no data).
    Own-history comparison needs more than one weekly snapshot and is n/a until a second one is loaded."""
    from common.db import warehouse

    own = con is None
    con = con or warehouse(read_only=True)
    try:
        snap = _latest_snapshot(con)
        if snap is None:
            return empty("No deposit snapshot is loaded.")
        wk = week_of(snap)
        if week and week_of(dt.date.fromisoformat(week[:10])) != wk:
            return empty(f"No weekly snapshot for {week}. The latest is the week of {wk.isoformat()}.", wk)
        rows = con.execute(GROUPS_SQL.format(ei=NEW_EI_DAYS, gap=GAP_DAYS), [snap, snap]).fetchall()
        cols = ["employer_key", "industry_naics2", "n_customers", "n_payroll_gap", "n_new_ei",
                "avg_payroll_change_pct", "open_cases", "exposure_cad"]
        groups = [{**dict(zip(cols, r, strict=True)), "week_start": wk, "members": []} for r in rows]
        events = con.execute("SELECT event_id, event_type, description, affected_tables, start_ts, end_ts "
                             "FROM silver.ops_events").fetchall()
        ev = [dict(zip(("event_id", "event_type", "description", "affected_tables", "start_ts", "end_ts"), e,
                       strict=True)) for e in events]
    finally:
        if own:
            con.close()
    rated = public(rate_groups(groups, ev))
    flagged = [r for r in rated if r["pattern"] != "none"]
    hidden = sum(1 for g in groups if g["n_customers"] < MIN_GROUP)
    return {
        "week_start": wk.isoformat(), "label": LABEL, "min_group": MIN_GROUP, "rows": rated[:limit],
        "employers_shown": len(rated), "employers_hidden_small": hidden, "clusters": len(flagged),
        "known_incidents": known_incidents(wk, ev),
        "summary": (f"{len(flagged)} employer(s) show a cluster out of {len(rated)} with at least "
                    f"{MIN_GROUP} customers."
                    if flagged else
                    f"No cluster: none of the {len(rated)} employers with at least {MIN_GROUP} customers has an "
                    f"unusual share of late payroll this week."),
        "own_history": "n/a: the release holds one full weekly snapshot",
    }


def empty(message: str, week: dt.date | None = None) -> dict[str, Any]:
    return {"week_start": week.isoformat() if week else None, "label": LABEL, "min_group": MIN_GROUP, "rows": [],
            "employers_shown": 0, "employers_hidden_small": 0, "clusters": 0, "known_incidents": [],
            "summary": message, "own_history": "n/a"}


MEMBERS_SQL = """
SELECT g.golden_id, k.golden_id IS NOT NULL AS behind
FROM (SELECT g.golden_id FROM silver.customers c JOIN identity.crm_golden g USING (crm_customer_id)
      WHERE c.employer_name IS NOT NULL AND c.effective_to_ts >= TIMESTAMP '9999-01-01'
        AND 'EMP-' || upper(substr(md5(lower(trim(c.employer_name))), 1, 8)) = ? GROUP BY 1) g
LEFT JOIN (SELECT DISTINCT x.golden_id FROM silver.collections_cases k JOIN identity.case_xref x USING (case_id)
           WHERE k.case_status = 'open') k USING (golden_id)
"""


def members(employer_key: str, con=None) -> dict[str, list[str]]:
    """Customers of one flagged employer, split into already behind (an open case) and not yet behind."""
    from common.db import warehouse

    own = con is None
    con = con or warehouse(read_only=True)
    try:
        rows = con.execute(MEMBERS_SQL, [employer_key]).fetchall()
    finally:
        if own:
            con.close()
    return {"members_behind": sorted(g for g, b in rows if b),
            "members_not_behind": sorted(g for g, b in rows if not b)}
