# ruff: noqa: E501
"""'Waiting for you': one list per persona of every pending human review across the system.

Read-only. Each source reads the same store the real screen reads (ops.db tables, the nightly queue file, the
warehouse, reports/), applies the persona's row scope (docs/reference/row_scope.md) and links to the screen where the person
acts. Nothing here approves anything: approval logic stays in the existing routes.

A source that does not exist in the code, or cannot be read right now (no warehouse loaded, no queue built), is
listed under `not_available` with the reason instead of failing the whole inbox.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import UTC, date, datetime

import numpy as np

from api.deps import live_data
from api.schemas.common import Session
from api.schemas.inbox import InboxCounts, InboxGroup, InboxItem, InboxResponse, NotAvailable
from common.config import get_settings
from common.db import ops
from common.types import Role

log = logging.getLogger(__name__)

SHOW = 8                     # items listed per group (the count covers them all)
SUMMARY_WINDOW_DAYS = 14     # post-call drafts from the last two weeks of calls
PROMISE_WINDOW_DAYS = 7      # promises due within a week
HIGH_RISK = ("high", "very_high")
MIN_DECISIONS_FOR_OVERRIDE_REVIEW = 5
PENDING_PROPOSAL = {"pending", "pending_approval", "proposed", "submitted", "open", "awaiting_approval", "awaiting_review"}
CACHE_SECONDS = 20.0         # the nav badge polls; the full inbox always rebuilds

TREATMENT = {"reminder": "Reminder", "payment_link": "Payment link", "plan_offer": "Plan offer",
             "specialist_referral": "Specialist referral", "no_contact": "No contact"}
CHANNEL = {"call": "call", "sms": "text", "email": "email", "push": "app notice", "letter": "letter"}
FLAG_SOURCE = {"model": "the model", "agent_coded": "an agent", "customer_form": "the customer's form", "rule": "a rule",
               "llm_flag": "the call summary", "rule_s7": "a rule", "radar": "the employer radar", "specialist": "a specialist"}


class Unavailable(Exception):
    """This source cannot be read right now (or does not exist); the reason is shown to the person."""


# ------------------------------------------------------------------ small helpers
def _as_of() -> date:
    return get_settings().as_of_date


def _days_between(d: date | None, today: date) -> int | None:
    return None if d is None else max((today - d).days, 0)


def _to_date(v) -> date | None:
    if v is None or v != v or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if hasattr(v, "date"):  # pandas Timestamp
        return v.date()
    return date.fromisoformat(str(v)[:10])


def _ops_age(ts: str | None) -> int | None:
    """Days since an ops.db timestamp (real time: these rows are written by people using the app)."""
    if not ts:
        return None
    try:
        t = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=UTC)
    return max((datetime.now(UTC) - t).days, 0)


def _age_label(days: int | None) -> str:
    """'new today', 'waiting 1 day', 'waiting 4 days'."""
    if days is None:
        return "n/a"
    return "new today" if days == 0 else f"waiting {days} day{'s' if days != 1 else ''}"


def _ago(days: int | None, lead: str) -> str:
    """'last decision today', 'sent 3 days ago'."""
    if days is None:
        return "n/a"
    return f"{lead} today" if days == 0 else f"{lead} {days} day{'s' if days != 1 else ''} ago"


def _due_label(due: date, today: date) -> str:
    d = (due - today).days
    if d < 0:
        return f"{-d} day{'s' if d != -1 else ''} overdue"
    if d == 0:
        return "due today"
    return f"due in {d} day{'s' if d != 1 else ''}"


def _short(name) -> str:
    p = str(name or "").split()
    if len(p) >= 2 and not p[0].endswith("."):
        return f"{p[0][0]}. {p[-1]}"
    return str(name or "Customer")


def _money(v) -> str:
    return "n/a" if v is None or v != v else f"${float(v):,.0f}"


def _q(sql: str, params: list | None = None) -> list[dict]:
    from api.services.c360 import _q as q

    return q(sql, params)


def _need_live(what: str) -> None:
    if not live_data():
        raise Unavailable(f"No warehouse is loaded, so {what} can't be read yet.")


def _queue_frame(columns: list[str]):
    import pandas as pd

    from decisioning import nba

    _need_live("the nightly queue")
    path = nba.queue_path()
    if not path.exists():
        raise Unavailable("The nightly queue has not been built yet.")
    return pd.read_parquet(path, columns=columns)


def _decided_cases(case_ids: list[str]) -> set[str]:
    if not case_ids:
        return set()
    with ops() as con:
        out: set[str] = set()
        for i in range(0, len(case_ids), 500):
            chunk = case_ids[i:i + 500]
            rows = con.execute(f"SELECT DISTINCT case_id FROM nba_decisions WHERE case_id IN ({','.join('?' * len(chunk))})", chunk).fetchall()
            out |= {r["case_id"] for r in rows}
    return out


def _table_exists(con, name: str) -> bool:
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


# ------------------------------------------------------------------ agent and hardship specialist: NBA actions
def _scoped_queue(session: Session):
    """The same row scope the queue screen uses (api.services.nba.queue)."""
    df = _queue_frame(["case_id", "golden_id", "name", "treatment", "channel", "priority", "route_to", "review_mode",
                       "headline", "status", "assigned_agent_id", "assigned_team", "plan_date", "hardship_flag", "vulnerable"])
    if session.role == Role.agent:
        return df[df.assigned_agent_id == session.user_id]
    if session.role == Role.hardship_specialist:
        site = (session.team_id or "").split("-")[0]
        return df[(df.route_to == "hardship_specialist") & (df.assigned_team.fillna("").str.startswith(site))]
    return df[df.assigned_team == session.team_id]


def _why_individual(r: dict) -> str:
    if r.get("route_to") == "hardship_specialist":
        return "Signs of hardship: a specialist reviews this before any contact, and pressure steps stay paused."
    if r.get("route_to") == "vulnerable_customer_certified":
        return "Vulnerable customer: a certified person approves each step one by one."
    if r.get("treatment") == "plan_offer":
        return "Plan offers are reviewed one by one: approve, edit or override before anything is sent."
    if r.get("treatment") == "specialist_referral":
        return "A referral changes who works the case, so you confirm it first."
    if r.get("channel") == "call":
        return "Calls are approved one by one by the person who makes them."
    return "Reviewed one by one: approve, edit or override it before anything reaches the customer."


def nba_actions(session: Session) -> InboxGroup:
    mine = _scoped_queue(session)
    work = mine[(mine.treatment != "no_contact") & (mine.review_mode == "individual") & (mine.status == "scheduled")]
    decided = _decided_cases(work.case_id.tolist())
    work = work[~work.case_id.isin(decided)].sort_values("priority", ascending=False)
    today = _as_of()
    items = []
    for r in work.head(SHOW).to_dict("records"):
        age = _days_between(_to_date(r.get("plan_date")), today)
        what = f"{TREATMENT.get(r['treatment'], r['treatment'])}"
        if r.get("channel"):
            what += f" by {CHANNEL.get(r['channel'], r['channel'])}"
        items.append(InboxItem(
            id=f"nba:{r['case_id']}", type="nba_actions", title=f"{what} for {_short(r['name'])} ({r['case_id']})",
            reason=_why_individual(r), age_days=age, age_label="proposed today" if age == 0 else _age_label(age),
            link=f"/customers/{r['golden_id']}", subject_kind="case", subject_id=r["case_id"]))
    spec = session.role == Role.hardship_specialist
    return InboxGroup(
        type="nba_actions",
        label="Cases routed to a hardship specialist" if spec else "Next best actions to review",
        why=("The rules routed these cases to a specialist: nothing is sent until you approve, edit or override."
             if spec else "Each one waits for you to approve, edit or override it before anything reaches the customer."),
        count=int(len(work)), items=items, link="/queue", link_label="Open the queue")


# ------------------------------------------------------------------ agent: post-call summaries
def call_summaries(session: Session) -> InboxGroup:
    _need_live("your calls")
    today = _as_of()
    rows = _q("""
        SELECT t.contact_id, t.case_id, CAST(t.call_start_ts AS DATE) AS call_day, k.golden_id
        FROM silver.call_transcripts t
        JOIN silver.collections_cases c ON c.case_id = t.case_id
        LEFT JOIN gold.c360_case k ON k.case_id = t.case_id
        WHERE c.assigned_agent_id = ? AND CAST(t.call_start_ts AS DATE) >= CAST(? AS DATE) - INTERVAL 14 DAY
          AND CAST(t.call_start_ts AS DATE) <= CAST(? AS DATE)
        ORDER BY t.call_start_ts DESC""", [session.user_id, today, today])
    with ops() as con:
        done = {r["contact_id"] for r in con.execute("SELECT contact_id FROM call_summaries WHERE status = 'approved'").fetchall()}
    rows = [r for r in rows if r["contact_id"] not in done]
    items = []
    for r in rows[:SHOW]:
        day = _to_date(r["call_day"])
        age = _days_between(day, today)
        items.append(InboxItem(
            id=f"summary:{r['contact_id']}", type="call_summaries",
            title=f"Call notes for {r['case_id']} ({day:%d %b})" if day else f"Call notes for {r['case_id']}",
            reason="The draft notes are saved only after you check, edit if needed and approve them.",
            age_days=age, age_label=_age_label(age), link=f"/calls/{r['contact_id']}",
            subject_kind="case", subject_id=r["case_id"]))
    return InboxGroup(type="call_summaries", label="Call summaries to approve",
                      why=f"Drafts from your calls in the last {SUMMARY_WINDOW_DAYS} days. Only approved notes are saved.",
                      count=len(rows), items=items, link=items[0].link if items else "/queue",
                      link_label="Review the first draft" if items else "Open the queue")


# ------------------------------------------------------------------ agent: promises due soon with a high break risk
def promises_at_risk(session: Session) -> InboxGroup:
    import pandas as pd

    from common.config import get_settings as gs

    mine = _scoped_queue(session)
    path = gs().features_dir / "ptp_scores.parquet"
    if not path.exists():
        raise Unavailable("Promise scores have not been built yet.")
    p = pd.read_parquet(path, columns=["ptp_id", "case_id", "golden_id", "ptp_due_date", "amount_cad", "p_break", "band"])
    today = _as_of()
    due = pd.to_datetime(p.ptp_due_date).dt.date
    p = p[p.case_id.isin(set(mine.case_id)) & p.band.isin(HIGH_RISK) & (due >= today)
          & (due <= date.fromordinal(today.toordinal() + PROMISE_WINDOW_DAYS))]
    p = p.assign(_due=pd.to_datetime(p.ptp_due_date).dt.date).sort_values(["_due", "p_break"], ascending=[True, False])
    items = []
    for r in p.head(SHOW).to_dict("records"):
        d = r["_due"]
        items.append(InboxItem(
            id=f"ptp:{r['ptp_id']}", type="promises_at_risk", title=f"Promise of {_money(r['amount_cad'])} on {r['case_id']}, due {d:%d %b}",
            reason=f"{round(float(r['p_break']) * 100)}% chance it breaks ({str(r['band']).replace('_', ' ')} risk, a model estimate): a check-in before the due date can help.",
            age_days=None, age_label=_due_label(d, today), due=str(d), link=f"/customers/{r['golden_id']}",
            subject_kind="case", subject_id=r["case_id"]))
    return InboxGroup(type="promises_at_risk", label="Promises due soon with a high break risk",
                      why=f"Promises on your cases due in the next {PROMISE_WINDOW_DAYS} days that the model rates high or very high risk.",
                      count=int(len(p)), items=items, link="/queue?view=high_risk", link_label="Open high-risk cases")


# ------------------------------------------------------------------ hardship specialist
def hardship_flags(session: Session) -> InboxGroup:
    from api.services import hardship as hs

    _need_live("the hardship board")
    b = hs.board()
    today = _as_of()
    items = []
    for r in b["items"][:SHOW]:
        due = _to_date(r.get("review_due"))
        age = _days_between(_to_date(r.get("raised")), today)
        items.append(InboxItem(
            id=f"flag:{r['golden_id']}", type="hardship_flags", title=f"{r['name']}: possible hardship ({r['case_id']})",
            reason=f"Raised by {FLAG_SOURCE.get(r.get('source') or '', 'the record')}. Confirm or clear it; pressure steps stay paused until a person decides.",
            age_days=age, age_label=_due_label(due, today) if due else _age_label(age), due=r.get("review_due"),
            overdue=bool(r.get("overdue")), link="/hardship/board", subject_kind="customer", subject_id=r["golden_id"]))
    count = int(b["total"])
    # flags raised to 'possible' in the app since the nightly build are not in the warehouse yet
    with ops() as con:
        ev = con.execute("""SELECT golden_id, source, ts FROM hardship_flag_events e WHERE to_level = 'possible'
                            AND event_id = (SELECT max(event_id) FROM hardship_flag_events x WHERE x.golden_id = e.golden_id)""").fetchall()
    if ev:
        gids = [e["golden_id"] for e in ev]
        on_board = {r["golden_id"] for r in _q("SELECT golden_id FROM gold.c360_customer WHERE hardship_flag = 'possible' AND list_contains(?, golden_id)", [gids])}
        for e in ev:
            if e["golden_id"] in on_board:
                continue
            raised = _to_date(e["ts"])
            due = np.busday_offset(raised, hs.REVIEW_DAYS, roll="forward").astype(date) if raised else None
            count += 1
            items.insert(0, InboxItem(
                id=f"flag:{e['golden_id']}", type="hardship_flags", title=f"Customer {e['golden_id']}: possible hardship (raised in the app)",
                reason=f"Raised by {FLAG_SOURCE.get(e['source'], 'the app')} since last night's build. Confirm or clear it.",
                age_days=_ops_age(e["ts"]), age_label=_age_label(_ops_age(e["ts"])), due=str(due) if due else None,
                link=f"/customers/{e['golden_id']}", subject_kind="customer", subject_id=e["golden_id"]))
    return InboxGroup(type="hardship_flags", label="Possible hardship to confirm or clear",
                      why=f"Each flag needs a person within {hs.REVIEW_DAYS} business days. Overdue ones come first.",
                      count=count, items=items[:SHOW], link="/hardship/board", link_label="Open the review board")


def vulnerability_reviews(session: Session) -> InboxGroup:
    from api.services import hardship as hs

    _need_live("vulnerability reviews")
    today = _as_of()
    v = hs.vulnerability_reviews(today, limit=SHOW)
    items = []
    for r in v["items"]:
        due = _to_date(r["vulnerability_review_date"])
        items.append(InboxItem(
            id=f"vuln:{r['golden_id']}", type="vulnerability_reviews", title=f"Vulnerability review for {r['golden_id']}",
            reason="The review date for this vulnerable-customer flag has passed: check the support in place is still right.",
            age_days=_days_between(due, today), age_label=_due_label(due, today), due=str(due), overdue=due < today,
            link="/hardship/board", subject_kind="customer", subject_id=r["golden_id"]))
    return InboxGroup(type="vulnerability_reviews", label="Vulnerability reviews due",
                      why="Customers flagged vulnerable whose review date is today or past, oldest first.",
                      count=int(v["total"]), items=items, link="/hardship/board", link_label="Open the review board")


def missed_offers(session: Session) -> InboxGroup:
    from api.services import hardship as hs

    _need_live("missed offers")
    cap = 50
    m = hs.missed_offers(limit=cap)
    today = _as_of()
    items = []
    for r in m["items"][:SHOW]:
        since = _to_date(r.get("flag_since"))
        progs = ", ".join(p["program_name"] for p in r.get("eligible_programs", [])[:2]) or "an agent-level program"
        items.append(InboxItem(
            id=f"missed:{r['case_id']}", type="missed_offers", title=f"{r['name']}: no hardship program offered ({r['case_id']})",
            reason=f"Flagged {r['level']} hardship and fits {progs}, but nothing has been offered yet.",
            age_days=_days_between(since, today), age_label=_age_label(_days_between(since, today)),
            link="/hardship/missed", subject_kind="case", subject_id=r["case_id"]))
    n = len(m["items"])
    return InboxGroup(type="missed_offers", label="Missed hardship offers",
                      why="Hardship-flagged customers who qualify for help that nobody has offered. Newest first."
                          + (f" Showing the first {cap}." if n >= cap else ""),
                      count=n, items=items, link="/hardship/missed", link_label="Open missed offers")


# ------------------------------------------------------------------ team lead
def batches(session: Session) -> InboxGroup:
    from api.services import nba as nba_svc

    data = nba_svc.batches("pending", session.team_id)  # the same list (and team filter) the Team screen shows
    with ops() as con:
        created = {r["batch_id"]: r["created_ts"] for r in con.execute("SELECT batch_id, created_ts FROM batches WHERE status = 'pending'").fetchall()}
    items = []
    for b in data["items"][:SHOW]:
        age = _ops_age(created.get(b["batch_id"]))
        what = f"{TREATMENT.get(b['treatment'], b['treatment'])}s by {CHANNEL.get(b['channel'], b['channel'])}" if b["kind"] == "digital_reminders" else b["kind"].replace("_", " ")
        items.append(InboxItem(
            id=f"batch:{b['batch_id']}", type="batches", title=f"{b['count']:,} {what.lower()} ({b['batch_id']})",
            reason=f"They go out together once you check the 2% sample ({b['sample_size']} case{'s' if b['sample_size'] != 1 else ''}) and approve.",
            age_days=age, age_label=_age_label(age), link="/team"))
    return InboxGroup(type="batches", label="Batches to approve",
                      why="Routine reminders for your team, sent as one batch after you look over a 2% sample.",
                      count=len(data["items"]), items=items, link="/team", link_label="Open batch approvals")


def playbook_proposals(session: Session) -> InboxGroup:
    from decisioning import playbooks

    ps = [p for p in playbooks.listing(playbooks.PENDING) if p["playbook"] != STRATEGY_TEST]  # tests: own group
    source = {"employer_radar": "the employer radar", "outage_shield": "the outage shield", "regional": "the weather map"}
    items = []
    for p in ps[:SHOW]:
        age = _ops_age(p.get("created_ts"))
        extra = " The contact step also needs Policy Office sign-off." if p.get("requires_policy_office_signoff") else ""
        items.append(InboxItem(
            id=f"playbook:{p['proposal_id']}", type="playbook_proposals", title=p["title"],
            reason=f"Suggested by {source.get(p['playbook'], 'a playbook')}. Approving creates a batch for the sample check; nobody is contacted.{extra}",
            age_days=age, age_label=_age_label(age), link="/team?tab=playbooks",
            subject_kind="employer" if p["playbook"] == "employer_radar" else None,
            subject_id=p["subject_id"] if p["playbook"] == "employer_radar" else None))
    return InboxGroup(type="playbook_proposals", label="Playbook proposals",
                      why="Radar, outage refund and regional playbooks wait for a team lead.",
                      count=len(ps), items=items, link="/team?tab=playbooks", link_label="Open playbooks")


def override_reviews(session: Session) -> InboxGroup:
    from governance import monitoring as mon

    _need_live("your team's agents")
    agents = _q("SELECT agent_id, agent_display_name FROM silver.agents WHERE team_id = ?", [session.team_id])
    names = {a["agent_id"]: a["agent_display_name"] for a in agents}
    if not names:
        return InboxGroup(type="override_reviews", label="Overrides above the review threshold", why="", count=0, items=[],
                          link="/governance/monitoring", link_label="Open monitoring")
    ids = list(names)
    with ops() as con:
        rows = con.execute(f"SELECT user_id, decision, proposed_json, final_json, ts FROM nba_decisions WHERE user_id IN ({','.join('?' * len(ids))})", ids).fetchall()
    by: dict[str, list[dict]] = {}
    last: dict[str, str] = {}
    for r in rows:
        prop = (json.loads(r["proposed_json"]) or {}).get("action")
        final = json.loads(r["final_json"]) if r["final_json"] else None
        by.setdefault(r["user_id"], []).append({"approved_via": "agent", "proposed": mon._action_key(prop),
                                                "final": None if r["decision"] == "approve" else mon._action_key(final)})
        last[r["user_id"]] = max(last.get(r["user_id"], ""), r["ts"] or "")
    flagged = []
    for uid, recs in by.items():
        rate, n, over = mon.override_rate(recs)
        if rate is not None and n >= MIN_DECISIONS_FOR_OVERRIDE_REVIEW and rate > mon.OVERRIDE_REVIEW_THRESHOLD:
            flagged.append((rate, uid, n, over))
    flagged.sort(reverse=True)
    items = [InboxItem(
        id=f"override:{uid}", type="override_reviews", title=f"{names.get(uid) or uid}: {over} of {n} decisions overridden ({round(rate * 100)}%)",
        reason=f"Above the {round(mon.OVERRIDE_REVIEW_THRESHOLD * 100)}% review threshold: go over the reasons with the agent.",
        age_days=_ops_age(last.get(uid)), age_label=_ago(_ops_age(last.get(uid)), "last decision"),
        link="/governance/monitoring", subject_kind="agent", subject_id=uid) for rate, uid, n, over in flagged[:SHOW]]
    return InboxGroup(type="override_reviews", label="Overrides above the review threshold",
                      why=f"Agents on your team who changed more than {round(mon.OVERRIDE_REVIEW_THRESHOLD * 100)}% of the suggested actions (at least {MIN_DECISIONS_FOR_OVERRIDE_REVIEW} decisions).",
                      count=len(flagged), items=items, link="/governance/monitoring", link_label="Open monitoring")


# ------------------------------------------------------------------ strategy proposals (a store another screen may add)
_COLS = {
    "id": ("proposal_id", "id"),
    "title": ("title", "name", "summary", "hypothesis"),
    "status": ("status",),
    "author": ("author_id", "created_by", "proposed_by", "user_id", "analyst_id"),
    "to_role": ("addressed_to", "to_role", "approver_role", "requires_role", "assignee_role", "reviewer_role"),
    "team": ("team_id", "addressed_team", "to_team"),
    "created": ("created_ts", "created_at", "ts", "submitted_at"),
    "link": ("link", "url"),
}


def _proposal_rows() -> list[dict] | None:
    """Rows of the `proposals` table, with known column names mapped; None when the table does not exist."""
    with ops() as con:
        if not _table_exists(con, "proposals"):
            return None
        cols = [r["name"] for r in con.execute("PRAGMA table_info(proposals)").fetchall()]
        pick = {k: next((c for c in names if c in cols), None) for k, names in _COLS.items()}
        rows = [dict(r) for r in con.execute("SELECT * FROM proposals").fetchall()]
    out = []
    for r in rows:
        m = {k: (r.get(c) if c else None) for k, c in pick.items()}
        m["id"] = str(m["id"] or r.get("rowid") or len(out) + 1)
        out.append(m)
    return out


STRATEGY_TEST = "strategy_test"  # analysts' test proposals live in the playbook store (api/services/track.py)


def _strategy_tests() -> list[dict]:
    """Analysts' strategy-test proposals in the playbook store, in the same shape as `_proposal_rows`."""
    from decisioning import playbooks

    out = []
    for p in playbooks.listing():
        if p["playbook"] != STRATEGY_TEST:
            continue
        status = "pending" if p["status"] == playbooks.PENDING else p["status"]
        out.append({"id": p["proposal_id"], "title": p["title"], "status": status, "to_role": p.get("requires_role"),
                    "author": (p.get("payload") or {}).get("proposed_by"), "team": None, "created": p.get("created_ts"),
                    "link": f"/track/cohort/{p['subject_id']}", "approve_link": "/team?tab=playbooks"})
    return out


def strategy_proposals(session: Session) -> InboxGroup:
    rows = _strategy_tests() + (_proposal_rows() or [])
    mine = [r for r in rows if str(r.get("status") or "").lower() in PENDING_PROPOSAL
            and (r.get("to_role") in (None, "", "team_lead"))
            and (not r.get("team") or r.get("team") == session.team_id)]
    mine.sort(key=lambda r: str(r.get("created") or ""))
    items = [InboxItem(
        id=f"proposal:{r['id']}", type="strategy_proposals", title=str(r.get("title") or f"Proposal {r['id']}"),
        reason=f"Proposed by {r.get('author') or 'an analyst'}: a strategy test waits for a team lead to accept or decline it.",
        age_days=_ops_age(r.get("created")), age_label=_age_label(_ops_age(r.get("created"))),
        link=str(r.get("approve_link") or r.get("link") or "/team")) for r in mine[:SHOW]]
    return InboxGroup(type="strategy_proposals", label="Strategy tests proposed by analysts",
                      why="Analysts' proposed strategy tests addressed to team leads. You approve them with the playbooks.",
                      count=len(mine), items=items, link="/team?tab=playbooks", link_label="Open playbooks")


def own_proposals(session: Session) -> InboxGroup:
    rows = _strategy_tests() + (_proposal_rows() or [])
    mine = [r for r in rows if r.get("author") == session.user_id]
    mine.sort(key=lambda r: str(r.get("created") or ""), reverse=True)
    items = [InboxItem(
        id=f"proposal:{r['id']}", type="own_proposals", title=str(r.get("title") or f"Proposal {r['id']}"),
        reason=f"Status: {str(r.get('status') or 'unknown').replace('_', ' ')}.",
        age_days=_ops_age(r.get("created")), age_label=_ago(_ops_age(r.get("created")), "sent"),
        link=str(r.get("link") or "/ask")) for r in mine[:SHOW]]
    return InboxGroup(type="own_proposals", label="Your proposals", informational=True,
                      why="Nothing waits for your approval: analysts see aggregates only. These are the proposals you sent and where they stand.",
                      count=len(mine), items=items, link="/ask", link_label="Open Ask")


# ------------------------------------------------------------------ steward
def identity_pairs(session: Session) -> InboxGroup:
    _need_live("the identity review queue")
    with ops() as con:
        reviewed = [r["pair_id"] for r in con.execute("SELECT pair_id FROM identity_reviews WHERE verdict IN ('link', 'no_link')").fetchall()]
    total = _q("SELECT count(*) AS n FROM identity.review_queue WHERE NOT list_contains(?, pair_id)", [reviewed])[0]["n"]
    rows = _q("""SELECT pair_id, source_system, candidate_golden_id, score FROM identity.review_queue
                 WHERE NOT list_contains(?, pair_id) ORDER BY score DESC, pair_id LIMIT ?""", [reviewed, SHOW])
    built = get_settings().warehouse_path.stat().st_mtime
    age = max(int((time.time() - built) // 86400), 0)
    items = [InboxItem(
        id=f"pair:{r['pair_id']}", type="identity_pairs", title=f"Pair {r['pair_id']}: {r['source_system'].replace('_', ' ')} record and {r['candidate_golden_id']}",
        reason=f"Match score {float(r['score']):.2f} is in the grey band. Decide link or no link: a wrong merge means contacting the wrong person.",
        age_days=age, age_label=_ago(age, "from the identity run"),
        link="/steward/identity", subject_kind="identity", subject_id=r["candidate_golden_id"]) for r in rows]
    return InboxGroup(type="identity_pairs", label="Identity pairs to link or keep apart",
                      why="Grey-band matches the matcher would not decide on its own. Highest score first.",
                      count=int(total), items=items, link="/steward/identity", link_label="Open identity review")


def drift_fixes(session: Session) -> InboxGroup:
    from governance import drift

    fx = drift.fixes(drift.PENDING)
    items = [InboxItem(
        id=f"drift:{f['fix_id']}", type="drift_fixes", title=f["description"],
        reason="A schema change was detected and a fix drafted. Nothing changes in the pipeline until you approve it.",
        age_days=_ops_age(f.get("created_ts")), age_label=_age_label(_ops_age(f.get("created_ts"))),
        link="/steward/drift", subject_kind="data_product", subject_id=f"silver.{f['table']}") for f in fx[:SHOW]]
    return InboxGroup(type="drift_fixes", label="Schema-drift fixes to approve",
                      why="Drafted fixes for changes in the source feeds. Only a steward approves them.",
                      count=len(fx), items=items, link="/steward/drift", link_label="Open schema changes")


def contract_tests(session: Session) -> InboxGroup:
    p = get_settings().reports_dir / "contract_tests.json"
    if not p.exists():
        raise Unavailable("No contract test results yet: they are saved by the nightly build (`make gold`).")
    res = json.loads(p.read_text())
    gen = (res.get("metadata") or {}).get("generated_at")
    bad = [r for r in res.get("results", []) if str(r.get("unique_id", "")).startswith("test.")
           and r.get("status") in ("fail", "error")]
    items = []
    for r in bad[:SHOW]:
        name = r["unique_id"].split(".")[2] if r["unique_id"].count(".") >= 2 else r["unique_id"]
        n = r.get("failures")
        items.append(InboxItem(
            id=f"test:{r['unique_id']}", type="contract_tests", title=f"Contract test failing: {name}",
            reason=(f"{n:,} rows break this rule. " if isinstance(n, int) and n else "")
                   + "The nightly publish keeps the old warehouse until every contract test passes.",
            age_days=_ops_age(gen), age_label=_ago(_ops_age(gen), "found"), link="/governance/quality",
            subject_kind="data_product", subject_id="gold.c360_customer"))
    return InboxGroup(type="contract_tests", label="Failing contract tests",
                      why="Data contract checks from the last build that did not pass.",
                      count=len(bad), items=items, link="/governance/quality", link_label="Open data quality")


# ------------------------------------------------------------------ assembly
Source = Callable[[Session], InboxGroup]
SOURCES: dict[Role, list[tuple[str, Source]]] = {
    Role.agent: [("Next best actions", nba_actions), ("Post-call summaries", call_summaries),
                 ("Promises at risk", promises_at_risk)],
    Role.hardship_specialist: [("Possible hardship flags", hardship_flags), ("Vulnerability reviews", vulnerability_reviews),
                               ("Cases routed to a specialist", nba_actions), ("Missed offers", missed_offers)],
    Role.team_lead: [("Batches", batches), ("Playbook proposals", playbook_proposals),
                     ("Overrides above 25%", override_reviews), ("Strategy proposals", strategy_proposals)],
    Role.analyst: [("Your proposals", own_proposals)],
    Role.steward: [("Identity grey-band pairs", identity_pairs), ("Drift fixes", drift_fixes),
                   ("Contract tests", contract_tests)],
}
# sources asked for that have no store in the code (reported, never faked)
MISSING: dict[Role, list[NotAvailable]] = {
    Role.hardship_specialist: [NotAvailable(
        source="Plan offers above an agent's level",
        reason="There is no sign-off store: the simulator shows the approver level for a scenario, but nothing saves a "
               "plan as waiting for someone else's sign-off.")],
}

_cache: dict[tuple, tuple[float, InboxResponse]] = {}


def clear_cache() -> None:
    _cache.clear()


def build(session: Session) -> InboxResponse:
    role = Role(session.role)
    groups: list[InboxGroup] = []
    missing = list(MISSING.get(role, []))
    for name, fn in SOURCES.get(role, []):
        try:
            groups.append(fn(session))
        except Unavailable as e:
            missing.append(NotAvailable(source=name, reason=str(e)))
        except Exception:  # noqa: BLE001 - one broken source must not hide the rest of the inbox
            log.exception("inbox source %s failed", name)
            missing.append(NotAvailable(source=name, reason="This list could not be read right now."))
    groups.sort(key=lambda g: g.count == 0)  # stable: the persona's order, empty groups last
    actionable = [g for g in groups if not g.informational]
    order = {g.type: i for i, g in enumerate(actionable)}
    pool = [i for g in actionable for i in g.items]
    top = sorted(pool, key=lambda i: (not i.overdue, order[i.type], -(i.age_days or 0)))[:3]
    out = InboxResponse(
        role=role.value, total=sum(min(g.count, SHOW) for g in actionable), backlog=sum(g.count for g in actionable), groups=groups, top=top, not_available=missing,
        as_of=str(_as_of()),
        note="Analysts approve nothing here; this shows where your own proposals stand." if role == Role.analyst else None)
    _cache[(session.user_id, role.value, session.team_id)] = (time.monotonic(), out)
    return out


def counts(session: Session) -> InboxCounts:
    key = (session.user_id, Role(session.role).value, session.team_id)
    hit = _cache.get(key)
    out = hit[1] if hit and time.monotonic() - hit[0] < CACHE_SECONDS else build(session)
    return InboxCounts(role=out.role, total=out.total, backlog=out.backlog,
                       by_type={g.type: g.count for g in out.groups if not g.informational})
