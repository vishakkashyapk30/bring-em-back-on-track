{#
  ONE definition of the promise-level features (Layer 3), evaluated "as of" a timestamp:
    - training (offline):  as_of = p.ptp_created_ts  -> point-in-time, nothing from after the promise was made
    - live scoring (online): as_of = the scoring time  -> same SQL, latest information
  Text features come from the rule extractor (features.transcript_features / note_features), joined only when
  their available_ts is before as_of.
#}
{% macro ptp_features(as_of, where='true') %}
with p as (
    select p.*, {{ as_of }} as as_of_ts
    from {{ ref('promises_to_pay') }} p
    where {{ where }}
),
ch as (
    select p.ptp_id,
           count(*) filter (where h.direction = 'outbound' and h.contact_ts_local >= p.as_of_ts - interval 30 day) as attempts_30d,
           count(*) filter (where h.rpc_flag and h.contact_ts_local >= p.as_of_ts - interval 30 day)               as rpc_30d,
           count(*)                                                                                                as contacts_90d,
           count(*) filter (where h.complaint_raised_flag)                                                          as complaints_90d,
           count(*) filter (where h.dispute_raised_flag)                                                            as disputes_90d,
           count(*) filter (where h.hardship_mentioned_flag)                                                        as hardship_mentions_90d,
           count(*) filter (where h.cease_request_flag)                                                             as cease_requests_90d
    from p join {{ ref('contact_history') }} h
      on h.case_id = p.case_id and h.contact_ts_local < p.as_of_ts and h.contact_ts_local >= p.as_of_ts - interval 90 day
    group by 1
),
pr as (
    select p.ptp_id,
           count(*) filter (where q.ptp_status in ('broken', 'partially_kept')) as broken_before_in_case,
           count(*) filter (where q.ptp_status = 'kept')                        as kept_before_in_case
    from p join {{ ref('promises_to_pay') }} q
      on q.case_id = p.case_id and q.ptp_id <> p.ptp_id and q.status_ts < p.as_of_ts
    group by 1
),
tx as (
    select p.ptp_id,
           count(*) filter (where t.hardship_signal = 'clear')    as text_hardship_clear_90d,
           count(*) filter (where t.hardship_signal = 'possible') as text_hardship_possible_90d,
           count(*) filter (where t.dispute_signal)               as text_dispute_90d,
           count(*) filter (where t.complaint_cue)                as text_complaint_90d,
           arg_max(t.stated_delay_reason, t.available_ts)         as last_stated_delay_reason
    from p join (
        select case_id, available_ts, hardship_signal, dispute_signal, complaint_cue, stated_delay_reason
        from {{ source('features', 'note_features') }}
        union all
        select case_id, available_ts, hardship_signal, dispute_signal, complaint_cue, stated_delay_reason
        from {{ source('features', 'transcript_features') }}
    ) t on t.case_id = p.case_id and t.available_ts < p.as_of_ts and t.available_ts >= p.as_of_ts - interval 90 day
    group by 1
)
select
    p.ptp_id, p.case_id, x.golden_id, p.as_of_ts, p.ptp_created_ts, p.ptp_due_date, p.ptp_status,
    -- known when the promise is made
    p.ptp_amount, p.days_to_due_at_creation, p.prior_broken_ptp_count, p.ptp_to_overdue_ratio, p.dpd_at_creation,
    p.overdue_at_creation, p.ptp_sequence_in_case, cast(p.reminder_scheduled_flag as int) as reminder_scheduled,
    p.ptp_type, p.payment_method_promised, p.ptp_channel, p.product,
    date_diff('day', p.customer_stated_income_date, p.ptp_due_date)                as due_minus_stated_payday_days,
    cast(p.customer_stated_income_date is not null as int)                         as stated_payday_known,
    -- case context
    date_diff('day', k.case_open_date, cast(p.as_of_ts as date))                    as days_in_case,
    k.entry_dpd, k.primary_product as case_product, k.queue,
    -- contact history (90 days before as-of)
    coalesce(ch.attempts_30d, 0) as attempts_30d, coalesce(ch.rpc_30d, 0) as rpc_30d,
    coalesce(ch.contacts_90d, 0) as contacts_90d, coalesce(ch.complaints_90d, 0) as complaints_90d,
    coalesce(ch.disputes_90d, 0) as disputes_90d, coalesce(ch.hardship_mentions_90d, 0) as hardship_mentions_90d,
    coalesce(ch.cease_requests_90d, 0) as cease_requests_90d,
    -- promise history in the case before as-of
    coalesce(pr.broken_before_in_case, 0) as broken_before_in_case, coalesce(pr.kept_before_in_case, 0) as kept_before_in_case,
    -- text features (rules over notes + transcripts, 90 days before as-of)
    coalesce(tx.text_hardship_clear_90d, 0) as text_hardship_clear_90d,
    coalesce(tx.text_hardship_possible_90d, 0) as text_hardship_possible_90d,
    coalesce(tx.text_dispute_90d, 0) as text_dispute_90d, coalesce(tx.text_complaint_90d, 0) as text_complaint_90d,
    tx.last_stated_delay_reason
from p
join {{ ref('collections_cases') }} k on k.case_id = p.case_id
left join {{ source('identity', 'case_xref') }} x on x.case_id = p.case_id
left join ch on ch.ptp_id = p.ptp_id
left join pr on pr.ptp_id = p.ptp_id
left join tx on tx.ptp_id = p.ptp_id
{% endmacro %}
