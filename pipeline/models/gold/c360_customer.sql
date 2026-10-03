-- gold.c360_customer v1.0: one row per golden_id (contract: docs/contracts/c360_customer.v1.yaml).
-- Survivorship: consent = most restrictive; hardship/vulnerability = set if any linked.
-- TODO(WS-A): display_name, tokens, contact_block precedence, employer_key, max_dpd/total_past_due from c360_account.
with links as (
    select golden_id, crm_customer_id, match_method, match_probability
    from {{ source('identity', 'identity_xref') }}
    where source_system = 'crm'
),
crm as (select * from {{ ref('stg_customers') }})
select
    l.golden_id,
    list(distinct c.crm_customer_id)                         as crm_customer_ids,
    min(l.match_method)                                      as match_method,      -- TODO precedence
    min(l.match_probability)                                 as match_confidence,
    any_value(coalesce(c.preferred_name, c.first_name) || ' ' || c.last_name) as display_name,
    any_value(c.province_code)                               as province_code,
    any_value(c.fsa)                                         as fsa,
    any_value(c.time_zone)                                   as time_zone,
    any_value(c.preferred_language)                          as preferred_language,
    bool_and(c.consent_call = 'true')                        as consent_call,
    bool_and(c.consent_sms = 'true')                         as consent_sms,
    bool_and(c.consent_email = 'true')                       as consent_email,
    bool_and(c.consent_push = 'true')                        as consent_push,
    max(c.permitted_call_start_local)                        as permitted_call_start_local,  -- latest start
    min(c.permitted_call_end_local)                          as permitted_call_end_local,    -- earliest end
    case
        when bool_or(c.deceased_flag = 'true') then 'deceased'
        when bool_or(c.bankruptcy_flag = 'true' or c.consumer_proposal_flag = 'true') then 'insolvency'
        when bool_or(c.cease_communication_flag = 'true') then 'cease'
        when bool_or(c.legal_representative_flag = 'true' or c.credit_counselling_agency_flag = 'true') then 'represented'
        else 'none'
    end                                                      as contact_block,
    'none'                                                   as hardship_flag,      -- TODO from cases + signals
    bool_or(c.vulnerability_flag = 'true')                   as vulnerability_flag,
    null::boolean                                            as dispute_open_flag,  -- TODO
    null::varchar                                            as employer_key,       -- TODO S1
    null::integer                                            as payroll_delay_days, -- TODO
    null::integer                                            as max_dpd,            -- TODO
    null::decimal(12, 2)                                     as total_past_due_cad, -- TODO
    null::varchar                                            as open_case_id,       -- TODO
    now()                                                    as _refreshed_at
from links l
join crm c using (crm_customer_id)
group by l.golden_id
