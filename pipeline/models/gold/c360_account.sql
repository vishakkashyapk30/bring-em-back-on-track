-- gold.c360_account: one row per account across cards, lending and core banking, in one shape, with the golden ID
-- from identity resolution (identity.account_xref).
with accts as (
    select 'cards' as source_system, account_id, product_type, product_code, src_customer_ref as source_ref,
           open_date, snapshot_date, account_status, current_balance, past_due_amount, dpd, dpd_bucket,
           credit_limit as limit_or_original_amount, minimum_payment_due as payment_due, purchase_apr as interest_rate,
           dispute_open_flag, chargeoff_flag, hardship_program_flag
    from {{ ref('stg_card_accounts') }}
    union all
    select 'lending', account_id, product_type, product_code, src_customer_ref, open_date, snapshot_date,
           case when chargeoff_flag then 'charged_off' when coalesce(current_balance, 0) <= 0 then 'closed' else 'active' end,
           current_balance, past_due_amount, dpd, dpd_bucket, original_amount, scheduled_payment_amount, interest_rate,
           false, chargeoff_flag, hardship_program_flag
    from {{ ref('stg_loan_accounts') }}
    union all
    select 'core_banking', account_id, product_type, product_code, src_customer_ref, open_date, snapshot_date,
           account_status, current_balance, case when coalesce(dpd, 0) > 0 then overdraft_used else 0 end, dpd, dpd_bucket,
           overdraft_limit, null, null, false, false, false
    from {{ ref('stg_deposit_accounts') }}
)
select a.*,
       x.golden_id, x.match_method, x.match_confidence, x.link_path,
       (a.account_status in ('active', 'blocked', 'dormant', 'frozen') and not coalesce(a.chargeoff_flag, false)) as is_open
from accts a
left join {{ source('identity', 'account_xref') }} x
       on x.source_system = a.source_system and x.account_id = a.account_id
