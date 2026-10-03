-- Cards: one row per account (latest snapshot). Identity fields parsed from the card system's formats:
-- names "F. LAST", "FIRST LAST" or "LAST/FIRST"; DOB DD-MM-YYYY; phones often masked (780304xxx63).
with src as (select * from {{ source('bronze', 'card_accounts') }}),
parsed as (
    select *,
        case when cardholder_name_raw like '%/%' then {{ last_token("split_part(cardholder_name_raw, '/', 1)") }}
             else {{ last_token('cardholder_name_raw') }} end as last_name_key,
        case when cardholder_name_raw like '%/%' then left({{ first_token("split_part(cardholder_name_raw, '/', 2)") }}, 1)
             else left({{ first_token('cardholder_name_raw') }}, 1) end as first_initial
    from src
)
select
    card_account_id as account_id, 'card' as product_type, product_code, src_customer_ref,
    try_cast(snapshot_date as date) as snapshot_date, try_cast(open_date as date) as open_date,
    try_cast(months_on_book as int) as months_on_book, account_status,
    try_cast(credit_limit as double) as credit_limit, try_cast(current_balance as double) as current_balance,
    try_cast(past_due_amount as double) as past_due_amount, try_cast(minimum_payment_due as double) as minimum_payment_due,
    try_cast(purchase_apr as double) as purchase_apr, try_cast(utilisation as double) as utilisation,
    try_cast(dpd as int) as dpd, dpd_bucket, try_cast(worst_dpd_12m as int) as worst_dpd_12m,
    {{ to_bool('dispute_open_flag') }} as dispute_open_flag, {{ to_bool('chargeoff_flag') }} as chargeoff_flag,
    try_cast(chargeoff_date as date) as chargeoff_date, try_cast(chargeoff_amount as double) as chargeoff_amount,
    {{ to_bool('hardship_program_flag') }} as hardship_program_flag, hardship_program_type,
    cardholder_name_raw as name_raw, last_name_key, first_initial,
    try_strptime(cardholder_dob_raw, '%d-%m-%Y')::date as dob,
    {{ phone_digits('cardholder_phone_raw') }} as phone_digits,
    {{ postal('cardholder_postal_raw') }} as postal
from parsed
