-- gold.c360_account: one row per account, all products in one shape.
-- TODO(WS-A): map src_customer_ref -> golden_id through identity_xref; normalise balances/status per product.
select 'card' as product, card_account_id as account_id, src_customer_ref, snapshot_date,
       dpd, past_due_amount, account_status
from {{ ref('stg_card_accounts') }}
union all
select 'loan', loan_id, src_customer_ref, snapshot_date, dpd, past_due_amount, null
from {{ ref('stg_loan_accounts') }}
union all
select 'deposit', deposit_account_id, src_customer_ref, snapshot_date, null, null, account_status
from {{ ref('stg_deposit_accounts') }}
