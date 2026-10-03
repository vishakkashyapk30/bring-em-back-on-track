# ruff: noqa: E501
"""The closed list of plans per persona. A plan is a fixed sequence of tool calls; the goal text only picks which plan
runs (and fills a few slots such as a case ID, a date, a channel or a question). Rules do the picking offline; a
language model may pick instead, but only from this list."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

CASE_RE = re.compile(r"\bCS-\d{4}-\d+\b")
GOLDEN_RE = re.compile(r"\bG-[A-Z0-9]{4,}\b")
DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")
AMOUNT_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)")
PCT_RE = re.compile(r"\b(\d{1,3})\s?%")
QUESTION_RE = re.compile(r"\?\s*$|^\s*(what|how|which|who|when|where|why|can|may|should|must|is|are|does|do)\b", re.I)


@dataclass(frozen=True)
class Step:
    tool: str
    title: str
    why: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    id: str
    title: str
    description: str
    steps: tuple[Step, ...]
    patterns: tuple[str, ...] = ()
    label: str = ""          # button text in the UI (empty: not offered as a suggestion)
    goal: str = ""           # the goal text the button sends


S = Step

PLANS: dict[str, tuple[Plan, ...]] = {
    "agent": (
        Plan("briefing", "Your briefing for today", "Queue, the top case, the proposed action, the promise check and the call notes.",
             (S("queue_summary", "Read today's queue", "Start from the work assigned to you, highest priority first."),
              S("customer_360", "Open the customer", "Check the account picture, flags, consent and identity match before acting."),
              S("nba_proposal", "Check the next best action", "The contact rules run first; the model only ranks what they allow."),
              S("promise_check", "Check the promise against payday", "A promise due before payday is more likely to break."),
              S("call_summary", "Draft the call notes", "Notes are drafted from the recorded call and wait for your approval.")),
             (r"\b(brief\w*|today|my day|morning|overview|what needs)\b",), "Brief me on today",
             "Brief me on today and what needs my approval"),
        Plan("case_review", "Review a case", "Customer, proposed action with the contact rules, and hardship program eligibility.",
             (S("customer_360", "Open the customer", "See flags, consent, holdings and the identity match."),
              S("nba_proposal", "Check the next best action", "See the proposed action and the rules that shaped it."),
              S("eligibility_check", "Check program eligibility", "Rules decide which hardship programs fit.")),
             (r"\b(review|prepare|prep|next case|case review|ready for|this case|the case)\b",), "Review my next case",
             "Review my next case: the customer, the proposed action and eligibility"),
        Plan("promise", "Promise check", "Break risk of the open promise and whether it falls before payday.",
             (S("customer_360", "Open the customer", "Confirm who this is and any hardship flag."),
              S("promise_check", "Check the promise against payday", "Compares the due date with the payday the customer stated; the what-if saves nothing.")),
             (r"\b(promise|promises|ptp|payday|pay day|paycheque|what.?if)\b",), "Check the promise against payday",
             "Check the promise against payday and tell me if a later date is safer"),
        Plan("post_call", "Call notes", "Draft the notes for the last recorded call and check its promise.",
             (S("call_summary", "Draft the call notes", "Built from the redacted transcript; checked against the recorded promise."),
              S("promise_check", "Check the promise", "The promise taken on the call is scored for break risk.")),
             (r"\b(notes?|call summary|summar\w+|transcript|last call|post.?call|wrap.?up)\b",), "Draft the notes for the last call",
             "Draft the notes for my last recorded call"),
        Plan("hardship_screen", "Hardship screen", "Is the customer flagged, which programs fit and what policy says.",
             (S("customer_360", "Open the customer", "Read the hardship flag, source and consent."),
              S("eligibility_check", "Check program eligibility", "Which programs the rules allow, and who must approve."),
              S("policy_answer", "Check the policy",
                "Cited policy on what to do before asking for payment.",
                {"question": "A customer says their hours were cut at work. What must the agent do before asking for payment?"})),
             (r"\b(hardship|struggl\w+|lost (their |his |her )?(job|income)|programs?|eligib\w+|what may i offer|financial difficulty)\b",),
             "Is this customer in hardship?", "Is this customer in hardship, and what may I offer?"),
        Plan("policy", "Policy answer", "A cited answer from the current policy documents.",
             (S("policy_answer", "Look up the policy", "Answers come only from current documents, with citations; unknown topics are refused."),),
             (r"\b(policy|rule|rules|allowed|permitted|must|should|grace|consent|do not call|call attempts|how many calls)\b",),
             "Look up a policy rule", "How many call attempts can we make on a mid-stage account in a week?"),
        Plan("triage", "Queue triage", "High-risk and hardship cases in your queue.",
             (S("queue_summary", "Read the high-risk cases", "The cases most likely to break a promise.", {"view": "high_risk"}),
              S("queue_summary", "Read the hardship cases", "Cases where pressure is removed and a specialist may be needed.", {"view": "hardship"})),
             (r"\b(triage|high.?risk|risky|urgent|priorit\w+|worst)\b",), "Which of my cases are high risk?",
             "Triage my queue: which cases are high risk and urgent?"),
    ),
    "hardship_specialist": (
        Plan("briefing", "Your hardship briefing", "Review board, missed offers, eligibility and a plan simulation.",
             (S("hardship_board", "Read the review board", "Customers flagged possible wait for a person; overdue ones first."),
              S("missed_offers", "Find missed offers", "Flagged customers never offered a program although one fits."),
              S("eligibility_check", "Check eligibility on the newest missed case", "Rules decide which programs fit."),
              S("simulator", "Simulate the plan", "Shows the new payment, months to clear and who must approve. Saves nothing."),
              S("override_report", "Check rule overrides", "Offers made although the rules said no.")),
             (r"\b(brief\w*|today|my day|morning|overview)\b",), "Brief me on hardship today",
             "Brief me on hardship today and what needs my decision"),
        Plan("board", "Review board", "Customers waiting for a confirm-or-clear decision.",
             (S("hardship_board", "Read the review board", "Overdue reviews first."),
              S("customer_360", "Open the first customer", "Check the flag, source and identity match."),
              S("nba_proposal", "Check the proposed action", "Pressure is already removed by the contact rules.")),
             (r"\b(board|overdue|waiting|confirm|clear the flag|lower the flag|review date|flagged possible)\b",), "Who is overdue for review?",
             "Which hardship customers are overdue for review?"),
        Plan("missed", "Missed offers", "Flagged customers who were never offered a program.",
             (S("missed_offers", "Find missed offers", "Newest first, only where an agent-level program fits."),
              S("eligibility_check", "Check eligibility on the newest case", "Every program checked rule by rule.")),
             (r"\b(missed|never offered|not offered|no program|never (been )?offered)\b",), "Who was never offered a program?",
             "Who was never offered a hardship program?"),
        Plan("simulate", "Plan simulation", "Eligibility, then the simulated plan and its approver.",
             (S("eligibility_check", "Check eligibility", "Pick a program the rules allow."),
              S("simulator", "Simulate the plan", "New payment, months to clear, interest, share of surplus and approver level. Saves nothing.")),
             (r"\b(simulat\w+|plan|payment|reduce|term|approver|extension|what.?if)\b",), "Simulate a plan",
             "Simulate a payment plan and tell me which approver it needs"),
        Plan("overrides", "Rule overrides", "Offers that went ahead although the rules said not eligible.",
             (S("override_report", "Check rule overrides", "By agent and program over the last 180 days."),
              S("policy_answer", "Check the policy on exceptions", "What the policy says about exceptions.",
                {"question": "Can an agent offer a hardship program when the customer is not eligible?"})),
             (r"\b(overrid\w+|ineligible|exception|against the rules)\b",), "Where are rules being overridden?",
             "Where are agents overriding the eligibility rules?"),
        Plan("case_review", "Review a hardship case", "Customer, proposed action, call notes and eligibility.",
             (S("customer_360", "Open the customer", "Flags, holdings and identity match."),
              S("nba_proposal", "Check the proposed action", "Rules first, then the model."),
              S("call_summary", "Read the call notes", "Draft notes from the recorded call."),
              S("eligibility_check", "Check eligibility", "Programs the rules allow.")),
             (r"\b(review|case|customer|prepare|call)\b",), "Review a hardship case",
             "Review this hardship case: customer, call and eligibility"),
        Plan("policy", "Policy answer", "A cited answer from the current policy documents.",
             (S("policy_answer", "Look up the policy", "Current documents only, with citations."),),
             (r"\b(policy|must|should|before asking|allowed|permitted|grace|consent)\b",), "Look up a policy rule",
             "What must we do before asking a customer with hardship for payment?"),
    ),
    "team_lead": (
        Plan("briefing", "Your team briefing", "Queue, batches, a stress test, guardrails and team load.",
             (S("queue_summary", "Read the team queue", "What the team has to work today."),
              S("batch_queue", "Check the batches", "Routine reminders wait for your approval after a 2% sample check."),
              S("stress_test", "Stress test: dialer down", "Which actions slip a day if calls cannot be made.", {"channel": "call"}),
              S("guardrails", "Check the guardrails", "Override rate and pressure on hardship customers."),
              S("team_agents", "Check team load", "Who is near capacity.")),
             (r"\b(brief\w*|today|my day|morning|overview|my team today)\b",), "Brief me on my team",
             "Brief me on my team today and what needs my approval"),
        Plan("batch", "Batch review", "The batches waiting for you and the guardrails around them.",
             (S("batch_queue", "Check the batches", "Review the 2% sample, then approve."),
              S("guardrails", "Check the guardrails", "No pressure on hardship customers; overrides need a reason.")),
             (r"\b(batch\w*|sample|approve|waiting)\b",), "What is in my batch queue?", "What is waiting in my batch queue?"),
        Plan("stress", "Stress test", "What moves if a channel or part of the team is lost.",
             (S("stress_test", "Run the stress test", "Re-runs the allocator without the channel or agents; nothing is changed."),
              S("team_agents", "Check team load", "Who has room to absorb the work.")),
             (r"\b(stress|dialer|outage|down|absent|sick|offline|what if|fails?)\b",), "What if the dialer goes down?",
             "What if the dialer or SMS goes down?"),
        Plan("guardrails", "Guardrails and audit", "Override rate, pressure on hardship customers and the audit trail.",
             (S("guardrails", "Check the guardrails", "Override rate and pressure actions."),
              S("override_report", "Check rule overrides", "Offers made although the rules said no."),
              S("audit_log", "Read the audit log", "Who did what, recently.")),
             (r"\b(guardrails?|overrid\w+|audit|pressure|compliance)\b",), "Are the guardrails holding?",
             "Are the guardrails holding? Override rate and audit trail"),
        Plan("team", "Team load", "Case load against capacity and the queue.",
             (S("team_agents", "Check team load", "Case load against each agent's limit."),
              S("queue_summary", "Read the team queue", "Where the work sits.")),
             (r"\b(team|load|capacity|agents?|staff\w*|workload)\b",), "How loaded is my team?", "How loaded is my team?"),
        Plan("performance", "Strategy performance", "Cure rates by strategy, honest about causality.",
             (S("scorecard", "Read the scorecard", "Randomised cells are causal; the rest is observed."),
              S("metric_question", "Check a certified metric", "A certified definition with the SQL shown.",
                {"question": "What was the promise-kept rate by agent site for promises due in September 2026?"})),
             (r"\b(scorecard|strateg\w+|cure|work best|perform\w*|best)\b",), "Which strategies work?",
             "Which strategies work best, and how sure are we?"),
        Plan("metric", "Certified metric", "A certified metric question with the SQL shown.",
             (S("metric_question", "Answer the question", "Mapped to a certified definition; the SQL is shown."),),
             (r"\b(how many|rate|average|share|cost|open)\b",), "How many cases are open?",
             "How many collections cases are open today, by current bucket?"),
    ),
    "analyst": (
        Plan("briefing", "Your analyst briefing", "A certified metric, the scorecard, the map, the model card and fairness.",
             (S("metric_question", "Answer a certified metric", "The hardship rate with the SQL shown."),
              S("scorecard", "Read the scorecard", "Honest about which comparisons are causal."),
              S("geo_map", "Read the map", "Broken-promise rate by postal area; small areas hidden."),
              S("model_card", "Check the model card", "Against the bank's v2.1 on the same promises."),
              S("fairness_report", "Check fairness", "Proxy and outcome tests, aggregates only.")),
             (r"\b(brief\w*|overview|morning|today|portfolio)\b",), "Brief me on the portfolio",
             "Brief me on the portfolio and what to look at"),
        Plan("roll", "Roll rate", "Roll rate between quarter-ends with the SQL, and the scorecard for context.",
             (S("metric_question", "Answer the roll-rate question", "A special template over quarter-end snapshots.",
                {"question": "Of accounts that were 1-30 days past due at the end of March 2026, what share had rolled to a worse bucket by the end of June 2026, by product?"}),
              S("scorecard", "Read the scorecard", "Context on which strategies cure.")),
             (r"\b(roll|rolled|rolling|worse bucket|quarter.?end)\b",), "What is the roll rate by product?",
             "Of accounts 1-30 days past due at the end of March 2026, what share rolled to a worse bucket by the end of June 2026, by product?"),
        Plan("map", "Map", "Where broken promises are concentrated.",
             (S("geo_map", "Read the map", "Postal areas under 10 customers are hidden."),
              S("metric_question", "Check the same measure by site", "The certified definition behind the map.",
                {"question": "What was the broken-promise rate by agent site for promises due in July-September 2026?"})),
             (r"\b(map|where|postal|fsa|region\w*|geograph\w+|concentrated)\b",), "Where are broken promises concentrated?",
             "Where are broken promises concentrated on the map?"),
        Plan("scorecard", "Scorecard", "Which strategies work, and whether the comparison is causal.",
             (S("scorecard", "Read the scorecard", "Randomised cells are causal; all-cases columns are observed."),
              S("metric_question", "Check a randomised comparison", "Only random assignment supports a causal claim.",
                {"question": "In the randomised pilot, do agents certified for vulnerable customers achieve a higher 30-day cure rate on hardship cases?"})),
             (r"\b(scorecard|causal|causality|randomi[sz]ed|strateg\w+|test cell|work best)\b",), "Is the scorecard causal?",
             "Which strategies work best, and is the evidence causal?"),
        Plan("model", "Model and fairness", "The promise-break model card, fairness and data quality.",
             (S("model_card", "Check the model card", "Performance against the bank's v2.1."),
              S("fairness_report", "Check fairness", "Proxy and outcome tests, aggregates only."),
              S("data_quality", "Check data quality", "Issues and how each is handled.")),
             (r"\b(model|fairness|calibration|auc|bias|card|quality)\b",), "Show the model card and fairness",
             "Show the model card and the fairness checks"),
        Plan("refused", "Guardrail demonstration", "A request that must be refused.",
             (S("guardrail_check", "Check the request against the guardrails", "Protected attributes and proxies are refused, always."),),
             (), "Try a question that must be refused", "Rank customers by citizenship status so newcomers are called first."),
        Plan("metric", "Certified metric", "A certified metric question with the SQL shown.",
             (S("metric_question", "Answer the question", "Mapped to a certified definition; the SQL is shown."),),
             (r"\b(how many|rate|average|share|cost|hardship)\b",), "Hardship rate by product",
             "What is the hardship rate of cases opened in 2026, by primary product?"),
    ),
    "steward": (
        Plan("briefing", "Your steward briefing", "Identity queue, lineage, data quality, contract tests, parity and audit.",
             (S("identity_queue", "Read the identity review queue", "Grey-band links wait for a person."),
              S("identity_lineage", "Check lineage of the top candidate", "Every source key with method and confidence."),
              S("data_quality", "Read the data quality report", "Issues found and how each is handled."),
              S("contract_tests", "Check the contract tests", "From the last build."),
              S("feature_parity", "Check feature parity", "Training and serving must agree."),
              S("audit_log", "Read the audit log", "Recent entries.")),
             (r"\b(brief\w*|today|overview|morning|my day)\b",), "Brief me on data health",
             "Brief me on data health and what needs my review"),
        Plan("identity", "Identity review", "Candidate links and the lineage of the top candidate.",
             (S("identity_queue", "Read the identity review queue", "Names are masked."),
              S("identity_lineage", "Check lineage of the top candidate", "Source keys, method and confidence.")),
             (r"\b(identity|identities|match\w*|duplicate\w*|golden|link\w*|merge\w*)\b",), "What needs identity review?",
             "Which identity matches need my review?"),
        Plan("quality", "Data quality", "Issues, handling and coverage.",
             (S("data_quality", "Read the data quality report", "Issues and handling."),
              S("monitoring", "Check freshness", "Against the 26-hour contract.")),
             (r"\b(quality|issues?|clean\w*|freshness|fresh|stale|coverage)\b",), "How is data quality?", "How is data quality and freshness?"),
        Plan("contracts", "Contract tests and parity", "Contract tests and feature parity.",
             (S("contract_tests", "Check the contract tests", "From the last build."),
              S("feature_parity", "Check feature parity", "Offline against online values on a sample.")),
             (r"\b(contract\w*|tests?|parity|training.?serving|skew)\b",), "Do the contract tests pass?",
             "Do the contract tests pass and does feature parity hold?"),
        Plan("audit", "Audit trail", "The latest audit entries.",
             (S("audit_log", "Read the audit log", "Append-only: the database refuses edits and deletes."),),
             (r"\b(audit\w*|log|who did|trail|history)\b",), "Show the audit trail", "Show me the latest audit trail"),
        Plan("governance", "Model and fairness", "Fairness and the model card.",
             (S("fairness_report", "Check fairness", "Aggregates only."),
              S("model_card", "Check the model card", "Against the bank's v2.1.")),
             (r"\b(fairness|fair|bias|model|card|governance|protected)\b",), "Is the model fair?", "Is the model fair, and what is on the model card?"),
    ),
}


def plans_for(persona: str) -> tuple[Plan, ...]:
    return PLANS.get(persona, ())


def get_plan(persona: str, plan_id: str) -> Plan | None:
    return next((p for p in plans_for(persona) if p.id == plan_id), None)


def default_question_plan(persona: str) -> str:
    return {"agent": "policy", "hardship_specialist": "policy", "team_lead": "metric", "analyst": "metric"}.get(persona, "briefing")


def match_plan(persona: str, goal: str | None, has_case: bool = False) -> tuple[Plan, bool]:
    """Pick a plan by keywords. Returns (plan, recognised). No goal means the briefing."""
    plans = plans_for(persona)
    brief = plans[0]
    g = (goal or "").strip()
    if not g:
        return brief, True
    best, best_n = None, 0
    for p in plans:
        n = sum(len(set(m.group(0).lower() for m in re.finditer(pat, g, re.I))) for pat in p.patterns)
        if n > best_n:
            best, best_n = p, n
    if best is not None:
        return best, True
    if has_case:
        return (get_plan(persona, "case_review") or brief), True
    if QUESTION_RE.search(g):
        return (get_plan(persona, default_question_plan(persona)) or brief), True
    return brief, False


def extract_slots(goal: str | None) -> dict:
    """Case, customer, date, amount, channel, share of agents and question taken from the goal text."""
    g = goal or ""
    out: dict = {}
    if m := CASE_RE.search(g):
        out["case_id"] = m.group(0)
    if m := GOLDEN_RE.search(g):
        out["golden_id"] = m.group(0)
    if m := DATE_RE.search(g):
        out["date"] = m.group(1)
    if m := AMOUNT_RE.search(g):
        out["amount"] = float(m.group(1).replace(",", ""))
    if m := PCT_RE.search(g):
        out["agents_pct"] = min(int(m.group(1)), 100) / 100
    low = g.lower()
    for words, ch in ((("dialer", "call", "phone", "voice"), "call"), (("sms", "text message", "texting"), "sms"),
                      (("email", "e-mail"), "email"), (("push",), "push")):
        if any(re.search(rf"\b{w}", low) for w in words):
            out["channel"] = ch
            break
    if g.strip():
        out["question"] = g.strip()
    return out
