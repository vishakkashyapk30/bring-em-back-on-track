-- Current CRM rows with standardised identity fields. TODO(WS-A): DOB 4-format parse,
-- name normalisation, E.164 check, email verified/not bounced.
select
    crm_customer_id,
    duplicate_of_crm_id,
    national_id_hash,
    first_name, last_name, preferred_name,
    date_of_birth, dob_raw,
    primary_phone_e164,
    case when email_verified_flag = 'true' and email_bounce_flag <> 'true' then email end as email_clean,
    province_code, upper(replace(postal_code, ' ', '')) as postal_code, fsa, time_zone,
    preferred_language,
    consent_call, consent_sms, consent_email, consent_push,
    permitted_call_start_local, permitted_call_end_local, sunday_contact_permitted,
    internal_do_not_call_flag, cease_communication_flag, bankruptcy_flag, consumer_proposal_flag,
    deceased_flag, credit_counselling_agency_flag, legal_representative_flag,
    vulnerability_flag, employer_name, returned_mail_flag,
    effective_from_ts, effective_to_ts
from {{ source('bronze', 'customers') }}
where {{ current_crm_filter() }}
