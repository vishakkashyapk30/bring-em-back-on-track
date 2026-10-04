"""Semantic layer: certified metrics, dimensions and filters, mapped onto the typed silver tables (plan D6).

Each metric is defined once (formula, base table, default filters, time column) following the release's
metric_definitions, so the same question always compiles to the same SQL. Ask never writes free-form SQL in the
offline mode: questions map onto these definitions, and anything that doesn't map is refused or answered from
documents. Base tables use the release's own table and column names (silver schema), so the SQL shown to users
reads like the data dictionary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Metric:
    id: str
    patterns: tuple[str, ...]            # regexes that identify the metric in a question
    base: str                            # FROM clause with alias
    select: str                          # value expressions (already aliased)
    where: tuple[str, ...] = ()          # default filters (metric_definitions.default_filters)
    time_col: str | None = None          # column the question's time range applies to
    alias: str = "x"                     # base alias, used by dimensions to choose joins
    order_by_value: bool = False


@dataclass(frozen=True)
class Dimension:
    id: str
    patterns: tuple[str, ...]
    expr: dict[str, str]                 # base alias -> expression
    joins: dict[str, str] = field(default_factory=dict)   # base alias -> JOIN clause it needs


CALL_OUT = "coalesce(h.channel_v2, h.channel) = 'call' AND h.direction = 'outbound'"
RESOLVED = "p.ptp_status IN ('kept', 'partially_kept', 'broken')"

METRICS: list[Metric] = [
    Metric("broken_promise_count", (r"how many (promises( to pay)? )?(were |was )?broken", r"(which|what) customers? (broke|broken|missed) (a |their )?promises?", r"number of broken promises", r"broken promises (were there|by)",
                                    r"count of broken promises"),
           "promises_to_pay p", "count(*) AS broken_promises", ("p.ptp_status = 'broken'",), "p.ptp_due_date", "p"),
    Metric("kept_promise_count", (r"number of (promises )?kept", r"how many promises( to pay)? (were |was )?kept"),
           "promises_to_pay p", "count(*) AS kept_promises", ("p.ptp_status = 'kept'",), "p.ptp_due_date", "p"),
    Metric("broken_promise_rate", (r"broken[- ]promise rate", r"break(ing)? (a )?promise", r"broken promises? rate"),
           "promises_to_pay p",
           "round(100.0 * avg(CASE WHEN p.ptp_status = 'broken' THEN 1 ELSE 0 END), 1) AS broken_rate_pct, count(*) AS promises",
           (RESOLVED,), "p.ptp_due_date", "p"),
    Metric("promise_kept_rate", (r"promise[- ]kept rate", r"kept rate", r"keep(ing)? (their )?promises?",
                                 r"promises? (were |was )?kept", r"(share|percentage|proportion) of promises", r"ptp kept rate", r"kept promises"),
           "promises_to_pay p",
           "round(100.0 * avg(CASE WHEN p.ptp_status = 'kept' THEN 1 ELSE 0 END), 1) AS promise_kept_rate_pct, count(*) AS promises",
           (RESOLVED,), "p.ptp_due_date", "p"),
    Metric("paid_against_promises", (r"paid against promises", r"paid (on|toward|towards) promises", r"amount paid against", r"collected (amount|dollars)", r"(amount|dollars|money) collected", r"how much (did we |was |were )?(collect|recover)", r"\brecover(ed|ies)\b", r"collections? (total|amount)"),
           "promises_to_pay p",
           "round(sum(p.amount_paid_against), 2) AS amount_paid_cad, count(*) FILTER (WHERE p.amount_paid_against > 0) AS promises_paid",
           (), "p.paid_date", "p"),
    Metric("average_dpd", (r"average days past due", r"average dpd", r"mean dpd", r"avg dpd", r"average arrears", r"mean days past due"),
           "collections_cases c", "round(avg(c.current_dpd), 1) AS avg_dpd, count(*) AS open_cases",
           ("c.outcome IS NULL",), None, "c"),
    Metric("cost_per_rpc", (r"cost per right[- ]party", r"cost per rpc", r"cost (of|per) (each )?rpc"),
           "contact_history h",
           "round(sum(h.contact_cost_cad) / nullif(count(*) FILTER (WHERE h.rpc_flag), 0), 2) AS cost_per_rpc_cad, count(*) FILTER (WHERE h.rpc_flag) AS rpcs",
           ("coalesce(h.channel_v2, h.channel) <> 'system'",), "h.contact_ts_local", "h"),
    Metric("cost_per_contact", (r"cost per contact", r"contact cost", r"cost per attempt", r"(spend|spent|cost) per (contact|attempt|touch)", r"how much (did we|do we) (spend|pay) per"),
           "contact_history h", "round(avg(h.contact_cost_cad), 2) AS cost_per_contact_cad, count(*) AS contacts",
           ("coalesce(h.channel_v2, h.channel) <> 'system'",), "h.contact_ts_local", "h"),
    Metric("average_overdue", (r"average (amount )?(past due|overdue)", r"average overdue", r"mean (amount )?(past due|overdue)"),
           "collections_cases c", "round(avg(c.total_overdue), 2) AS avg_overdue_cad, count(*) AS open_cases",
           ("c.outcome IS NULL",), None, "c"),
    Metric("cases_on_hardship_plan", (r"(on|under|in) (a )?(hardship|payment) plans?", r"hardship plans? (today|now|active)",
                                      r"accepted (a )?(hardship )?(plan|program)"),
           "collections_cases c", "count(*) AS cases_on_plan", ("c.outcome IS NULL", "c.hardship_program_accepted"), None, "c"),
    Metric("rpc_rate", (r"right[- ]party contact rate", r"\brpc rate", r"right[- ]party contact"),
           "contact_history h",
           "round(100.0 * avg(CASE WHEN h.rpc_flag THEN 1 ELSE 0 END), 1) AS rpc_rate_pct, count(*) AS attempts",
           (CALL_OUT,), "h.contact_ts_local", "h"),
    Metric("out_of_hours_share", (r"outside permitted (calling )?hours", r"out[- ]of[- ]hours"),
           "contact_history h",
           "round(100.0 * avg(CASE WHEN NOT h.within_permitted_hours_flag THEN 1 ELSE 0 END), 2) AS out_of_hours_pct, count(*) AS calls",
           (CALL_OUT,), "h.contact_ts_local", "h"),
    Metric("loan_delinquency_rate", (r"(personal|auto|student|unsecured|mortgage|line of credit|loc|loan)s?\b.{0,60}(delinquen|past due|arrears)",
                                     r"(delinquen|past due|arrears).{0,60}\b(personal|auto|student|unsecured|mortgage|line of credit|loc|loan)s?\b"),
           "loan_accounts ln",
           "round(100.0 * avg(CASE WHEN ln.dpd >= 1 THEN 1 ELSE 0 END), 2) AS delinquency_rate_pct, count(*) AS accounts",
           ("ln.snapshot_date = DATE '{as_of}'", "NOT coalesce(ln.chargeoff_flag, false)", "ln.dpd IS NOT NULL"),
           None, "ln"),
    Metric("delinquency_rate", (r"days past due today", r"delinquen(cy|t) (rate|share)", r"\d+ or more days past due", r"past due today",
                                r"share of active .* past due", r"arrears rate", r"(share|percentage|proportion) of .{0,30}accounts .{0,25}past due"),
           "card_accounts a",
           "round(100.0 * avg(CASE WHEN a.dpd >= 1 THEN 1 ELSE 0 END), 2) AS delinquency_rate_pct, count(*) AS accounts",
           ("a.snapshot_date = DATE '{as_of}'", "a.account_status IN ('active', 'blocked')", "a.dpd IS NOT NULL"),
           None, "a"),
    Metric("hardship_rate", (r"hardship rate", r"share of cases with (financial )?hardship", r"hardship share", r"(share|percentage|proportion) of (open )?cases .{0,25}hardship", r"flagged (as )?(in )?hardship"),
           "collections_cases c",
           "round(100.0 * avg(CASE WHEN c.hardship_flag THEN 1 ELSE 0 END), 1) AS hardship_rate_pct, count(*) AS cases",
           (), "c.case_open_date", "c"),
    Metric("cure_rate", (r"cure rate", r"\bcured\b", r"\bcures?\b", r"self[- ]cure", r"back to current", r"cure within", r"worked best", r"most effective",
                         r"best (performing )?strateg", r"which strateg"),
           "collections_cases c",
           "round(100.0 * avg(CASE WHEN c.cure_flag AND c.days_to_cure <= {cure_days} THEN 1 ELSE 0 END), 1) AS cure_rate_pct, count(*) AS cases, round(100.0 * avg(CASE WHEN c.cure_flag THEN 1 ELSE 0 END), 1) AS cured_any_time_pct",
           # certified default filter (metric_definitions.cure_rate): exclude insolvency and deceased holds
           ("NOT coalesce(c.insolvency_hold_flag, false)", "NOT coalesce(c.deceased_hold_flag, false)"),
           "c.case_open_date", "c"),
    Metric("ptp_rate", (r"\bptp rate", r"promises? (taken|made) per", r"promise[- ]to[- ]pay rate", r"\bpromise rate", r"ptp per rpc", r"promises? per right[- ]party"),
           "contact_history h",
           "round(100.0 * count(*) FILTER (WHERE h.ptp_made_flag) / nullif(count(*) FILTER (WHERE h.rpc_flag), 0), 1) AS ptp_rate_pct, count(*) FILTER (WHERE h.rpc_flag) AS rpcs",
           (), "h.contact_ts_local", "h"),
    Metric("contact_attempts_per_case", (r"(outbound )?(contact )?attempts .*per case", r"attempts per case", r"contact intensity", r"touches per case", r"contact attempts .*(average|on average).*case", r"average .*case (receive|get)", r"how many (outbound )?contact attempts does",
                                         r"outbound contact attempts .* on average", r"how many outbound contact attempts"),
           "collections_cases c LEFT JOIN contact_history h ON h.case_id = c.case_id AND h.direction = 'outbound' AND coalesce(h.channel_v2, h.channel) <> 'system'",
           "round(count(h.contact_id) * 1.0 / count(DISTINCT c.case_id), 2) AS attempts_per_case, count(DISTINCT c.case_id) AS open_cases",
           ("c.outcome IS NULL",), None, "c"),
    Metric("open_case_count", (r"how many (collections )?cases (are )?open", r"number of open cases", r"open cases today",
                               r"cases are open", r"open cases (do we|are there|exist)", r"how many open cases", r"count of open cases"),
           "collections_cases c", "count(*) AS open_cases", ("c.outcome IS NULL",), None, "c"),
    Metric("contact_count", (r"how many (outbound )?(calls|contacts|contact attempts|sms|texts|emails|letters|attempts)\b",
                             r"number of (outbound )?(calls|contacts|contact attempts|sms|texts|emails)",
                             r"outbound (call|contact) volume"),
           "contact_history h", "count(*) AS contacts", ("h.direction = 'outbound'", "coalesce(h.channel_v2, h.channel) <> 'system'"),
           "h.contact_ts_local", "h"),
    Metric("dispute_count", (r"disputes? (were )?raised", r"how many (late[- ]fee )?disputes"),
           "contact_history h", "count(*) AS disputes", ("h.dispute_raised_flag",), "h.contact_ts_local", "h"),
    Metric("complaint_count", (r"how many complaints", r"complaints? (were )?raised"),
           "contact_history h", "count(*) AS complaints", ("h.complaint_raised_flag",), "h.contact_ts_local", "h"),
    Metric("payroll_delay_share", (r"payroll delay", r"payroll (deposit )?(more than )?\d+ days late", r"(delayed|late) payroll", r"payroll .{0,20}late", r"missed pay"),
           "deposit_accounts d",
           "round(100.0 * avg(CASE WHEN d.payroll_delay_days > 7 THEN 1 ELSE 0 END), 1) AS payroll_delay_share_pct, count(*) AS accounts",
           ("d.payroll_deposit_flag",), None, "d"),
    Metric("write_off", (r"charged off", r"charge[- ]offs?", r"written off", r"write[- ]offs?", r"loss rate"),
           "(SELECT 'card' AS product, chargeoff_date, chargeoff_amount, chargeoff_flag FROM card_accounts "
           "UNION ALL SELECT product_type, chargeoff_date, chargeoff_amount, chargeoff_flag FROM loan_accounts) w",
           "count(*) AS accounts_charged_off, round(sum(w.chargeoff_amount), 2) AS chargeoff_amount_cad",
           ("w.chargeoff_flag",), "w.chargeoff_date", "w"),
    Metric("case_count", (r"how many (collections )?cases", r"number of cases"),
           "collections_cases c", "count(*) AS cases", (), "c.case_open_date", "c"),
]

DIMENSIONS: list[Dimension] = [
    Dimension("prior_broken", (r"previously broken", r"prior broken", r"number of (previously )?broken promises"),
              {"p": "least(p.prior_broken_ptp_count, 3)"}),
    Dimension("agent_site", (r"agent site", r"\bby site\b", r"\bsites?\b"),
              {"p": "coalesce(a.site, 'self_serve')", "h": "coalesce(a.site, 'self_serve')", "c": "coalesce(a.site, 'self_serve')"},
              {"p": "LEFT JOIN agents a ON a.agent_id = p.agent_id", "h": "LEFT JOIN agents a ON a.agent_id = h.agent_id",
               "c": "LEFT JOIN agents a ON a.agent_id = c.assigned_agent_id"}),
    Dimension("queue", (r"\bqueues?\b",), {"c": "c.queue", "p": "c.queue", "h": "c.queue"},
              {"p": "JOIN collections_cases c ON c.case_id = p.case_id", "h": "JOIN collections_cases c ON c.case_id = h.case_id"}),
    Dimension("province", (r"province",), {"c": "c.province_code", "h": "c.province_code", "p": "c.province_code"},
              {"h": "JOIN collections_cases c ON c.case_id = h.case_id", "p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    Dimension("hour", (r"hour of (the )?day", r"local hour", r"\bby hour\b"), {"h": "h.contact_hour_local"}),
    Dimension("card_product", (r"card product", r"product code"), {"a": "a.product_code"}),
    Dimension("current_bucket", (r"current bucket", r"\bby bucket\b", r"delinquency bucket", r"\bbuckets?\b"),
              {"c": "c.current_bucket", "p": "c.current_bucket", "h": "c.current_bucket"},
              {"p": "JOIN collections_cases c ON c.case_id = p.case_id", "h": "JOIN collections_cases c ON c.case_id = h.case_id"}),
    Dimension("test_cell", (r"test cells?", r"champion", r"challenger"),
              {"c": "c.test_cell", "p": "c.test_cell", "h": "h.test_cell"},
              {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    Dimension("strategy", (r"\bstrateg(y|ies)\b",), {"c": "c.strategy_code", "p": "c.strategy_code", "h": "h.strategy_code"},
              {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    Dimension("channel", (r"\bby channel\b", r"\bchannels?\b"), {"h": "coalesce(h.channel_v2, h.channel)"}),
    Dimension("primary_product", (r"primary product",), {"c": "c.primary_product", "p": "c.primary_product"},
              {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    Dimension("product", (r"\bby product\b", r"\bproducts?\b"),
              {"p": "p.product", "c": "c.primary_product", "w": "w.product", "a": "a.product_code", "ln": "ln.product_type", "s": "s.product_type"}),
    Dimension("team", (r"agent team", r"\bteams?\b"), {"c": "c.assigned_team", "p": "c.assigned_team", "h": "a.team_id"},
              {"p": "JOIN collections_cases c ON c.case_id = p.case_id", "h": "LEFT JOIN agents a ON a.agent_id = h.agent_id"}),
    Dimension("month", (r"\bby month\b", r"\bmonthly\b", r"per month"),
              {"p": "date_trunc('month', p.ptp_due_date)", "c": "date_trunc('month', c.case_open_date)",
               "h": "date_trunc('month', h.contact_ts_local)"}),
    Dimension("payment_method", (r"payment method", r"method promised", r"how (customers|they) (promised|pay)"),
              {"p": "coalesce(p.payment_method_promised, 'not stated')"}),
    Dimension("promise_type", (r"promise type", r"\bptp type", r"single or instalment"), {"p": "p.ptp_type"}),
    Dimension("agent", (r"\bby agent\b(?! site)", r"\beach agent\b", r"\bagents?\b.{0,30}\b(highest|lowest|best|worst|top)\b",
                        r"\b(which|top|best|worst) agents?\b", r"per agent"),
              {"p": "p.agent_id", "h": "h.agent_id", "c": "c.assigned_agent_id"}),
    Dimension("day", (r"\bby day\b", r"\bdaily\b", r"per day", r"\bby date\b"),
              {"p": "p.ptp_due_date", "c": "c.case_open_date", "h": "CAST(h.contact_ts_local AS DATE)"}),
    Dimension("weekday", (r"day of (the )?week", r"\bby weekday\b"), {"h": "h.day_of_week"}),
    Dimension("language", (r"\blanguage\b",), {"c": "c.language_of_service"}),
    Dimension("vulnerable_certified", (r"certified for vulnerable", r"vulnerable[- ]certified"),
              {"c": "cah.certified_for_vulnerable_flag"},
              {"c": "JOIN case_assignment_history cah ON cah.case_id = c.case_id"}),
]

# Filters: (pattern, base alias -> condition, base alias -> join)
FILTERS: list[tuple[str, dict[str, str], dict[str, str]]] = [
    (r"randomi[sz]ed pilot", {"c": "cah.assignment_method = 'randomised_pilot'"},
     {"c": "JOIN case_assignment_history cah ON cah.case_id = c.case_id"}),
    (r"randomi[sz]ed(?! pilot)", {"p": "c.assignment_method = 'random'", "c": "c.assignment_method = 'random'"},
     {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    (r"champion", {"p": "c.test_cell IN ('champion', 'challenger_A', 'challenger_B')", "c": "c.test_cell IN ('champion', 'challenger_A', 'challenger_B')"},
     {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    (r"hardship cases", {"c": "c.hardship_flag", "p": "c.hardship_flag"}, {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    (r"open cases", {"c": "c.outcome IS NULL", "p": "c.outcome IS NULL"}, {"p": "JOIN collections_cases c ON c.case_id = p.case_id"}),
    (r"unsecured loans?", {"c": "c.primary_product IN ('personal_loan', 'loc')", "p": "p.product IN ('personal_loan', 'loc')"}, {}),
    (r"personal loans?", {"ln": "ln.product_type = 'personal_loan'", "w": "w.product = 'personal_loan'"}, {}),
    (r"auto loans?", {"ln": "ln.product_type = 'auto_loan'", "w": "w.product = 'auto_loan'"}, {}),
    (r"mortgages?", {"ln": "ln.product_type = 'mortgage'", "w": "w.product = 'mortgage'"}, {}),
    (r"student (loans?|lines? of credit|loc)", {"ln": "ln.product_type = 'student_loc'", "w": "w.product = 'student_loc'"}, {}),
    (r"(unsecured )?lines? of credit|\bloc\b", {"ln": "ln.product_type IN ('unsecured_loc', 'student_loc')",
                                                  "w": "w.product IN ('unsecured_loc', 'student_loc')"}, {}),
    (r"credit cards?|\bcards?\b(?! product)", {"w": "w.product = 'card'"}, {}),
    (r"\bcalls?\b", {"h": CALL_OUT}, {}),
    (r"\b(sms|text messages?|texts)\b", {"h": "coalesce(h.channel_v2, h.channel) = 'sms'"}, {}),
    (r"\bemails?\b", {"h": "coalesce(h.channel_v2, h.channel) = 'email'"}, {}),
    (r"late[- ]fee", {"h": "h.dispute_raised_flag"}, {}),
]


def find(patterns: tuple[str, ...], text: str) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)
