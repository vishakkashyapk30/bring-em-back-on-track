"""Pass 2: scored matching for source keys that no deterministic bridge reached.

A Fellegi-Sunter-style score with hand-set weights on fields every system carries in its own format (normalised
in silver): last name, date of birth, first initial, postal code, phone (masked card phones compare on the
visible digits). The weights are checked on the deterministically linked keys, which act as an answer key
(see `evaluate`), and the thresholds are set for precision first (a wrong merge means contacting the wrong person).
"""

from __future__ import annotations

AUTO_LINK = 0.90   # at or above: link automatically (if the best candidate is unique)
REVIEW = 0.70      # between REVIEW and AUTO_LINK: steward review queue; below: leave unlinked

# Candidate generation (blocking) + scoring, as DuckDB SQL over a `probe` table and the CRM `index` table.
# probe(source_system, source_ref, last_name_key, first_initial, dob, postal, phone_digits)
# idx(golden_id, last_name_key, first_initial, dob, postal, phone_digits)
SCORE_SQL = """
WITH cand AS (
    SELECT p.source_system, p.source_ref, i.golden_id,
           0.55
           + CASE WHEN p.first_initial = i.first_initial THEN 0.20 ELSE -0.25 END
           + CASE WHEN p.postal IS NOT NULL AND p.postal = i.postal THEN 0.15 ELSE 0 END
           + CASE WHEN p.phone_digits IS NOT NULL AND i.phone_digits IS NOT NULL
                       AND length(p.phone_digits) = 10 AND length(i.phone_digits) = 10
                       AND (p.phone_digits = i.phone_digits
                            OR (p.phone_digits LIKE '%x%'
                                AND left(p.phone_digits, 6) = left(i.phone_digits, 6)
                                AND right(p.phone_digits, 2) = right(i.phone_digits, 2)))
                  THEN 0.15 ELSE 0 END AS score
    FROM probe p JOIN idx i ON p.last_name_key = i.last_name_key AND p.dob = i.dob
    UNION ALL
    -- second block for records without a DOB: name + postal must both agree
    SELECT p.source_system, p.source_ref, i.golden_id,
           0.45 + CASE WHEN p.first_initial = i.first_initial THEN 0.20 ELSE -0.25 END + 0.15 AS score
    FROM probe p JOIN idx i ON p.last_name_key = i.last_name_key AND p.postal = i.postal
    WHERE p.dob IS NULL
),
best AS (
    SELECT source_system, source_ref, golden_id, max(score) score FROM cand GROUP BY ALL
),
ranked AS (
    SELECT *, row_number() OVER (PARTITION BY source_system, source_ref ORDER BY score DESC, golden_id) rn,
           count(*) FILTER (WHERE score >= {review}) OVER (PARTITION BY source_system, source_ref) n_plausible
    FROM best
)
SELECT source_system, source_ref, golden_id, least(score, 0.99) AS score, n_plausible
FROM ranked WHERE rn = 1
"""


def score_sql() -> str:
    return SCORE_SQL.replace("{review}", str(REVIEW))
