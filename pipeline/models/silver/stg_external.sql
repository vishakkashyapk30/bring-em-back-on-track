-- Bureau pulls (latest per customer). Subject key = 10-digit CIF. Name "LAST, FIRST MIDDLE"; postal from address.
select
    {{ cif('bank_subject_ref') }} as bank_subject_ref, bureau_request_id, bureau_name,
    try_cast(pull_date as date) as pull_date, try_cast(file_received_ts as timestamp) as file_received_ts,
    try_cast(risk_score as int) as risk_score, try_cast(risk_score_delta_90d as int) as risk_score_delta_90d,
    try_cast(inquiries_hard_3m as int) as inquiries_hard_3m, try_cast(bnpl_trades_count as int) as bnpl_trades_count,
    try_cast(off_us_delinquent_trades as int) as off_us_delinquent_trades,
    try_cast(high_cost_lender_trades_count as int) as high_cost_lender_trades_count,
    try_cast(total_monthly_obligations as double) as total_monthly_obligations,
    {{ to_bool('address_mismatch_flag') }} as address_mismatch_flag,
    subject_name_reported as name_raw,
    {{ last_token("split_part(subject_name_reported, ',', 1)") }} as last_name_key,
    left({{ first_token("split_part(subject_name_reported, ',', 2)") }}, 1) as first_initial,
    try_cast(subject_dob_reported as date) as dob,
    nullif(regexp_extract(upper(replace(subject_address_reported, ' ', '')), '([A-Z][0-9][A-Z][0-9][A-Z][0-9])$', 1), '') as postal
from {{ source('bronze', 'external') }}
