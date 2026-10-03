"""Blocking rules for candidate pairs (pass 0): FSA, last-name soundex, DOB year, phone last 4."""

BLOCKING_RULES: list[str] = [
    "l.fsa = r.fsa and l.last_name_soundex = r.last_name_soundex",
    "l.dob_year = r.dob_year and l.phone_last4 = r.phone_last4",
    # TODO(WS-A): tune after profiling pair counts
]
