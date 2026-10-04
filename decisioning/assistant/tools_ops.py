# ruff: noqa: E501
"""Read-only assistant tools for the team-lead, analyst, steward and hardship screens that were not reachable before:
employer radar (S1), playbook proposals, outage victims (H5), data drift (S3) and the call friction summary (A3).

Rules for every tool here: the role allow-list matches the screen and the API route that shows the same thing; groups
under 10 customers are never shown; no individual customer row goes to an analyst; nothing is written (no proposal is
stored, no fix is recorded: the tool only reads what the screens read). An action is a proposal with a link to the
real screen, where a person approves it. The stress test (S6) lives in tools.py."""

from __future__ import annotations

from decisioning.assistant import data
from decisioning.assistant.tools import (
    ToolContext,
    ToolResult,
    ToolSkip,
    kv,
    link,
    proposal,
    table,
    tool,
)

MIN_GROUP = 10  # a group under this many customers is never shown


# ---------------------------------------------------------------- S1 employer radar

@tool("employer_radar", "Weekly employer radar: employers with at least 10 customers whose late-payroll share and new Employment "
      "Insurance deposits stand out against industry peers. A radar, not a layoff detector; smaller employers are hidden.",
      ("team_lead", "analyst"))
def employer_radar(ctx: ToolContext) -> ToolResult:
    from decisioning import radar

    r = data.ttl_cached(("radar",), 300, lambda: radar.employer_week(limit=10**9))
    if not r.get("rows") and not r.get("week_start"):
        raise ToolSkip(r.get("summary") or "No deposit snapshot is loaded, so the radar has nothing to show.")
    rows_all = [x for x in r["rows"] if x["n_customers"] >= MIN_GROUP]
    flagged = [x for x in rows_all if x["pattern"] != "none"]
    shown = flagged or sorted(rows_all, key=lambda x: -(x["gap_rate"] or 0))[:5]
    rows = [[x["employer_key"], x["industry_naics2"], x["n_customers"], x["n_payroll_gap"], x["n_new_ei"], x["gap_rate"],
             x["peer_gap_rate"], x["pattern"].replace("_", " "), x["open_cases"]] for x in shown[:8]]
    ev = {**table(["Employer", "Industry (NAICS2)", "Customers", "Late payroll", "New EI", "Late share", "Industry peers", "Pattern", "Open cases"], rows),
          "kv": kv([("Week of", r["week_start"]), ("Employers shown (10 or more customers)", r["employers_shown"]),
                    ("Employers hidden (under 10 customers)", r["employers_hidden_small"]), ("Clusters", len(flagged)),
                    ("Known incidents", "; ".join(f'{i["event_id"]} {i["description"]}' for i in r.get("known_incidents", [])[:2]) or None),
                    ("Own-history comparison", r.get("own_history"))]),
          "text": r["label"] + ("\nRows shown are the five highest late-payroll shares, not clusters." if not flagged and rows else ""),
          "links": [link("Open the radar", "/map")]}
    res = ToolResult(r["summary"], ev)
    res.findings.append(r["summary"] + f" {r['employers_hidden_small']:,} employers under {MIN_GROUP} customers are hidden.")
    res.findings.append(r["label"])
    if flagged:
        top = flagged[0]
        res.findings.append(f"Top cluster: {top['employer_key']} with {top['n_payroll_gap']} of {top['n_customers']} customers paid late "
                            f"({top['pattern'].replace('_', ' ')}); the radar shows patterns in deposits, it does not say anyone lost a job.")
        res.proposals.append(proposal(
            "radar-playbook", f"Review the playbook for {len(flagged)} employer cluster(s)",
            "The radar proposes outreach to customers who are not yet behind. A team lead reviews the playbook and approves it on the team page; "
            "approving makes a batch for the usual sample check and contacts nobody.",
            "review_playbook", "/team" if ctx.role == "team_lead" else "/map", "team_lead"))
    return res


# ---------------------------------------------------------------- playbook proposals

@tool("playbook_proposals", "Playbook proposals waiting for a team lead (employer radar, outage shield, regional). Counts and titles only; "
      "approving happens on the team page and creates a batch for the usual sample check.", ("team_lead",))
def playbook_proposals(ctx: ToolContext, status: str | None = None) -> ToolResult:
    from decisioning import playbooks

    items = playbooks.listing(status)
    pending = [i for i in items if i["status"] == playbooks.PENDING]
    by: dict[str, int] = {}
    for i in pending:
        by[i["playbook"]] = by.get(i["playbook"], 0) + 1
    rows = [[i["proposal_id"], i["playbook"].replace("_", " "), i["kind"].replace("_", " "), i["title"], i["status"].replace("_", " "),
             "yes" if i.get("requires_policy_office_signoff") else "no"] for i in items[:8]]
    ev = {**table(["Proposal", "Playbook", "Kind", "Title", "Status", "Policy Office sign-off"], rows),
          "kv": kv([("Proposals", len(items)), ("Waiting for a team lead", len(pending))] + [(f"Pending: {k.replace('_', ' ')}", v) for k, v in sorted(by.items())]),
          "text": "Nothing is sent: approving creates a batch that gets the usual 2% sample check.", "links": [link("Open the playbooks", "/team")]}
    if not items:
        res = ToolResult("No playbook proposals right now: the radar and the outage shield found nothing that needs a team lead.", ev)
        res.findings.append("No playbook proposals are stored; the nightly job creates them when the radar or the outage shield finds something.")
        return res
    res = ToolResult(f"{len(pending)} of {len(items)} playbook proposal(s) wait for a team lead.", ev,
                     status="needs_approval" if pending else "done")
    res.findings.append(f"{len(pending)} playbook proposal(s) are pending" + (": " + ", ".join(f"{n} from {k.replace('_', ' ')}" for k, n in sorted(by.items())) if by else "") + ".")
    if pending:
        res.proposals.append(proposal(
            "playbooks-review", f"Review {len(pending)} playbook proposal(s)",
            "Open the playbooks on the team page and approve, one by one. Approval is audited, creates a batch for the sample check and contacts nobody.",
            "approve_playbook", "/team", "team_lead"))
    return res


# ---------------------------------------------------------------- H5 outage victims

@tool("outage_victims", "Outage shield: customers whose payment was due during a payment outage and landed the next day (a candidate list), "
      "with the fee reversals and pressure holds it proposes. Candidates, not a final answer.", ("hardship_specialist", "team_lead"))
def outage_victims(ctx: ToolContext) -> ToolResult:
    from decisioning import outage_shield

    reps = data.ttl_cached(("outage",), 300, outage_shield.candidates)
    if not reps:
        res = ToolResult("No payment outage is recorded, so there are no outage victims to protect.",
                         {"text": outage_shield.NOTE, "links": [link("Open the playbooks", "/team")] if ctx.role == "team_lead" else []})
        res.findings.append("No payment outage event is on record.")
        return res
    df = data.queue_df()
    mine: dict[str, set[str]] = {}
    if df is not None:  # a person sees only customers whose case they may see
        for rep in reps:
            ids = set(rep["members"])
            sub = df[df.golden_id.isin(ids)].to_dict("records")
            mine[rep["event_id"]] = {r["golden_id"] for r in sub if data.can_see(ctx.session, r)}
    rows, owed_by_event = [], {}
    for rep in reps:
        fees = [p for p in rep["proposals"] if p["kind"] == "fee_reversal"]
        holds = [p for p in rep["proposals"] if p["kind"] == "pressure_hold"]
        owed_by_event[rep["event_id"]] = len(fees)
        rows.append([rep["event_id"], rep["start_ts"][:16], rep["end_ts"][:16], rep["our_count"], rep["bank_estimate"], len(fees), len(holds),
                     len(mine.get(rep["event_id"], ())), rep["customers_contacted_during_incident"]])
    top = reps[0]
    ids = sorted(mine.get(top["event_id"], ()))[:5]
    ev = {**table(["Event", "From", "To", "Candidates (ours)", "Bank estimate", "Fee reversals proposed", "Pressure holds proposed",
                   "Candidates in your cases", "Contacted during the outage"], rows),
          "kv": kv([("Event", f'{top["event_id"]}: {top["description"]}'), ("Customers in your cases (sample)", ", ".join(ids) or "none in your cases")]),
          "text": top["note"], "links": [link("Open the playbooks", "/team")] if ctx.role == "team_lead" else [link("Open the board", "/hardship/board")]}
    res = ToolResult(f"{top['event_id']}: {top['our_count']:,} payments due during the outage were paid the next day (the bank estimates {top['bank_estimate']:,}); "
                     f"{len(top['proposals']):,} reversals and holds are proposed, none applied.", ev,
                     status="needs_approval", facts={"outage_event": top["event_id"]})
    res.findings.append(f"{top['our_count']:,} candidate payments in {top['event_id']}; this is a candidate list, not a final answer, and no fee or hold has been applied.")
    if top.get("customers_contacted_during_incident"):
        res.findings.append(f"{top['customers_contacted_during_incident']:,} customers were contacted during the outage window.")
    res.proposals.append(proposal(
        f"outage-{top['event_id']}", f"Reverse fees and hold pressure for {top['event_id']} victims",
        "Fee reversals and pressure holds are proposals. A team lead approves them as a playbook on the team page; a specialist can flag customers on the board. Nothing is applied by the assistant.",
        "approve_playbook", "/team" if ctx.role == "team_lead" else "/hardship/board", "team_lead"))
    return res


# ---------------------------------------------------------------- S3 data drift

@tool("data_drift", "Schema drift telemetry: columns added, removed or renamed after a release or feed issue, and the drafted fixes that wait for a "
      "data steward. The assistant only reads; an engineer applies a fix.", ("steward", "analyst"))
def data_drift(ctx: ToolContext) -> ToolResult:
    from governance import drift

    scans = data.ttl_cached(("drift",), 300, drift.scan_warehouse)
    fixes = drift.fixes()
    changed = [s for s in scans if s.get("changed")]
    rows = [[s["table"], s["event_id"], ", ".join(s["added_columns"][:4]) or "none", ", ".join(s["removed_columns"][:4]) or "none",
             ", ".join(f'{x["from"]} to {x["to"]}' for x in s["renames"][:3]) or "none", s["row_count_change"]] for s in changed[:6]]
    fix_rows = [[f["fix_id"], f["table"], f["status"].replace("_", " "), f["description"][:90]] for f in fixes[:6]]
    pending = [f for f in fixes if f["status"] == drift.PENDING]
    ev = {**table(["Table", "Release or issue", "Columns added", "Columns removed", "Renamed", "Row count change"], rows),
          "kv": kv([("Releases and feed issues scanned", len(scans)), ("With a schema change", len(changed)), ("Drafted fixes", len(fixes)),
                    ("Waiting for the steward", len(pending))] + [("Fix " + f["fix_id"], f["description"][:100]) for f in fixes[:3]]),
          "text": "Fixes are drafts: the app changes nothing, the steward approves and an engineer applies the mapping in the dbt project.\n"
                  + "\n".join(" | ".join(str(c) for c in r) for r in fix_rows),
          "links": [link("Open drift", "/steward/drift")] if ctx.role == "steward" else [link("Open monitoring", "/governance/monitoring")]}
    if not changed:
        res = ToolResult("No schema change found in recent releases or feed issues. Nothing needs an engineer.", ev)
        res.findings.append("No schema drift detected.")
        return res
    t = changed[0]
    res = ToolResult(f"{len(changed)} table(s) changed shape after a release; {len(pending)} drafted fix(es) wait for a steward.", ev,
                     status="needs_approval" if pending else "done")
    res.findings.append(f"{t['table']} changed after {t['event_id']}: " + ("; ".join(filter(None, [
        f"{len(t['added_columns'])} column(s) added" if t["added_columns"] else "", f"{len(t['removed_columns'])} removed" if t["removed_columns"] else "",
        f"{len(t['renames'])} rename(s)" if t["renames"] else ""])) or "values shifted") + f"; row count changed by {t['row_count_change'] * 100:.0f}% (partial week, so compare with care).")
    if pending:
        res.proposals.append(proposal(
            "drift-review", f"Review {len(pending)} drafted schema fix(es)",
            "Only the data steward approves a fix, on the drift page, and an engineer applies it in the dbt project. The app applies nothing.",
            "approve_drift_fix", "/steward/drift", "steward"))
    return res


# ---------------------------------------------------------------- A3 call friction

FRICTION_SQL = """SELECT h.bucket_at_contact AS stage, count(*) AS calls, avg(t.silence_ratio) AS avg_silence,
       avg(t.overtalk_count) AS avg_overtalk, avg(t.hold_count) AS avg_holds,
       avg(CASE WHEN t.overtalk_count >= 4 OR t.hold_count >= 1 OR t.silence_ratio >= 0.5 THEN 1.0 ELSE 0.0 END) AS high_friction_share,
       avg(v.dead_air_sec) AS avg_dead_air_sec, count(v.voice_sample_id) AS recordings
FROM silver.call_transcripts t
JOIN silver.contact_history h ON h.contact_id = t.contact_id
LEFT JOIN silver.voice_samples v ON v.voice_sample_id = t.voice_sample_id
GROUP BY 1 HAVING count(*) >= 10"""


@tool("call_friction", "Negotiation friction (A3) at portfolio level: how often calls show overtalk, holds or long silence, by delinquency stage "
      "(stages under 10 calls hidden). Call-level measures only: never speaker traits, never one customer, never used to treat anyone differently.",
      ("analyst", "team_lead"))
def call_friction(ctx: ToolContext) -> ToolResult:
    from common.db import warehouse
    from features import voice

    voice.assert_call_level(["silence_ratio", "overtalk_count", "hold_count", "dead_air_sec"])

    def q() -> list[tuple]:
        con = warehouse(read_only=True)
        try:
            return con.execute(FRICTION_SQL).fetchall()
        finally:
            con.close()

    raw = data.ttl_cached(("friction",), 300, q)
    if not raw:
        raise ToolSkip("No recorded calls with a stage are available, so the friction summary was skipped.")
    order = {"current": 0, "1-30": 1, "31-60": 2, "61-90": 3, "91-120": 4, "121-150": 5, "151-180": 6, "180+": 7}
    grp = sorted(raw, key=lambda r: order.get(str(r[0]), 9))
    total = sum(r[1] for r in grp)
    share = sum(r[1] * r[5] for r in grp) / total
    worst = max(grp, key=lambda r: r[5])
    rows = [[r[0], r[1], round(r[2], 3), round(r[3], 2), round(r[4], 2), round(r[5], 3), None if r[6] is None else round(r[6], 1), r[7]] for r in grp]
    ev = {**table(["Stage", "Calls", "Avg silence share", "Avg overtalk events", "Avg holds", "High-friction share", "Avg dead air (s)", "Recordings"], rows),
          "kv": kv([("Calls", total), ("High-friction share of all calls", round(share, 3)),
                    ("High-friction call", "overtalk 4 or more, a hold, or silence over half the call"),
                    ("Coverage", "transcribed calls only (about 25,000 of the contacts); dead air from the 2,000 recordings"),
                    ("Status", "descriptive and designed (A3); it must pass the proxy-feature test before any use in a decision")]),
          "text": "SQL used:\n" + FRICTION_SQL, "links": [link("Open Ask", "/ask")]}
    res = ToolResult(f"{share * 100:.0f}% of {total:,} transcribed calls show friction (overtalk, a hold or long silence); highest in stage {worst[0]} at {worst[5] * 100:.0f}%.", ev)
    res.findings.append(f"{share * 100:.0f}% of {total:,} transcribed calls are high-friction; stage {worst[0]} is highest at {worst[5] * 100:.0f}% over {worst[1]:,} calls.")
    res.findings.append("Friction describes the line and the conversation, not the person: silence and talk ratios can track disability or accent, so this stays out of every decision until it passes the proxy test.")
    res.proposals.append(proposal(
        "friction-coaching", "Review friction by stage with the team",
        "Use the aggregate to decide where call scripts or hold handling need a look. It never ranks customers or agents and changes no action.",
        "review_metric", "/ask", ctx.role))
    return res

