-- Contract rule 5: no golden_id links two different non-null national_id_hash values.
select g.golden_id
from {{ source('identity', 'crm_golden') }} g
join {{ ref('stg_customers') }} s using (crm_customer_id)
where s.national_id_hash is not null
group by g.golden_id having count(distinct s.national_id_hash) > 1
