-- Role view for NL-to-SQL and the API (D5). The read-only executor can only see role_<role>_* views.
-- TODO(WS-A/WS-B): restrict columns, apply row filters, mask names, suppress groups < 10 where aggregate.
select golden_id, province_code, fsa, max_dpd, total_past_due_cad, hardship_flag, _refreshed_at
from {{ ref('c360_customer') }}
