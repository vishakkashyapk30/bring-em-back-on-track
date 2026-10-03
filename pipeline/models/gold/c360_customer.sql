-- gold.c360_customer v1.0: one row per golden_id (contract docs/contracts/c360_customer.v1.yaml, DC-COLL-C360-001).
-- Survivorship: name/contact from the primary CRM record (not deleted, not a duplicate, most recently updated);
-- consent = most restrictive across linked records; hardship and vulnerability = set if any linked record is set.
-- No protected attributes are selected (contract rule 8).
with crm as (
    select g.golden_id, c.*
    from {{ ref('stg_customers') }} c
    join {{ source('identity', 'crm_golden') }} g using (crm_customer_id)
),
primary_rec as (
    select * from crm
    qualify row_number() over (
        partition by golden_id
        order by is_deleted, duplicate_of_crm_id is not null, last_profile_update_ts desc nulls last, crm_customer_id
    ) = 1
),
agg as (
    select golden_id,
           list(crm_customer_id order by crm_customer_id) as crm_customer_ids,
           bool_and(coalesce(consent_call, false))  as consent_call,
           bool_and(coalesce(consent_sms, false))   as consent_sms,
           bool_and(coalesce(consent_email, false)) as consent_email,
           bool_and(coalesce(consent_push, false))  as consent_push,
           max(permitted_call_start_local)          as permitted_call_start_local,
           min(permitted_call_end_local)            as permitted_call_end_local,
           bool_and(coalesce(sunday_contact_permitted, false)) as sunday_contact_permitted,
           bool_or(coalesce(internal_do_not_call_flag, false)) as internal_do_not_call_flag,
           bool_or(deceased_flag)                    as any_deceased,
           bool_or(bankruptcy_flag or consumer_proposal_flag) as any_insolvency,
           bool_or(cease_communication_flag)         as any_cease,
           bool_or(legal_representative_flag or credit_counselling_agency_flag or power_of_attorney_flag) as any_rep,
           bool_or(coalesce(vulnerability_flag, false)) as any_vulnerable,
           min(vulnerability_review_date)           as vulnerability_review_date
    from crm group by 1
),
acct as (
    select golden_id,
           count(*)                                         as accounts,
           count(*) filter (where is_open)                  as open_accounts,
           max(dpd) filter (where is_open)                  as max_dpd,
           sum(past_due_amount) filter (where is_open)      as total_past_due_cad,
           sum(current_balance) filter (where is_open and source_system <> 'core_banking') as total_credit_balance_cad,
           min(match_confidence)                            as min_link_confidence,
           bool_or(match_method = 'probabilistic')          as any_probabilistic,
           bool_or(coalesce(dispute_open_flag, false) and is_open) as card_dispute_open
    from {{ ref('c360_account') }} where golden_id is not null group by 1
),
cases as (
    select golden_id,
           arg_max(case_id, case_open_date) filter (where case_status = 'open') as open_case_id,
           count(*) filter (where case_status = 'open')                           as open_cases,
           bool_or(case_status = 'open' and hardship_flag and (hardship_program_accepted or hardship_source in ('agent_coded', 'customer_form'))) as hardship_confirmed,
           bool_or(case_status = 'open' and hardship_flag)                        as hardship_any_open,
           bool_or(case_status = 'open' and dispute_status = 'open')              as case_dispute_open,
           bool_or(case_status = 'open' and vulnerable_customer_flag)             as case_vulnerable,
           bool_or(case_status = 'open' and cease_contact_flag)                   as case_cease,
           bool_or(case_status = 'open' and insolvency_hold_flag)                 as case_insolvency,
           bool_or(case_status = 'open' and deceased_hold_flag)                   as case_deceased,
           bool_or(case_status = 'open' and third_party_rep_flag)                 as case_rep
    from {{ ref('c360_case') }} where golden_id is not null group by 1
),
ids as (
    select golden_id,
           count(distinct source_system) as source_systems,
           list(distinct source_system || ':' || source_ref order by source_system || ':' || source_ref) as source_refs
    from {{ source('identity', 'identity_xref') }} group by 1
),
dep as (
    select x.golden_id, max(d.payroll_delay_days) as payroll_delay_days
    from {{ ref('stg_deposit_accounts') }} d
    join {{ source('identity', 'account_xref') }} x on x.source_system = 'core_banking' and x.account_id = d.account_id
    group by 1
)
select
    p.golden_id,
    a.crm_customer_ids,
    case when coalesce(ac.any_probabilistic, false) then 'probabilistic' else 'deterministic' end as match_method,
    cast(least(coalesce(ac.min_link_confidence, 1.0), 1.0) as decimal(4, 3))           as match_confidence,
    coalesce(p.preferred_name, p.first_name) || ' ' || p.last_name                       as display_name,
    case when p.primary_phone_e164 is not null then sha256(p.primary_phone_e164) end     as phone_token,
    case when p.email_clean is not null then sha256(lower(p.email_clean)) end            as email_token,
    p.province_code, p.fsa, p.city, p.time_zone, p.preferred_language,
    p.segment, p.customer_since_date, upper(p.employer_name) as employer_key,
    a.consent_call, a.consent_sms, a.consent_email, a.consent_push,
    a.permitted_call_start_local, a.permitted_call_end_local, a.sunday_contact_permitted, a.internal_do_not_call_flag,
    case
        when a.any_deceased or coalesce(c.case_deceased, false) then 'deceased'
        when a.any_insolvency or coalesce(c.case_insolvency, false) then 'insolvency'
        when a.any_cease or coalesce(c.case_cease, false) then 'cease'
        when a.any_rep or coalesce(c.case_rep, false) then 'represented'
        else 'none'
    end as contact_block,
    case when coalesce(c.hardship_confirmed, false) then 'clear'
         when coalesce(c.hardship_any_open, false) then 'possible'
         else 'none' end                                                                  as hardship_flag,
    (a.any_vulnerable or coalesce(c.case_vulnerable, false))                              as vulnerability_flag,
    a.vulnerability_review_date,
    (coalesce(c.case_dispute_open, false) or coalesce(ac.card_dispute_open, false))       as dispute_open_flag,
    d.payroll_delay_days,
    coalesce(ac.max_dpd, 0)                                                               as max_dpd,
    cast(coalesce(ac.total_past_due_cad, 0) as decimal(12, 2))                            as total_past_due_cad,
    cast(coalesce(ac.total_credit_balance_cad, 0) as decimal(14, 2))                      as total_credit_balance_cad,
    coalesce(ac.accounts, 0) as accounts, coalesce(ac.open_accounts, 0) as open_accounts,
    i.source_systems,   -- CRM, cards, lending, core banking, bureau, collections
    i.source_refs,
    c.open_case_id, coalesce(c.open_cases, 0) as open_cases,
    now() as _refreshed_at
from primary_rec p
join agg a using (golden_id)
left join acct ac using (golden_id)
left join cases c using (golden_id)
left join dep d using (golden_id)
left join ids i using (golden_id)
