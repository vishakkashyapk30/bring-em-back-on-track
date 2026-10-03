-- Contract rule 6: every current CRM record maps to exactly one golden_id, and every golden_id is in the C360.
select s.crm_customer_id
from {{ ref('stg_customers') }} s
left join {{ source('identity', 'crm_golden') }} g using (crm_customer_id)
group by s.crm_customer_id having count(g.golden_id) <> 1
union all
select g.golden_id from {{ source('identity', 'crm_golden') }} g
anti join {{ ref('c360_customer') }} c using (golden_id)
