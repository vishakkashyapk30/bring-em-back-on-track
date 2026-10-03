-- Contract rule 4: consent is never more permissive than any linked current CRM record.
select c.golden_id
from {{ ref('c360_customer') }} c
join {{ source('identity', 'crm_golden') }} g using (golden_id)
join {{ ref('stg_customers') }} s using (crm_customer_id)
where (c.consent_call and not coalesce(s.consent_call, false))
   or (c.consent_sms and not coalesce(s.consent_sms, false))
   or (c.consent_email and not coalesce(s.consent_email, false))
   or (c.consent_push and not coalesce(s.consent_push, false))
