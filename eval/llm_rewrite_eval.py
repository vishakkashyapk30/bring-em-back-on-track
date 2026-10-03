"""Which local model should understand unseen questions? Scores the LLM question rewrite on paraphrases that map to a
certified metric (must pick that metric) and on questions that must be declined. Wrong guesses count double against a
model because Ask would answer the wrong question. Run:
LLM_PROVIDER=ollama OLLAMA_MODEL=<model> python -m eval.llm_rewrite_eval
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date

from nlq.pipeline import _metric
from nlq.rewrite import choose_metric

AS_OF = date(2026, 9, 28)
# (question, expected metric id or None to decline). None of these are in the released benchmark or the probe set.
CASES = [
    ("What proportion of the people we phoned in September actually reached the right person?", "rpc_rate"),
    ("Typical number of days late for an open file, by team?", "average_dpd"),
    ("What fraction of promises due in July were honoured?", "promise_kept_rate"),
    ("How much money did promises bring in during September 2026?", "paid_against_promises"),
    ("Share of customers asking for hardship help by province for cases opened in 2026?", "hardship_rate"),
    ("How many files are currently open, split by bucket?", "open_case_count"),
    ("What does it cost us on average to try reaching someone, by channel, in August 2026?", "cost_per_contact"),
    ("Rate at which customers who were reached made a promise, by site, September 2026", "ptp_rate"),
    ("How many cases came in during August 2026 by product?", "case_count"),
    ("How many accounts did we write off over the past 12 months, by product?", "write_off"),
    ("Percentage of personal loans that are late today", "loan_delinquency_rate"),
    ("How many complaints did customers raise in September 2026?", "complaint_count"),
    ("Which strategy got the most cases back to current, for cases opened in 2026?", "cure_rate"),
    ("How many outbound texts went out on 24 September 2026?", "contact_count"),
    ("Average amount customers are behind on open cases, by queue", "average_overdue"),
    ("What was the average handle time of calls in September?", None),
    ("Which customers will default next month?", None),
    ("How satisfied are customers with our agents?", None),
    ("What was our total revenue from collections interest in 2026?", None),
    ("How many agents do we have on shift tomorrow?", None),
    ("Forecast the cure rate for October 2026", None),
    ("What was the average talk time per call by site in September?", None),
    ("Who is the best performing agent's manager?", None),
    ("What is the net promoter score of the hardship team?", None),
]


def main() -> None:
    right = wrong = declined_ok = missed = 0
    t0 = time.perf_counter()
    for q, want in CASES:
        try:
            pick = choose_metric(q, AS_OF)
        except Exception as e:  # noqa: BLE001
            pick = None
            print("ERR", e)
        got = None
        if pick:
            a = _metric(q, AS_OF, force_metric=pick["metric_id"])
            got = pick["metric_id"] if a is not None else None
        ok = got == want
        if want is None:
            declined_ok += ok
            wrong += (not ok)
        else:
            right += ok
            missed += (got is None)
            wrong += (got is not None and not ok)
        print(("ok  " if ok else "BAD ") + f"want={want!s:22} got={got!s:22} | {q[:70]}")
    answerable = sum(1 for _, w in CASES if w)
    print(json.dumps({"model": sys.argv[1] if len(sys.argv) > 1 else "?", "mapped_correctly": f"{right}/{answerable}",
                      "declined_correctly": f"{declined_ok}/{len(CASES) - answerable}", "wrong_answer_given": wrong,
                      "seconds": round(time.perf_counter() - t0)}))


if __name__ == "__main__":
    main()
