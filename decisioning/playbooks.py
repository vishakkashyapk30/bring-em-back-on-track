"""Team-lead playbooks (S1 employer radar, H5 outage shield, regional areas): proposals that wait for a person.

* Every proposal is created `pending_approval`. Nothing runs by itself, and nothing here contacts a customer.
* Kinds: `contact` (reach out early), `hold` (pause pressure steps), and from the outage shield `fee_reversal` and
  `pressure_hold`.
* A `contact` playbook aimed at customers who are not yet behind needs Policy Office sign-off
  (`requires_policy_office_signoff`): the team lead's approval is recorded, but the batch it creates waits as
  `awaiting_policy_office` and is not offered for sending until the Policy Office signs off.
* Approving is audited (`governance.audit.record`) and creates one batch in the existing approval flow
  (`batches`, with the 2% sample first, `decisioning.nba.sample_size`). Only the `team_lead` role may approve.

The proposals live in the ops store (`playbook_proposals`, created on first use). Rules only: works offline.
"""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Iterable, Mapping
from typing import Any

from common.db import ops
from governance import audit

APPROVER = "team_lead"
PENDING = "pending_approval"

SCHEMA = """
CREATE TABLE IF NOT EXISTS playbook_proposals (
    proposal_id   TEXT PRIMARY KEY,
    playbook      TEXT NOT NULL,        -- employer_radar | outage_shield | regional
    kind          TEXT NOT NULL,        -- contact | hold | fee_reversal | pressure_hold
    subject_id    TEXT NOT NULL,
    title         TEXT NOT NULL,
    detail        TEXT NOT NULL,
    payload_json  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending_approval',
    requires_role TEXT NOT NULL DEFAULT 'team_lead',
    requires_policy_office_signoff INTEGER NOT NULL DEFAULT 0,
    created_ts    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    decided_by    TEXT,
    decided_ts    TEXT,
    decision_note TEXT,
    batch_id      TEXT
);
"""


def _con_ready(con) -> None:
    con.executescript(SCHEMA)


def _row(r: Mapping[str, Any]) -> dict[str, Any]:
    d = dict(r)
    d["payload"] = json.loads(d.pop("payload_json"))
    d["requires_policy_office_signoff"] = bool(d["requires_policy_office_signoff"])
    return d


def _insert(con, p: dict[str, Any]) -> bool:
    cur = con.execute(
        """INSERT OR IGNORE INTO playbook_proposals (proposal_id, playbook, kind, subject_id, title, detail,
           payload_json, requires_role, requires_policy_office_signoff) VALUES (?,?,?,?,?,?,?,?,?)""",
        (p["proposal_id"], p["playbook"], p["kind"], p["subject_id"], p["title"], p["detail"],
         json.dumps(p["payload"], default=str), APPROVER, int(p.get("requires_policy_office_signoff", False))))
    return cur.rowcount > 0


# ------------------------------------------------------------------ building proposals (pure)
def from_radar(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Employer radar rows with a pattern become playbook proposals. A known incident means wait, do not contact."""
    out = []
    for r in rows:
        if r["pattern"] == "none":
            continue
        key, week = r["employer_key"], r["week_start"]
        behind, not_behind = list(r.get("members_behind") or []), list(r.get("members_not_behind") or [])
        base = {"playbook": "employer_radar", "subject_id": key,
                "payload": {"employer_key": key, "week_start": week, "pattern": r["pattern"],
                            "n_customers": r["n_customers"], "n_payroll_gap": r["n_payroll_gap"],
                            "n_new_ei": r["n_new_ei"], "explained_by_incident": r.get("explained_by_incident"),
                            "label": r["label"]}}
        if behind or not r.get("members"):
            out.append({**base, "proposal_id": f"PB-HOLD-{key}-{week}", "kind": "hold",
                        "title": f"Hold pressure steps for customers already behind at employer {key}",
                        "detail": (f"{r['n_payroll_gap']} of {r['n_customers']} customers show late payroll "
                                   f"({r['pattern'].replace('_', ' ')}). Pause escalation for those already behind "
                                   "until payday or a review."),
                        "payload": {**base["payload"], "customer_ids": behind, "audience": "already_behind"}})
        if r["pattern"] == "layoff_like" and not r.get("explained_by_incident") and not_behind:
            out.append({**base, "proposal_id": f"PB-CONTACT-{key}-{week}", "kind": "contact",
                        "title": f"Offer early help to customers not yet behind at employer {key}",
                        "detail": (f"{r['n_new_ei']} customers have new EI deposits. Reach out with help options "
                                   "before a payment is missed. Needs Policy Office sign-off because these "
                                   "customers are not yet behind."),
                        "requires_policy_office_signoff": True,
                        "payload": {**base["payload"], "customer_ids": not_behind, "audience": "not_yet_behind"}})
    return out


def from_outage(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """H5: each candidate gets a fee reversal proposal (when a fee was charged) and a pressure hold proposal."""
    out = []
    for p in report["proposals"]:
        out.append({"proposal_id": f"H5-{report['event_id']}-{p['proposal_id']}", "playbook": "outage_shield",
                    "kind": p["kind"], "subject_id": p["subject_id"],
                    "title": ("Reverse the late fee" if p["kind"] == "fee_reversal" else "Hold pressure actions")
                    + f" ({report['event_id']} outage victim)",
                    "detail": p["detail"] + " Candidate list: payment attempt times are sample-only.",
                    "payload": {"event_id": report["event_id"], "golden_id": p.get("golden_id"),
                                "customer_ids": [p["subject_id"]], "note": report.get("note")}})
    return out


def from_areas(areas: Iterable[Mapping[str, Any]], min_group: int = 10, multiple: float = 2.0,
               floor: float = 0.15) -> list[dict[str, Any]]:
    """Regional playbooks from the weather map: an area with at least `min_group` customers whose broken-promise
    rate is at least `multiple` times the overall rate (and above `floor`) gets a hold and a contact proposal."""
    areas = [a for a in areas if a["n_customers"] >= min_group]
    n = sum(a["n_customers"] for a in areas)
    overall = sum(a["broken_promise_rate"] * a["n_customers"] for a in areas) / n if n else 0.0
    out = []
    for a in areas:
        if a["broken_promise_rate"] < max(floor, multiple * overall):
            continue
        area = a["area"]
        payload = {"area": area, "n_customers": a["n_customers"], "broken_promise_rate": a["broken_promise_rate"],
                   "overall_rate": round(overall, 4), "label": "observed, not causal"}
        out.append({"proposal_id": f"PB-REGION-HOLD-{area}", "playbook": "regional", "kind": "hold",
                    "subject_id": area, "title": f"Hold pressure steps in area {area}", "payload": payload,
                    "detail": f"Broken promises are high in {area} ({a['broken_promise_rate']:.0%} against "
                              f"{overall:.0%} overall). Pause escalation while a person looks at why."})
        out.append({"proposal_id": f"PB-REGION-CONTACT-{area}", "playbook": "regional", "kind": "contact",
                    "subject_id": area, "title": f"Offer early help in area {area}", "payload": payload,
                    "requires_policy_office_signoff": True,
                    "detail": "Reach out to customers in this area who are not yet behind. Needs Policy Office "
                              "sign-off."})
    return out


# ------------------------------------------------------------------ the store
def store(proposals: Iterable[Mapping[str, Any]]) -> int:
    """Insert new proposals (existing ones, decided or not, are left alone). Returns how many were new."""
    n = 0
    with ops() as con:
        _con_ready(con)
        for p in proposals:
            n += _insert(con, dict(p))
    return n


def listing(status: str | None = None) -> list[dict[str, Any]]:
    with ops() as con:
        _con_ready(con)
        where = " WHERE status = ?" if status else ""
        q = f"SELECT * FROM playbook_proposals{where} ORDER BY created_ts, proposal_id"
        return [_row(r) for r in con.execute(q, (status,) if status else ()).fetchall()]


def get(proposal_id: str) -> dict[str, Any] | None:
    with ops() as con:
        _con_ready(con)
        r = con.execute("SELECT * FROM playbook_proposals WHERE proposal_id = ?", (proposal_id,)).fetchone()
    return _row(r) if r else None


def approve(proposal_id: str, user_id: str, role: str, team_id: str | None = None, note: str | None = None,
            today: dt.date | None = None) -> dict[str, Any]:
    """A team lead approves one proposal. It creates a batch for the existing approval and 2% sample flow and
    contacts nobody. Raises PermissionError (wrong role), KeyError (unknown) or ValueError (already decided)."""
    if str(role) != APPROVER:
        raise PermissionError(f"Only a {APPROVER} approves playbooks, not the {role} role")
    p = get(proposal_id)
    if p is None:
        raise KeyError(proposal_id)
    if p["status"] != PENDING:
        raise ValueError(f"This proposal has already been dealt with ({p['status']})")
    from decisioning.nba import sample_size

    items = sorted({str(i) for i in (p["payload"].get("customer_ids") or [p["subject_id"]])})
    sample = items[: sample_size(len(items))]
    signoff = p["requires_policy_office_signoff"]
    day = (today or dt.date.today()).strftime("%Y%m%d")
    batch_id = f"B-{day}-PLAYBOOK-PB{abs(hash_id(proposal_id)) % 16**6:06X}-{team_id or 'POOL'}"
    batch_kind = "outage_playbook" if p["playbook"] == "outage_shield" else "radar_playbook"
    status = "awaiting_policy_office" if signoff else "pending"
    audit_id = audit.record(user_id, role, "playbook_approve", "playbook_proposal", proposal_id,
                            {"proposal_id": proposal_id, "kind": p["kind"], "note": note},
                            {"batch_id": batch_id, "items": len(items), "batch_status": status,
                             "contacts_anyone": False})
    with ops() as con:
        con.execute("INSERT OR IGNORE INTO batches (batch_id, kind, strategy_code, items_json, sample_json, status) "
                    "VALUES (?,?,?,?,?,?)",
                    (batch_id, batch_kind, f"{p['kind']}:playbook", json.dumps(items), json.dumps(sample), status))
        con.execute("UPDATE playbook_proposals SET status='approved', decided_by=?, decision_note=?, batch_id=?, "
                    "decided_ts=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE proposal_id=?",
                    (user_id, note, batch_id, proposal_id))
    return {"proposal_id": proposal_id, "status": "approved", "batch_id": batch_id, "batch_status": status,
            "items": len(items), "sample_size": len(sample), "audit_id": audit_id,
            "note": ("Approved. The batch waits for Policy Office sign-off before anyone can be contacted."
                     if signoff else "Approved. A batch was created for the usual sample check and approval.")}


def reject(proposal_id: str, user_id: str, role: str, reason: str) -> dict[str, Any]:
    if str(role) != APPROVER:
        raise PermissionError(f"Only a {APPROVER} decides playbooks, not the {role} role")
    if not (reason or "").strip():
        raise ValueError("Rejecting a proposal needs a reason")
    p = get(proposal_id)
    if p is None:
        raise KeyError(proposal_id)
    if p["status"] != PENDING:
        raise ValueError(f"This proposal has already been dealt with ({p['status']})")
    audit_id = audit.record(user_id, role, "playbook_reject", "playbook_proposal", proposal_id,
                            {"proposal_id": proposal_id, "reason": reason}, {"status": "rejected"})
    with ops() as con:
        con.execute("UPDATE playbook_proposals SET status='rejected', decided_by=?, decision_note=?, "
                    "decided_ts=strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE proposal_id=?",
                    (user_id, reason, proposal_id))
    return {"proposal_id": proposal_id, "status": "rejected", "audit_id": audit_id}


def hash_id(s: str) -> int:
    """A stable number from a string (Python's hash() changes between runs)."""
    import hashlib

    return int(hashlib.sha1(s.encode()).hexdigest()[:8], 16)


# ------------------------------------------------------------------ from the real warehouse
def generate_from_warehouse() -> dict[str, Any]:
    """Run the radar and the outage shield on the real warehouse and store what they propose (nightly job)."""
    from decisioning import outage_shield, radar

    r = radar.employer_week(limit=10**9)
    flagged = [x for x in r["rows"] if x["pattern"] != "none"]
    for x in flagged:
        x.update(radar.members(x["employer_key"]))
        x["members"] = x["members_behind"] + x["members_not_behind"]
    proposals = from_radar(flagged)
    reports = outage_shield.candidates()
    for rep in reports:
        proposals += from_outage(rep)
    return {"new": store(proposals), "clusters": r["clusters"], "outage_events": len(reports)}
