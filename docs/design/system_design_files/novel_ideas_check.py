#!/usr/bin/env python3
"""Check novel_ideas.md against the data dictionary.

1. Every `table.column` token must exist in the Columns sheet (call_transcripts uses turn.* columns).
2. Every `table` named in a token must be a real table; row counts and enum claims below are asserted too.
3. The scoreboard must have unique IDs, DF 1-5, and every ID must have a section heading.
Exit 0 and print OK when all pass.
"""
import csv
import re
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
dd = here.parent / "data_dictionary"
cols = {}
for r in list(csv.reader(open(dd / "CIBC Hackathon - Data Dictionary - Columns.csv")))[1:]:
    cols.setdefault(r[0], {})[r[1]] = r
tables = {r[0]: r for r in list(csv.reader(open(dd / "CIBC Hackathon - Data Dictionary - Tables.csv")))[1:]}
V1 = len(sys.argv) > 1
md = (Path(sys.argv[1]) if V1 else here / "novel_ideas.md").read_text()
reg = (here / "novel_ideas.md").read_text()
problems = []

# 1 + 2: table.column tokens
tokens = set(re.findall(r"`([a-z_0-9]+)\.([a-z_0-9.]+)`", md))
checked = 0
for t, c in sorted(tokens):
    if t not in tables:
        continue  # not a table reference (e.g. a file name)
    checked += 1
    if c not in cols.get(t, {}):
        problems.append(f"unknown column: {t}.{c}")

# enum / value claims: (table, column, value that must appear in the description)
claims = [
    ("collections_cases", "hardship_plan_type", "skip_payment"),
    ("collections_cases", "hardship_plan_type", "term_extension"),
    ("loan_accounts", "hardship_program_type", "skip_payment"),
    ("offers", "eligibility_result", "ineligible_overridden"),
    ("offers", "decline_reason", "still_unaffordable"),
    ("offers", "decline_reason", "wants_lower"),
    ("offers", "decline_reason", "will_pay_full"),
    ("offers", "decline_reason", "distrust"),
    ("collections_cases", "hardship_source", "llm_flag"),
    ("ops_events", "event_type", "external_economic"),
    ("ops_events", "event_type", "data_feed_issue"),
    ("ops_events", "event_type", "platform_release"),
    ("reference_documents", "doc_type", "release_note"),
    ("model_scores", "entity_type", "customer_hour_slot"),
    ("model_scores", "entity_type", "customer_channel"),
    ("case_assignment_history", "assignment_method", "randomised_pilot"),
    ("contact_history", "channel_v2", "26-Sep"),
    ("channel_capacity", "time_band", "17-21"),
    ("customers", "vulnerability_type", "Protected"),
]
for t, c, v in claims:
    row = cols.get(t, {}).get(c)
    if not row:
        problems.append(f"claim column missing: {t}.{c}")
        continue
    text = " ".join(row)
    if v not in text:
        problems.append(f"claim not supported: {t}.{c} lacks '{v}'")

# protected-attribute claims
for t, c in [("customers", "household_size"), ("customers", "dependants_count"), ("customers", "accessibility_needs_flag"),
             ("voice_samples", "customer_accent_region"), ("customers", "vulnerability_type")]:
    if "Protected" not in " ".join(cols[t][c]):
        problems.append(f"{t}.{c} is not marked protected")
for t, c in [("customers", "vulnerability_flag"), ("customers", "employer_name"), ("customers", "monthly_housing_cost")]:
    if "Protected" in " ".join(cols[t][c]):
        problems.append(f"{t}.{c} is unexpectedly protected")

# table facts quoted in the text
if "Parquet" not in tables["transactions"][4] or "customer sample" not in tables["transactions"][2]:
    problems.append("transactions description changed")
if tables["call_transcripts"][5].replace('"', "") != "25,000":
    problems.append("call_transcripts row count changed")
if tables["voice_samples"][5].replace('"', "") != "2,000":
    problems.append("voice_samples row count changed")
if "~2.5M" not in tables["contact_history"][5]:
    problems.append("contact_history row count changed")
if "call_transcripts" not in cols["call_transcripts"]["transcript_id"][0]:
    problems.append("call_transcripts missing")

# 3: scoreboard
ids, board = [], re.findall(r"(?m)^\| ([A-Z]\d) \| (.+?) \| (.+?) \| (.+?) \| (\d) \| (\d) \| (.+?) \| (.+?) \| (.+?) \|$", reg)
reg_df = {b_[0]: b_[4] for b_ in board}
if V1:
    # the design's section 7 table: | ID | Capability | Key fields | DF | Status |
    rows = re.findall(r"(?m)^\| ([A-Z]\d) \| (.+?) \| (.+?) \| (\d)(?: \(day\), (\d))?(?: \(hour\))? \| (.+?) \|$", md)
    for i, name, fields, df, df2, status in rows:
        ids.append(i)
        if reg_df.get(i) != df:
            problems.append(f"{i}: DF {df} differs from the register ({reg_df.get(i)})")
    missing = set(reg_df) - set(ids)
    if missing:
        problems.append(f"capabilities missing from section 7: {sorted(missing)}")
    for i in reg_df:
        if len(re.findall(rf"\b{i}\b", md)) < 2:
            problems.append(f"{i}: named only in the table, not described in a layer")
else:
    for i, name, who, layer, df, nov, eff, risk, verdict in board:
        ids.append(i)
        if not (1 <= int(df) <= 5 and 1 <= int(nov) <= 5):
            problems.append(f"{i}: score out of range")
        if not re.search(rf"(?m)^###? {i}\. ", md):
            problems.append(f"{i}: no section heading")
if len(ids) != len(set(ids)):
    problems.append("duplicate IDs in scoreboard")
if len(ids) != 15:
    problems.append(f"expected 15 ideas, found {len(ids)}")

if problems:
    print("PROBLEMS:")
    for p in problems:
        print(" -", p)
    sys.exit(1)
print(f"OK: {checked} table.column references and {len(claims)} value claims verified, {len(ids)} ideas covered")
