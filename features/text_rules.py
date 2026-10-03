"""Offline text features and call summaries (no LLM), built from rules mined from the release's 500 public
labels each for transcripts and notes. Registered as the offline handler for the `text_features` and
`post_call_summary` prompts, so an LLM provider can replace them later without changing callers.

Fields follow the label schema: hardship (none/possible/clear), hardship_reason, stated_delay_reason, dispute and
dispute_type, complaint, cease_request, ptp (amount, date), next_step, and a summary in the gold template:
"Customer reports <reason>; disputes <type>; promised $<amount> on <d Mon>; wants to complain;
 asked to stop contact; next step: <step>."
"""

from __future__ import annotations

import re
from datetime import date

from llm.providers.offline import register

# Hardship reasons (customer turns), English and French phrasings seen in the transcripts.
REASONS: list[tuple[str, re.Pattern[str]]] = [
    ("ei_waiting", re.compile(r"\bEI hasn'?t started|waiting (for|on) (my )?EI|EI pending|employment insurance|assurance-emploi|attend l'?AE|en attente (de l'?)?AE", re.I)),
    ("disaster_evacuation", re.compile(r"flood|evacuat|wildfire|\bfire\b|feux|inond|staying with family", re.I)),
    ("rate_reset", re.compile(r"rate reset|payment went up|renewed at (a )?higher rate|renouvel|taux plus élevé|hausse de taux", re.I)),
    ("disability", re.compile(r"disability|invalidit", re.I)),
    ("illness", re.compile(r"medical leave|off work sick|\bsick\b|surgery|hospital|maladie|congé de maladie|chimio|cancer", re.I)),
    ("separation", re.compile(r"separation|divorc|one income now|split (up )?(with|w/) (my )?(partner|husband|wife|spouse)|séparation|rupture|séparé", re.I)),
    ("job_loss", re.compile(r"lost (my |his |her )?job|laid off|position (was )?eliminated|unemployed|perdu (mon |son )?emploi|mis à pied|licenci|poste aboli", re.I)),
    ("reduced_income", re.compile(r"(shifts|hours)\b.{0,30}\b(cut|reduced)|\b(cut|reduced) (my|our|his|her) (hours|shifts)|pay got cut|pay cut|reduced hours|lost (my )?overtime|making less now|less pay|pay was cut|only getting \d days a week|heures.{0,20}(coupées|réduites)|coupé des heures|salaire a été réduit|salaire.{0,15}(baiss|coup)|moins d'heures", re.I)),
]
REASON_PHRASE = {
    "reduced_income": "reduced hours / income", "job_loss": "job loss", "separation": "separation",
    "illness": "illness", "rate_reset": "payment increase after rate reset", "disability": "disability",
    "disaster_evacuation": "evacuation (disaster)", "ei_waiting": "waiting for EI",
}
TIGHT = re.compile(r"budget has been (really )?tight|money is tight|finances are tight|things are hard this month|i'?m struggling|difficile financièrement|budget (est )?serré|c'est dur ce mois", re.I)
DISPUTE_LATE_FEE = re.compile(r"late fee|frais de retard", re.I)
DISPUTE_BILLING = re.compile(r"statement is wrong|don'?t add up|billing error|relevé.{0,20}(faux|erron)", re.I)
DISPUTE_NOT_APPLIED = re.compile(r"payment and it wasn'?t applied|wasn'?t applied|not applied|n'a pas été appliqué", re.I)
DISPUTE_FRAUD = re.compile(r"aren'?t mine|it'?s fraud|\bfraud\b|ne sont pas à moi|fraude", re.I)
ESCALATE = re.compile(r"this is harassment|i'?m done with this|done this\.|tous les jours|j'en ai assez|harcèlement", re.I)
DISPUTE_GENERIC = re.compile(r"don'?t agree with (that|this) charge|not my (charge|purchase)|didn'?t authori[sz]e|conteste", re.I)
COMPLAINT = re.compile(r"make a complaint|file a complaint|want to complain|porter plainte|plainte", re.I)
CEASE = re.compile(r"(please )?stop calling me\b(?!.{0,5}every day)|don'?t call me again|cease (all )?contact|(veuillez )?arrêtez de m'?appeler(?! tous les jours)|ne m'?appelez plus", re.I)
FINAL_DEMAND = re.compile(r"final demand|mise en demeure", re.I)
# The amount must start at a number boundary: a greedy prefix used to swallow leading digits ("280.00 $" -> 0.00).
CONFIRM_PTP = re.compile(r"(?:confirm|confirmer|\bnote|\bnoting)[^$]{0,40}\$?\s?(?<![\d,.])([\d,]+(?:\.\d{1,2})?)\s?(?:\$|dollars)?\s(?:on|le)\s([A-Za-zéû]+\.?\s?\d{1,2}(?:st|nd|rd|th)?|\d{1,2}(?:er)?\s[A-Za-zéû]+)", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS_FR = {"janv": 1, "févr": 2, "mars": 3, "avr": 4, "mai": 5, "juin": 6, "juil": 7, "août": 8, "sept": 9, "oct": 10, "nov": 11, "déc": 12}


def _text(turns: list[dict], speaker: str | None = None) -> str:
    return " ".join(t.get("text", "") for t in turns if speaker is None or t.get("speaker") == speaker)


def _parse_month_day(s: str, call_date: date | None) -> date | None:
    s = re.sub(r"(?<=\d)(st|nd|rd|th|er)\b", "", s.strip().lower().replace(".", ""))
    m = re.match(r"([a-zéû]+)\s?(\d{1,2})$", s) or re.match(r"(\d{1,2})\s([a-zéû]+)$", s)
    if not m:
        return None
    a, b = m.groups()
    word, day = (a, b) if a.isalpha() else (b, a)
    month = MONTHS.get(word[:3]) or next((v for k, v in MONTHS_FR.items() if word.startswith(k[:3])), None)
    if not month:
        return None
    year = (call_date.year if call_date else 2026)
    try:
        d = date(year, month, int(day))
    except ValueError:
        return None
    if call_date and d < call_date and (call_date - d).days > 60:  # "Jan 5" said in December
        d = date(year + 1, month, int(day))
    return d


def extract(turns: list[dict], call_date: date | None = None, ptp_record: dict | None = None) -> dict:
    """Structured fields from a redacted transcript (or a note as one 'customer' turn)."""
    cust, agent = _text(turns, "customer"), _text(turns, "agent")
    reason = next((name for name, p in REASONS if p.search(cust)), None)
    tight = bool(TIGHT.search(cust))
    dispute_type = ("fraud" if DISPUTE_FRAUD.search(cust) else
                    "payment_not_applied" if DISPUTE_NOT_APPLIED.search(cust) else
                    "late_fee" if DISPUTE_LATE_FEE.search(cust) else
                    "billing_error" if DISPUTE_BILLING.search(cust) else
                    "other" if DISPUTE_GENERIC.search(cust) else None)
    complaint = bool(COMPLAINT.search(cust))
    cease = bool(CEASE.search(cust))
    amount, due = None, None
    if ptp_record and ptp_record.get("amount") is not None:
        amount, due = float(ptp_record["amount"]), ptp_record.get("date")
    else:
        m = CONFIRM_PTP.search(agent)
        if m:
            amount = float(m.group(1).replace(",", ""))
            due = _parse_month_day(m.group(2), call_date)
    if cease:
        next_step = "stop_contact"
    elif complaint or ESCALATE.search(cust):
        next_step = "escalate_supervisor"
    elif dispute_type:
        next_step = "dispute_investigation"
    elif reason:
        next_step = "hardship_plan_review"
    elif amount is not None:
        next_step = "send_payment_link"
    elif FINAL_DEMAND.search(agent):
        next_step = "call_back"
    else:
        next_step = "call_back"
    hardship = "clear" if reason else ("possible" if tight else "none")
    stated = ("dispute" if dispute_type else "reduced_income" if (reason in ("reduced_income", "job_loss") or tight)
              else None)
    # Turn citations: the turns whose text fired each rule (turn_index, or position for a note).
    ev_hard = _cite(turns, dict(REASONS)[reason], "customer") if reason else (
        _cite(turns, TIGHT, "customer") if tight else [])
    ev_dispute = _cite(turns, DISPUTE_PATTERNS[dispute_type], "customer") if dispute_type else []
    ev_complaint = _cite(turns, COMPLAINT, "customer") if complaint else []
    ev_cease = _cite(turns, CEASE, "customer") if cease else []
    ev_ptp: list[int] = []
    if amount is not None:
        said = re.compile(rf"(?<![\d,.]){int(amount)}(?:[.,]\d\d)?(?!\d)")
        ev_ptp = _cite(turns, CONFIRM_PTP, "agent") or _cite(turns, said)
    ev_next = (ev_cease if cease else (ev_complaint or _cite(turns, ESCALATE, "customer")) if next_step == "escalate_supervisor"
               else ev_dispute if dispute_type else ev_hard if reason else ev_ptp if amount is not None
               else _cite(turns, FINAL_DEMAND, "agent"))
    cites = {"hardship_signal": ev_hard, "stated_delay_reason": ev_dispute if stated == "dispute" else ev_hard if stated else [],
             "dispute_signal": ev_dispute, "complaint": ev_complaint, "cease_request": ev_cease, "promise": ev_ptp,
             "next_steps": ev_next}
    return {"hardship": hardship, "hardship_reason": reason, "stated_delay_reason": stated,
            "dispute": dispute_type is not None, "dispute_type": dispute_type, "complaint": complaint,
            "cease_request": cease, "ptp": {"amount": amount, "date": due.isoformat() if isinstance(due, date) else due}
            if amount is not None else None, "next_step": next_step, "cites": cites}


DISPUTE_PATTERNS = {"fraud": DISPUTE_FRAUD, "payment_not_applied": DISPUTE_NOT_APPLIED, "late_fee": DISPUTE_LATE_FEE,
                    "billing_error": DISPUTE_BILLING, "other": DISPUTE_GENERIC}


def _cite(turns: list[dict], pattern: re.Pattern[str], speaker: str | None = None) -> list[int]:
    return [t.get("turn_index", i) for i, t in enumerate(turns)
            if (speaker is None or t.get("speaker") == speaker) and pattern.search(t.get("text", ""))]


def _fmt_date(d: str | date | None) -> str | None:
    if d is None:
        return None
    if isinstance(d, str):
        try:
            d = date.fromisoformat(d[:10])
        except ValueError:
            return d
    return f"{d.day} {d.strftime('%b')}"


def summary(fields: dict) -> str:
    """Gold-template summary from extracted fields."""
    parts = []
    if fields.get("hardship_reason"):
        parts.append(f"Customer reports {REASON_PHRASE[fields['hardship_reason']]}")
    elif fields.get("hardship") == "possible":
        parts.append("Customer indicates finances are tight")
    if fields.get("dispute_type") in ("late_fee", "billing_error", "payment_not_applied", "fraud"):
        parts.append(f"disputes {fields['dispute_type'].replace('_', ' ')}")
    elif fields.get("dispute"):
        parts.append("disputes a charge")
    p = fields.get("ptp")
    if p and p.get("amount") is not None:
        when = _fmt_date(p.get("date"))
        parts.append(f"promised ${round(p['amount']):,}" + (f" on {when}" if when else ""))
    if fields.get("complaint"):
        parts.append("wants to complain")
    if fields.get("cease_request"):
        parts.append("asked to stop contact")
    if not p and not fields.get("hardship_reason") and not fields.get("dispute"):
        parts.insert(0, "No commitment made")
    parts.append(f"next step: {fields['next_step'].replace('_', ' ')}")
    return "; ".join(parts) + "."


@register("text_features")
def extract_offline(inputs: dict) -> dict:
    """inputs: {text} (a note) or {turns}. Returns the label-schema fields."""
    turns = inputs.get("turns") or [{"speaker": "customer", "text": inputs.get("text", "")}]
    f = extract(turns)
    return {"hardship_signal": f["hardship"], "stated_delay_reason": f["stated_delay_reason"],
            "ptp_intent_strength": None, "dispute_signal": f["dispute"], "evidence": [], **f}
