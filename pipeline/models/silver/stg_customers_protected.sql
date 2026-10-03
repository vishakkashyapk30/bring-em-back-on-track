-- RESTRICTED: protected attributes for the fairness audit only (governance/fairness). Never join into gold
-- or features. Age is included because we treat it as protected too.
select crm_customer_id, gender_code, marital_status, citizenship_status, household_size, dependants_count,
       newcomer_program_flag, newcomer_arrival_date, accessibility_needs_flag, accessibility_type,
       vulnerability_type, age, age_band
from {{ source('bronze', 'customers') }}
