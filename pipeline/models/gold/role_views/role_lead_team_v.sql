-- Team lead view: open-case customers with team assignment.
select c.golden_id, c.display_name, c.hardship_flag, c.vulnerability_flag, c.max_dpd, c.total_past_due_cad,
       k.case_id, k.assigned_team, k.assigned_agent_id, k.queue, k.strategy_code, k.test_cell
from {{ ref('c360_customer') }} c
join {{ ref('c360_case') }} k on k.case_id = c.open_case_id
