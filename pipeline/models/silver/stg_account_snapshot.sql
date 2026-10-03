-- Quarter-end account history (Dec 2023 to Jun 2026). month_end_date comes in three formats; slash dates are
-- DD/MM or MM/DD: quarter ends (31/03, 30/06, 30/09, 31/12) disambiguate them (day > 12).
select
    account_id, crm_customer_id, product_type, account_status,
    coalesce(
        try_strptime(month_end_date, '%Y-%m-%d'),
        try_strptime(month_end_date, '%Y%m%d'),
        case when try_cast(split_part(month_end_date, '/', 1) as int) > 12 then try_strptime(month_end_date, '%d/%m/%Y')
             else try_strptime(month_end_date, '%m/%d/%Y') end
    )::date as month_end_date,
    try_cast(balance as double) as balance, try_cast(minimum_due as double) as minimum_due,
    try_cast(payment_made as double) as payment_made, try_cast(dpd as int) as dpd, dpd_bucket,
    {{ to_bool('write_off_flag') }} as write_off_flag
from {{ source('bronze', 'account_monthly_snapshot') }}
