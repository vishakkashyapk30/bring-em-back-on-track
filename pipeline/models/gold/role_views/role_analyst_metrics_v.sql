-- Analyst view (D5): no direct identifiers (no names, tokens or CRM IDs). Aggregates are suppressed below 10
-- customers by the Ask executor.
select golden_id, province_code, fsa, time_zone, preferred_language, segment, contact_block, hardship_flag,
       vulnerability_flag, dispute_open_flag, payroll_delay_days, max_dpd, total_past_due_cad, open_accounts,
       open_cases, match_method, _refreshed_at
from {{ ref('c360_customer') }}
