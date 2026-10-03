"""Policy gate: plain rules BEFORE any model. Returns allowed actions plus a reason code for every exclusion.
Never put an LLM here.

Rules: cease/insolvency/deceased -> no contact; a representative -> a person; an open dispute -> pause; each channel
needs consent (unknown means no); calls only inside permitted_call_start/end_local in the customer's time zone, not
on Sundays (V1: "never Sundays"; see SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS), not on statutory holidays; no more contacts
than contact_cap_7d in a week; internal_do_not_call_flag blocks calls; hardship possible/clear or a vulnerability
flag removes pressure treatments and routes to a trained agent; stale features block pressure. national_dncl_flag
and CASL consent are marketing-only and ignored here by design.

The customer is a plain dict (see `customer_from_row`) so the same function serves the nightly queue, one live
case and the spec suite. Protected attributes are never read.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from common.types import PRESSURE_TREATMENTS
from decisioning.schemas import Action, BlockedAction, GateResult, ReasonCode

CHANNEL_LABEL = {"call": "call", "sms": "text message", "email": "email", "push": "app message", "letter": "letter"}
CONSENT_CHANNELS = ("call", "sms", "email", "push")
HOURS_RULE_CHANNELS = {"call"}
STALE_HOURS = 26  # data contract rule 11
# Decided 3 Oct: no Sunday calls, for anyone. V1 section 6 says "never Sundays" (v2 allowed an exception through
# sunday_contact_permitted), the specification suite tests V1, and agents get a day of rest. The per-customer flag is
# read but does not unlock Sunday calls. Leave this False.
SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS = False

BLOCK_TEXT = {
    "cease": ("CEASE_CONTACT", "No contact: the customer asked us to stop"),
    "insolvency": ("INSOLVENCY_HOLD", "No contact: insolvency hold, the trustee handles this"),
    "deceased": ("DECEASED_HOLD", "No contact: deceased customer, the estate team handles this"),
}


def _easter(year: int) -> date:
    a, b, c = year % 19, year // 100, year % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    ell = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * ell) // 451
    month, day = divmod(h + ell - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_monday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(7 - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def holidays(year: int) -> dict[date, str]:
    """National statutory holidays that apply in every province. Provincial extras (Family Day, Civic Holiday,
    Quebec's Fete nationale and so on) are TBC with Compliance and not included."""
    victoria = date(year, 5, 24)
    victoria -= timedelta(days=(victoria.weekday() - 0) % 7)
    return {
        date(year, 1, 1): "New Year's Day",
        _easter(year) - timedelta(days=2): "Good Friday",
        victoria: "Victoria Day",
        date(year, 7, 1): "Canada Day",
        _nth_monday(year, 9, 1): "Labour Day",
        _nth_monday(year, 10, 2): "Thanksgiving",
        date(year, 12, 25): "Christmas Day",
        date(year, 12, 26): "Boxing Day",
    }


def _hm(s: str | None, default: str) -> time:
    s = (s or default)[:5]
    h, m = s.split(":")
    return time(int(h), int(m))


def customer_from_row(row: dict) -> dict:
    """The gate's view of a customer, from a `decisioning.context.load_cases` row."""

    def yes(v):
        return None if v is None or v != v else bool(v)

    hard = row.get("hardship_flag")
    return {
        "time_zone": row.get("time_zone") or "America/Toronto",
        "consent": {c: yes(row.get(f"consent_{c}")) for c in CONSENT_CHANNELS},
        "permitted_call_start_local": row.get("permitted_call_start_local") or "08:00",
        "permitted_call_end_local": row.get("permitted_call_end_local") or "20:00",
        "sunday_contact_permitted": bool(row.get("sunday_contact_permitted")),
        "internal_do_not_call_flag": bool(row.get("internal_do_not_call_flag")),
        "contact_block": row.get("contact_block") or "none",
        "third_party_rep_flag": bool(row.get("third_party_rep_flag")),
        "dispute_open_flag": bool(row.get("dispute_open_flag")),
        "hardship_flag": hard if hard in ("possible", "clear") else "none",
        "vulnerability_flag": bool(row.get("vulnerability_flag")),
        "contacts_last_7d": int(row.get("contacts_last_7d") or 0),
        "contact_cap_7d": int(row.get("contact_cap_7d") or 3),
    }


def _rule(rules: dict[str, ReasonCode], code: str, text: str) -> str:
    rules.setdefault(code, ReasonCode(code=code, text=text, kind="rule"))
    return code


def gate(customer: dict, candidates: list[Action], at: datetime, feature_age_hours: float | None = None) -> GateResult:
    """Apply the contact rules to every candidate action at time `at` (or the action's own `scheduled_at`)."""
    rules: dict[str, ReasonCode] = {}
    blocked: list[BlockedAction] = []
    allowed: list[Action] = []
    block = customer.get("contact_block") or "none"

    def refuse_all(disposition: str, code: str, route: str | None = None) -> GateResult:
        for a in candidates:
            if a.treatment != "no_contact":
                blocked.append(BlockedAction(treatment=a.treatment, channel=a.channel, code=code))
        return GateResult(
            disposition=disposition, allowed=[], blocked=blocked, rules_fired=list(rules.values()), route_to=route
        )

    if block in BLOCK_TEXT:
        code, text = BLOCK_TEXT[block]
        return refuse_all("no_contact", _rule(rules, code, text))
    if block == "represented" or customer.get("third_party_rep_flag"):
        code = _rule(
            rules,
            "THIRD_PARTY_REP",
            "A representative acts for this customer: a person handles it, no automated contact",
        )
        return refuse_all("route_to_person", code, "person")
    if customer.get("dispute_open_flag"):
        return refuse_all(
            "paused", _rule(rules, "DISPUTE_OPEN", "Open dispute: collection contact is paused until it is resolved")
        )

    hardship = customer.get("hardship_flag") or "none"
    vulnerable = bool(customer.get("vulnerability_flag"))
    gentle_only = hardship in ("possible", "clear") or vulnerable
    stale = feature_age_hours is not None and feature_age_hours > STALE_HOURS
    used, cap = int(customer.get("contacts_last_7d") or 0), int(customer.get("contact_cap_7d") or 3)
    tz = ZoneInfo(customer.get("time_zone") or "America/Toronto")
    start, end = (
        _hm(customer.get("permitted_call_start_local"), "08:00"),
        _hm(customer.get("permitted_call_end_local"), "20:00"),
    )
    consent = customer.get("consent") or {}
    pressure_removed = False

    for a in candidates:
        if a.treatment == "no_contact":
            continue
        ch = a.channel.value if hasattr(a.channel, "value") else a.channel
        label = CHANNEL_LABEL.get(ch or "", ch or "contact")
        tre = a.treatment.value if hasattr(a.treatment, "value") else a.treatment
        why: str | None = None

        if gentle_only and a.treatment in PRESSURE_TREATMENTS:
            why = _rule(
                rules,
                "HARDSHIP_NO_PRESSURE" if hardship != "none" else "VULNERABLE_NO_PRESSURE",
                "Hardship flagged: pressure actions are paused, a trained agent handles this"
                if hardship != "none"
                else "Vulnerable customer: pressure actions are paused, a trained agent handles this",
            )
            pressure_removed = True
        elif stale and a.treatment in PRESSURE_TREATMENTS:
            why = _rule(
                rules,
                "FEATURES_STALE",
                f"Data is more than {STALE_HOURS} hours old: no automated pressure until it refreshes",
            )
        elif ch in CONSENT_CHANNELS and consent.get(ch) is not True:
            why = _rule(rules, f"NO_CONSENT_{ch.upper()}", f"No {label}: no consent on file for this channel")
        elif used >= cap:
            why = _rule(rules, "CAP_7D_REACHED", f"No {label}: {used} of {cap} contacts used this week")
        elif ch in HOURS_RULE_CHANNELS:
            if customer.get("internal_do_not_call_flag"):
                why = _rule(rules, "INTERNAL_DNC", "No call: on the internal do-not-call list")
            else:
                when = a.scheduled_at or at
                local = when.astimezone(tz) if when.tzinfo else when.replace(tzinfo=tz)
                d = local.date()
                if d in holidays(d.year):
                    why = _rule(rules, "HOLIDAY", f"No call: {holidays(d.year)[d]} is a statutory holiday")
                elif local.weekday() == 6 and not (
                    SUNDAY_FLAG_UNLOCKS_SUNDAY_CALLS and customer.get("sunday_contact_permitted")
                ):
                    why = _rule(rules, "SUNDAY", "No call on Sundays")
                elif not (start <= local.time() < end):
                    why = _rule(
                        rules,
                        "OUTSIDE_HOURS",
                        f"No call: outside permitted hours {start:%H:%M} to {end:%H:%M} local time",
                    )
        if why:
            blocked.append(BlockedAction(treatment=tre, channel=ch, code=why))
        else:
            allowed.append(a)

    route = None
    if pressure_removed or gentle_only:
        route = "hardship_specialist" if hardship != "none" else "vulnerable_customer_certified"
        if hardship == "none" and not pressure_removed:
            _rule(
                rules,
                "VULNERABLE_NO_PRESSURE",
                "Vulnerable customer: pressure actions are paused, a trained agent handles this",
            )
        elif hardship != "none":
            _rule(
                rules,
                "HARDSHIP_NO_PRESSURE",
                "Hardship flagged: pressure actions are paused, a trained agent handles this",
            )
    fired = list(rules.values())
    return GateResult(
        disposition="contact_allowed",
        allowed=allowed,
        blocked=blocked,
        rules_fired=fired,
        route_to=route,
        pressure_removed=pressure_removed or gentle_only,
    )
