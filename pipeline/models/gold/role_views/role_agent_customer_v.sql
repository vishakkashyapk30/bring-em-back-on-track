-- Agent view (D5): customers with an open case; the API filters further to the agent's own cases.
select c.*, k.assigned_agent_id, k.queue, k.current_bucket
from {{ ref('c360_customer') }} c
join {{ ref('c360_case') }} k on k.case_id = c.open_case_id
