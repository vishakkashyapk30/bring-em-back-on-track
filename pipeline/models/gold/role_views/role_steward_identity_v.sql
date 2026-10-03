-- Data steward view: identity links and confidence, no contact details.
select x.golden_id, x.source_system, x.source_ref, x.match_method, x.match_probability, x.evidence
from {{ source('identity', 'identity_xref') }} x
