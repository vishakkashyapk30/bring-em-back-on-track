{{ config(materialized='view') }}
-- Collections cases with their golden ID (identity.case_xref recovers mistyped coll_customer_ref via the primary account).
select k.*, x.golden_id, x.link_path as identity_link_path
from {{ ref('collections_cases') }} k
left join {{ source('identity', 'case_xref') }} x using (case_id)
