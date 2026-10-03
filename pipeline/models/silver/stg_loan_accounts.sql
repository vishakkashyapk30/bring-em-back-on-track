-- Lending: one row per loan. Identity formats: "First Last"; DOB YYYY/MM/DD; phone "+1 (250) 785 5700".
select
    loan_id as account_id, product_type, product_code, src_customer_ref, nullif(co_borrower_ref, '') as co_borrower_ref,
    try_cast(snapshot_date as date) as snapshot_date, try_cast(origination_date as date) as open_date,
    try_cast(original_amount as double) as original_amount, try_cast(principal_balance as double) as principal_balance,
    try_cast(total_outstanding as double) as current_balance, try_cast(past_due_amount as double) as past_due_amount,
    try_cast(scheduled_payment_amount as double) as scheduled_payment_amount, payment_frequency,
    try_cast(remaining_term_months as int) as remaining_term_months, try_cast(interest_rate as double) as interest_rate,
    rate_type, try_cast(accrued_interest as double) as accrued_interest, try_cast(fees_outstanding as double) as fees_outstanding,
    try_cast(dpd as int) as dpd, dpd_bucket, try_cast(missed_payments_count as int) as missed_payments_count,
    try_cast(worst_dpd_12m as int) as worst_dpd_12m, try_cast(deferral_count_life as int) as deferral_count_life,
    {{ to_bool('chargeoff_flag') }} as chargeoff_flag, try_cast(chargeoff_date as date) as chargeoff_date,
    try_cast(chargeoff_amount as double) as chargeoff_amount,
    {{ to_bool('hardship_program_flag') }} as hardship_program_flag, hardship_program_type,
    {{ to_bool('pad_enrolled') }} as pad_enrolled, nullif(pad_source_account, '') as pad_source_account,
    borrower_name_raw as name_raw, {{ last_token('borrower_name_raw') }} as last_name_key,
    left({{ first_token('borrower_name_raw') }}, 1) as first_initial,
    try_strptime(borrower_dob_raw, '%Y/%m/%d')::date as dob,
    {{ phone_digits('borrower_phone_raw') }} as phone_digits,
    {{ postal('borrower_postal_raw') }} as postal
from {{ source('bronze', 'loan_accounts') }}
