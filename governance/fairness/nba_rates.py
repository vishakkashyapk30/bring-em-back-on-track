"""NBA decision fairness by group: does the next-best-action queue treat protected groups the same way?

Reads the current queue (data/features/nba_queue.parquet, one row per open case, written by decisioning.nba) and joins
the protected attributes through the restricted auditor view, here only. Nothing is joined back into features or
decisions. Per group (aggregates only; groups under `suppression_min_group` customers hidden): action mix, pressure
rate, contact rate, no-contact rate, hardship or vulnerable routing rate, scheduled rate, mean break risk and mean
expected value (the allocator's priority score). A group goes to "review" when it has at least MIN_GROUP cases and a
rate is outside 0.8x to 1.25x of the overall rate. Review means a person looks and explains it, not an automatic change.

It also checks the design claim "higher break risk never raised pressure for a hardship or vulnerable customer":
(1) no such customer was given a pressure action, and (2) re-deciding each of them at a low and a high break risk
never turns pressure on. Both counts should be 0.

Run: python -m governance.fairness.nba_rates
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from common.config import get_settings
from common.types import PRESSURE_TREATMENTS

# ruff: noqa: E501
MIN_GROUP = 300
RATIO_REVIEW = (0.8, 1.25)
LOW_P, HIGH_P = 0.05, 0.95
TREATMENTS = ["reminder", "payment_link", "plan_offer", "specialist_referral", "no_contact"]
PRESSURE = {t.value for t in PRESSURE_TREATMENTS}
# Rates that are compared with the overall rate (ratio and flag).
FLAGGED = ["pressure_rate", "contact_rate", "no_contact_rate", "routing_rate"]
MEANS = ["mean_risk", "mean_value"]
# Where a difference is the intended gentler treatment, a flag is explained rather than a surprise.
BY_DESIGN = {"vulnerability_type"}


def _prep(q: pd.DataFrame) -> pd.DataFrame:
    d = q.copy()
    d["is_pressure"] = d.treatment.isin(PRESSURE)
    d["is_contact"] = d.treatment != "no_contact"
    d["is_routed"] = d.route_to.notna()
    d["is_care"] = (d.hardship_flag.fillna("none") != "none") | d.vulnerable.fillna(False).astype(bool) | d.is_routed
    d["is_scheduled"] = d.status == "scheduled"
    return d


def _rates(g: pd.DataFrame) -> dict:
    n = len(g)
    out = {
        "cases": int(n),
        "customers": int(g.golden_id.nunique()),
        "pressure_rate": float(g.is_pressure.mean()),
        "contact_rate": float(g.is_contact.mean()),
        "no_contact_rate": float((~g.is_contact).mean()),
        "routing_rate": float(g.is_routed.mean()),
        "scheduled_rate": float(g.is_scheduled.mean()),
        "mean_risk": float(g.p_break.mean()) if g.p_break.notna().any() else None,
        "mean_value": float(g.priority.mean()),
        "risk_scored": int(g.p_break.notna().sum()),
    }
    out["mix"] = {t: float((g.treatment == t).mean()) for t in TREATMENTS}
    return out


def _round(v):
    return round(v, 4) if isinstance(v, float) else v


def _group_row(g: pd.DataFrame, overall: dict, attr: str, min_group: int) -> dict:
    r = _rates(g)
    ratios, flags = {}, []
    for k in FLAGGED + MEANS:
        base = overall[k]
        ratios[k] = round(r[k] / base, 3) if base and r[k] is not None else None
    low = r["cases"] < min_group
    if not low:
        flags = [k for k in FLAGGED
                 if ratios[k] is not None and not RATIO_REVIEW[0] <= ratios[k] <= RATIO_REVIEW[1]]
    status = "low volume" if low else ("review" if flags else "ok")
    return {
        **{k: (_round(v) if not isinstance(v, dict) else {t: _round(x) for t, x in v.items()}) for k, v in r.items()},
        "ratios": ratios,
        "flags": flags,
        "by_design": bool(flags) and attr in BY_DESIGN,
        "status": status,
    }


def by_group(queue: pd.DataFrame, protected: pd.DataFrame, attributes: list[str], min_group: int = MIN_GROUP,
             suppression_min: int = 10) -> dict:
    """Aggregates by each protected attribute. `protected` has golden_id plus the attribute columns."""
    d = _prep(queue).merge(protected, on="golden_id", how="left")
    overall = _rates(d)
    attrs = []
    for attr in attributes:
        vals = d[attr].astype("string").fillna("unknown")
        groups, hidden = [], 0
        for val, g in d.groupby(vals, observed=True):
            if g.golden_id.nunique() < suppression_min:
                hidden += 1
                continue
            groups.append({"group": str(val), **_group_row(g, overall, attr, min_group)})
        groups.sort(key=lambda r: -r["cases"])
        attrs.append({"attribute": attr, "groups": groups, "suppressed_groups": hidden,
                      "reviews": sum(r["status"] == "review" for r in groups),
                      "unexplained_reviews": sum(r["status"] == "review" and not r["by_design"] for r in groups)})
    return {"overall": {k: (_round(v) if not isinstance(v, dict) else {t: _round(x) for t, x in v.items()})
                        for k, v in overall.items()}, "attributes": attrs}


def risk_never_raised_pressure(queue: pd.DataFrame, redecide=None) -> dict:
    """The design claim for hardship and vulnerable customers.

    `observed`: care customers given a pressure action (expect 0). `counterfactual`: care customers for whom
    re-deciding at a high break risk gives pressure where a low break risk did not (expect 0); needs `redecide`,
    a function (case_id, p_break) -> treatment, and is skipped (None) without it."""
    d = _prep(queue)
    care = d[d.is_care]
    scored = care[care.p_break.notna()]
    band = pd.cut(scored.p_break, [-0.01, 0.35, 0.55, 1.0], labels=["low", "medium", "high"])
    by_band = {str(b): {"cases": int((band == b).sum()), "pressure": int(scored[band == b].is_pressure.sum())}
               for b in ["low", "medium", "high"]}
    observed = int(care.is_pressure.sum())
    out = {
        "claim": "Higher break risk never raised pressure for a hardship or vulnerable customer",
        "care_cases": int(len(care)),
        "care_customers": int(care.golden_id.nunique()),
        "pressure_among_care": observed,
        "pressure_by_risk_band": by_band,
        "counterfactual_checked": None,
        "counterfactual_violations": None,
    }
    violations = observed
    if redecide is not None:
        bad = checked = 0
        for cid in care.case_id:
            lo, hi = redecide(cid, LOW_P), redecide(cid, HIGH_P)
            checked += 1
            bad += int(hi in PRESSURE and lo not in PRESSURE)
        out["counterfactual_checked"], out["counterfactual_violations"] = checked, bad
        violations += bad
    out["violations"] = violations
    out["holds"] = violations == 0
    return out


def _live_redecide(case_ids: set[str]):
    """Re-run the real policy gate and ladder for a case at a chosen break risk."""
    from decisioning import context, nba

    rows = {r["case_id"]: r for r in context.load_cases() if r["case_id"] in case_ids}

    def redecide(case_id: str, p: float) -> str:
        return nba.decide({**rows[case_id], "p_break": p})["action"].treatment.value

    return redecide


def build(with_counterfactual: bool = True) -> dict:
    from decisioning import nba
    from governance.fairness import auditor

    s = get_settings()
    queue = pd.read_parquet(nba.queue_path())
    res = by_group(queue, auditor.load(), auditor.ATTRIBUTES, MIN_GROUP, s.suppression_min_group)
    q = _prep(queue)
    redecide = _live_redecide(set(q[q.is_care].case_id)) if with_counterfactual else None
    claim = risk_never_raised_pressure(queue, redecide)
    items = [f"{a['attribute']}: {r['group']} ({', '.join(r['flags'])}" + (", by design)" if r["by_design"] else ")")
             for a in res["attributes"] for r in a["groups"] if r["status"] == "review"]
    return {
        "meta": {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "source": "nba_queue.parquet + restricted view",
                 "plan_date": str(queue.plan_date.iloc[0]), "cases": int(len(queue)),
                 "scheduled": int((queue.status == "scheduled").sum()), "fixture": False},
        "thresholds": {"min_group": MIN_GROUP, "ratio": list(RATIO_REVIEW), "flagged_metrics": FLAGGED,
                       "counterfactual_risk": [LOW_P, HIGH_P]},
        **res,
        "design_claim": claim,
        "review_items": items,
        "note": "Aggregates only; groups under 10 customers are hidden and groups under 300 cases are not judged. "
                "Protected attributes are read only by governance/fairness and are never decision inputs.",
    }


def _md(rep: dict) -> str:
    m, c, o = rep["meta"], rep["design_claim"], rep["overall"]
    pc = lambda v: "n/a" if v is None else f"{v * 100:.1f}%"  # noqa: E731
    L = ["# NBA decision fairness by group", "",
         f"Generated {m['generated_at']} for plan date {m['plan_date']}: {m['cases']:,} open cases, {m['scheduled']:,} scheduled. "
         "Aggregates only; groups under 10 customers are hidden and groups under 300 cases are not judged. "
         "Flag: a rate outside 0.8x to 1.25x of the overall rate. A flag means a person looks and explains it.", "",
         "## Design claim", "",
         f"Claim: {c['claim']}.", "",
         f"- Hardship or vulnerable cases: {c['care_cases']:,} ({c['care_customers']:,} customers).",
         f"- Pressure actions given to them: {c['pressure_among_care']}.",
         f"- Counterfactual (re-decided at break risk {LOW_P} and {HIGH_P}): "
         + ("not run." if c["counterfactual_checked"] is None else
            f"{c['counterfactual_checked']:,} cases checked, {c['counterfactual_violations']} where high risk turned pressure on."),
         f"- Violations: {c['violations']}. The claim {'holds' if c['holds'] else 'DOES NOT HOLD'}.", "",
         "## Overall", "",
         f"Pressure {pc(o['pressure_rate'])}, contact {pc(o['contact_rate'])}, no contact {pc(o['no_contact_rate'])}, "
         f"routed to a person {pc(o['routing_rate'])}, scheduled {pc(o['scheduled_rate'])}, "
         f"mean break risk {o['mean_risk']}, mean expected value {o['mean_value']}.", ""]
    for a in rep["attributes"]:
        L += [f"## {a['attribute']}", "",
              "| Group | Cases | Pressure | Contact | No contact | Routed | Mean risk | Mean value | Flags | Status |",
              "|---|---|---|---|---|---|---|---|---|---|"]
        for r in a["groups"]:
            fl = ", ".join(r["flags"]) + (" (by design)" if r["by_design"] else "") if r["flags"] else "none"
            L.append(f"| {r['group']} | {r['cases']:,} | {pc(r['pressure_rate'])} ({r['ratios']['pressure_rate']}x) | "
                     f"{pc(r['contact_rate'])} | {pc(r['no_contact_rate'])} | {pc(r['routing_rate'])} | "
                     f"{r['mean_risk']} | {r['mean_value']} | {fl} | {r['status']} |")
        if a["suppressed_groups"]:
            L += ["", f"{a['suppressed_groups']} group(s) with fewer than 10 customers are hidden."]
        L.append("")
    return "\n".join(L)


def main() -> None:
    s = get_settings()
    rep = build()
    p = s.reports_dir / "fairness_nba.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rep, indent=2, default=str))
    doc = s.reports_dir.parent / "docs" / "fairness_nba.md"
    doc.write_text(_md(rep))
    print(f"wrote {p} and {doc}: {len(rep['review_items'])} flagged groups, "
          f"{rep['design_claim']['violations']} design-claim violations")
    for r in rep["review_items"]:
        print(" -", r)


if __name__ == "__main__":
    main()
