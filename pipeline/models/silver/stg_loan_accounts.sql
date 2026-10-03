-- Latest snapshot per account (history stays in account_monthly_snapshot). Never use the wide _m01.._m12
-- columns for training. TODO(WS-A): cast types, select needed columns only.
select *
from {{ source('bronze', 'loan_accounts') }}
qualify row_number() over (partition by loan_id order by snapshot_date desc) = 1
