-- Feature group "payday" (registry: features/registry.yaml). Same SQL feeds offline + online.
-- TODO(WS-C): available_ts = snapshot_date + extract lag; days_to_expected_payroll; per golden_id.
select src_customer_ref, snapshot_date,
       payroll_delay_days, expected_next_payroll_date, payroll_amount_change_pct,
       snapshot_date as available_ts
from {{ source('bronze', 'deposit_accounts') }}
