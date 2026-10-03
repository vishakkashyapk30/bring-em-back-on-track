-- Who is on each account: primary holder, joint holder (deposit joint_holder_ref is a CIF) and co-borrower
-- (loan co_borrower_ref is a lending borrower number).
select account_id, source_system, golden_id, 'primary' as role
from {{ source('identity', 'account_xref') }} where golden_id is not null
union all
select d.account_id, 'core_banking', k.golden_id, 'joint'
from {{ ref('stg_deposit_accounts') }} d
join {{ source('identity', 'source_key_xref') }} k
  on k.source_system = 'core_banking' and k.source_ref = lpad(d.joint_holder_ref, 10, '0')
where d.joint_holder_ref is not null
union all
select l.account_id, 'lending', k.golden_id, 'co_borrower'
from {{ ref('stg_loan_accounts') }} l
join {{ source('identity', 'source_key_xref') }} k
  on k.source_system = 'lending' and k.source_ref = l.co_borrower_ref
where l.co_borrower_ref is not null
