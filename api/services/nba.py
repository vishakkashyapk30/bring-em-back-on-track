# ruff: noqa: E501
"""Queue, proposal, decision and batch services for Layer 4 (reads the nightly queue file, recomputes one case live)."""

from __future__ import annotations

import json
import math

import pandas as pd

from api.services.c360 import _meta
from common.db import ops
from decisioning import nba

LIST_COLS = [
    "case_id",
    "golden_id",
    "name",
    "product",
    "dpd",
    "treatment",
    "channel",
    "window",
    "program_id",
    "priority",
    "p_break",
    "risk_band",
    "hardship_flag",
    "vulnerable",
    "route_to",
    "review_mode",
    "headline",
    "status",
    "deferred_reason",
    "assigned_agent_id",
    "assigned_team",
    "overdue",
]


def _clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def _latest_decisions(case_ids: list[str]) -> dict[str, dict]:
    if not case_ids:
        return {}
    with ops() as con:
        q = ",".join("?" * len(case_ids))
        rows = con.execute(
            f"""SELECT case_id, decision, reason_code, user_id, ts FROM nba_decisions d
                               WHERE decision_id = (SELECT max(decision_id) FROM nba_decisions x WHERE x.case_id = d.case_id)
                               AND case_id IN ({q})""",
            case_ids,
        ).fetchall()
    return {r["case_id"]: dict(r) for r in rows}


FILTERS = {
    "all": lambda d: d.treatment != "no_contact",
    "calls": lambda d: (d.channel == "call") & (d.treatment != "no_contact"),
    "digital": lambda d: d.channel.isin(["sms", "email", "push"]),
    "hardship": lambda d: (d.hardship_flag != "none") & (d.treatment != "no_contact"),
    "vulnerable": lambda d: d.vulnerable.astype(bool) & (d.treatment != "no_contact"),
    "high_risk": lambda d: d.risk_band.isin(["high", "very_high"]) & (d.treatment != "no_contact"),
    "tomorrow": lambda d: d.status == "deferred",
    "batch": lambda d: d.review_mode == "batch",
    "no_contact": lambda d: d.treatment == "no_contact",
}
SORTS = {
    "priority": ("priority", False),
    "risk": ("p_break", False),
    "overdue": ("overdue", False),
    "dpd": ("dpd", False),
    "name": ("name", True),
}


def queue(session, view: str = "all", sort: str = "priority", q: str = "", offset: int = 0, limit: int = 50) -> dict:
    path = nba.queue_path()
    if not path.exists():
        return {
            "meta": _meta(),
            "date": None,
            "items": [],
            "total": 0,
            "counts": {},
            "note": "The nightly queue has not been built yet.",
        }
    df = pd.read_parquet(path, columns=LIST_COLS + ["plan_date"])
    role = session.role.value if hasattr(session.role, "value") else session.role
    if role == "agent":
        mine = df[df.assigned_agent_id == session.user_id]
        scope = f"your {len(mine):,} cases"
    elif role == "hardship_specialist":
        site = (session.team_id or "").split("-")[0]
        mine = df[(df.route_to == "hardship_specialist") & (df.assigned_team.fillna("").str.startswith(site))]
        scope = f"hardship cases at the {site} site"
    else:  # team lead
        mine = df[df.assigned_team == session.team_id]
        scope = f"team {session.team_id}"
    # the worklist excludes routine reminders that go through a batch (the team lead approves those)
    work = mine[(mine.treatment != "no_contact") & ((mine.review_mode == "individual") | (role == "team_lead"))]
    pool = mine if view in ("batch", "no_contact") else work
    pick = FILTERS.get(view, FILTERS["all"])
    shown = pool[pick(pool)]
    if q.strip():
        needle = q.strip().lower()
        shown = shown[
            shown.name.str.lower().str.contains(needle, regex=False)
            | shown.case_id.str.lower().str.contains(needle, regex=False)
            | shown["product"].str.lower().str.contains(needle.replace(" ", "_"), regex=False)
        ]
    col, asc = SORTS.get(sort, SORTS["priority"])
    shown = shown.sort_values([col, "priority"], ascending=[asc, False], na_position="last")
    counts = {
        "in_scope": int(len(mine)),
        "all": int(len(work)),
        "calls": int(FILTERS["calls"](work).sum()),
        "digital": int(FILTERS["digital"](work).sum()),
        "hardship": int(FILTERS["hardship"](work).sum()),
        "vulnerable": int(FILTERS["vulnerable"](work).sum()),
        "high_risk": int(FILTERS["high_risk"](work).sum()),
        "tomorrow": int((mine.status == "deferred").sum()),
        "batch": int((mine.review_mode == "batch").sum()),
        "no_contact": int((mine.treatment == "no_contact").sum()),
    }
    top = shown.iloc[offset : offset + limit]
    dec = _latest_decisions(top.case_id.tolist())
    items = []
    for r in top.to_dict("records"):
        r = {k: _clean(v) for k, v in r.items()}
        items.append(
            {
                "case_id": r["case_id"],
                "golden_id": r["golden_id"],
                "name": r["name"],
                "product": r["product"],
                "dpd": r["dpd"],
                "action": {
                    "treatment": r["treatment"],
                    "channel": r["channel"],
                    "window": r["window"],
                    "program_id": r["program_id"],
                },
                "priority": r["priority"],
                "risk_band": r["risk_band"],
                "p_break": r["p_break"],
                "hardship_flag": r["hardship_flag"],
                "vulnerable": r["vulnerable"],
                "route_to": r["route_to"],
                "review_mode": r["review_mode"],
                "headline": r["headline"],
                "status": r["status"],
                "deferred_reason": r["deferred_reason"],
                "overdue": r["overdue"],
                "decision": dec.get(r["case_id"]),
            }
        )
    return {
        "meta": _meta(),
        "date": str(df.plan_date.iloc[0]),
        "scope": scope,
        "items": items,
        "total": int(len(shown)),
        "view": view,
        "sort": sort,
        "offset": offset,
        "counts": counts,
    }


def proposal(case_id: str, session=None) -> dict | None:
    p = nba.propose(case_id)
    if p is None:
        return None
    if session is not None:  # V1 section 10: every score and proposal is audited
        a = p["action"]
        nba.audit_proposal(
            case_id,
            a["treatment"],
            a.get("channel"),
            p["explanation"]["model_evidence"].get("p_break"),
            [r["code"] for r in p["explanation"]["rules_applied"]],
            session.user_id,
            session.role,
        )
    p["meta"] = _meta()
    p["decision"] = _latest_decisions([case_id]).get(case_id)
    return p


def record_decision(session, case_id: str, body) -> int:
    from governance import audit

    p = nba.propose(case_id)
    if p is None:
        raise KeyError(case_id)
    final = body.action.model_dump(mode="json") if body.action else p["action"]
    if body.decision == "edit":
        ok = [(p["action"]["treatment"], p["action"]["channel"])] + [
            (a["action"]["treatment"], a["action"]["channel"])
            for a in p["explanation"]["alternatives"]
            if a.get("allowed")
        ]
        if (final["treatment"], final.get("channel")) not in ok:
            raise ValueError("The contact rules do not allow that action for this customer")
    audit_id = audit.record(
        session.user_id,
        session.role,
        "nba_decision" if body.decision == "approve" else body.decision,
        "case",
        case_id,
        body.model_dump(mode="json"),
        {"proposed": p["action"], "final": final},
    )
    with ops() as con:
        con.execute(
            """INSERT INTO nba_decisions (case_id, golden_id, proposed_json, decision, final_json, reason_code, note, user_id, audit_id)
                       VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                case_id,
                p["golden_id"],
                json.dumps({"action": p["action"], "explanation": p["explanation"]}, default=str),
                body.decision,
                json.dumps(final),
                body.reason_code,
                body.note,
                session.user_id,
                audit_id,
            ),
        )
    return audit_id


def batches(status: str = "pending", team_id: str | None = None) -> dict:
    with ops() as con:
        rows = con.execute("SELECT * FROM batches WHERE status = ? ORDER BY batch_id", (status,)).fetchall()
    q = pd.read_parquet(nba.queue_path()) if nba.queue_path().exists() else None
    items = []
    for r in rows:
        ids, sample = json.loads(r["items_json"]), json.loads(r["sample_json"] or "[]")
        # batch ids end with the team ID (which itself contains dashes): B-<date>-<channel>-<treatment>-<team>
        parts = r["batch_id"].split("-", 4)
        team = parts[4] if len(parts) > 4 else ""
        if team_id and team != team_id:
            continue
        s = []
        if q is not None:
            sub = q[q.case_id.isin(sample)].sort_values("priority", ascending=False).head(10)
            s = [
                {
                    "case_id": x.case_id,
                    "name": x.name,
                    "product": x["product"],
                    "dpd": int(x.dpd),
                    "p_break": _clean(x.p_break),
                    "headline": x.headline,
                }
                for _, x in sub.iterrows()
            ]
        treat, ch = r["strategy_code"].split(":")
        items.append(
            {
                "batch_id": r["batch_id"],
                "kind": r["kind"],
                "strategy_code": r["strategy_code"],
                "treatment": treat,
                "channel": ch,
                "team": team,
                "count": len(ids),
                "sample_size": len(sample),
                "sample": s,
                "status": r["status"],
                "approved_by": r["approved_by"],
                "approved_ts": r["approved_ts"],
            }
        )
    return {"meta": _meta(), "items": items}


def approve_batch(session, batch_id: str) -> int:
    from governance import audit

    with ops() as con:
        row = con.execute("SELECT status, items_json FROM batches WHERE batch_id = ?", (batch_id,)).fetchone()
    if row is None:
        raise KeyError(batch_id)
    if row["status"] != "pending":
        raise ValueError("Batch is already " + row["status"])
    n = len(json.loads(row["items_json"]))
    audit_id = audit.record(
        session.user_id, session.role, "batch_approve", "batch", batch_id, {"batch_id": batch_id}, {"count": n}
    )
    with ops() as con:
        con.execute(
            "UPDATE batches SET status='approved', approved_by=?, approved_ts=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE batch_id=?",
            (session.user_id, batch_id),
        )
    return audit_id
